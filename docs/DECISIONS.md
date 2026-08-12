# Decisions

Context, decision, cost.

## 1. Uploads go straight to S3; Django never sees the bytes

**Context.** The obvious design has the browser POST a file to Django,
which re-uploads it to S3. Every byte crosses the app server twice.

**Decision.** Django only ever hands out a presigned PUT URL. The browser
PUTs directly to MinIO (real S3 in production); Django's own process
never holds the file in memory or on disk.

**Cost.** The app server can no longer validate file *content* before
it lands in the bucket -- no virus scan, no re-encode, no dimension
check before storage. A production version would need a second-stage
worker to validate and quarantine, not the request path itself.

## 2. An event only goes out after the write is verified, not claimed

**Context.** The browser could call `/photos/{id}/confirm/` right after
its PUT resolves -- but a PUT resolving with 200 doesn't guarantee the
object exists; a network partition between client and S3 on the response
leg, or a client that lies, both look identical to Django from the
confirm call alone.

**Decision.** `confirm_upload` calls `head_object` against S3 before
touching the database or the channel layer. No object, no confirmation,
409 instead -- the same pattern as the acknowledged-write-then-broadcast
flow in `tinclone-backend`, applied here to Channels groups instead of a
message queue.

**Cost.** One extra network round trip to S3 on every confirm. Cheaper
than the alternative: a WebSocket message pointing at a photo that
404s when a viewer tries to load its thumbnail, with no way for any
viewer to know it was ever wrong.

## 3. The broadcast is best-effort; the confirmation is not

**Context.** Found by actually stopping the Redis container mid-request
(not simulated, not mocked, docker compose stop redis while a real
confirm request was in flight): `channels_redis.core.RedisChannelLayer`
raises a bare `ConnectionError` out of `group_send`, uncaught. The first
version of `confirm_upload` let that exception propagate, which turned
into a Django 500 on a request whose write had *already succeeded* --
the photo was CONFIRMED in Postgres, and the response told the uploader
the opposite.

**Decision.** Wrap the `group_send` call in try/except, log the failure,
and still return 200 with the photo's data. The row landing in Postgres
is the fact this service is responsible for getting right; a viewer who
happens to be connected at the exact moment Redis is down misses one
live update and sees the photo on their next page load or reconnect,
which is a real but bounded cost.

**Cost.** A connected viewer can silently miss a photo with no retry and
no "you missed something" indicator. Explicitly accepted rather than
building a per-viewer catch-up mechanism for a failure mode this
narrow -- the alternative (persisting every missed event per connection)
is closer to `feat/resume-after-reconnect` in `websocket-presence-board`
than to anything this project's scope justifies. See
`docs/vs-fastapi-websockets.md` for how that project's Redis bridge
compares.

## 4. No `put_bucket_cors` call -- MinIO doesn't need one

**Context.** The first version of `bootstrap_storage` called
`s3_client.put_bucket_cors(...)` after creating the bucket, following
the standard "presigned PUT needs CORS" advice that's correct for real
AWS S3. It failed immediately: `NotImplemented: A header you provided
implies functionality that is not implemented`. Swapping boto3 for
MinIO's own `mc cors set` CLI produced the identical error, which ruled
out a boto3-specific cause (a mandatory `x-amz-checksum-crc32` header
newer botocore attaches to this API, confirmed by inspecting the actual
request botocore sent) in favor of a simpler one: `curl -X OPTIONS`
against the bucket, with *no* CORS policy ever set, already returned a
correct preflight response -- origin, method and headers all echoed,
204. This MinIO release answers CORS for every bucket unconditionally;
`PutBucketCors` is vestigial.

**Decision.** Don't call it. `ensure_bucket()` creates the bucket and
stops.

**Cost.** This is a MinIO-local shortcut, not a portable one. A real S3
bucket stays closed to cross-origin requests until a CORS policy is set
explicitly, and deploying against real S3 without ever adding one back
would silently fail the exact upload flow this project exists to
demonstrate -- the failure would just show up for the first time in a
different environment than the one it was found in.

## 5. Presigning happens on a different client than the one that checks

**Context.** Inside Docker Compose, Django reaches MinIO as
`minio:9000`; a browser on the host has never heard of that hostname.
SigV4 signs the `Host` header into the request, so a presigned URL is
only valid against the exact host it was signed for -- rewriting a
signed URL's host after the fact (the obvious fix) invalidates its own
signature rather than working around the mismatch.

**Decision.** Two boto3 clients, not one: `_public_client()` (configured
with the host a browser can actually reach) signs every presigned URL;
`_internal_client()` (configured with the Docker-network hostname) makes
every real server-to-S3 call, like `head_object`. Each request goes to
the host it was actually built for.

**Cost.** Two client objects and two endpoint settings
(`S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL`) to keep straight instead of
one -- a real cost in a small codebase, worth it because the failure
mode of getting it wrong (`SignatureDoesNotMatch` on every single
upload) is opaque enough that it's worth never encountering by
construction rather than debugging later.
