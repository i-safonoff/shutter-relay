# shutter-relay

**Upload a photo, and everyone else looking at the album sees it appear —
no refresh, no polling. Uploads go straight to S3, thumbnails are never
stored, and the live update only ever fires after the write it describes
is actually verified.**

[![CI](https://github.com/i-safonoff/shutter-relay/actions/workflows/ci.yml/badge.svg)](https://github.com/i-safonoff/shutter-relay/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Django](https://img.shields.io/badge/django-6.1-0C4B33)
![Channels](https://img.shields.io/badge/channels-daphne-44B78B)
![S3](https://img.shields.io/badge/storage-s3%20%2F%20minio-C8102E)
![imgproxy](https://img.shields.io/badge/images-imgproxy-FF6600)
![Tests](https://img.shields.io/badge/tests-12%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Contents

- [Why I built this](#why-i-built-this)
- [What it does](#what-it-does)
- [The problems this project is actually about](#the-problems-this-project-is-actually-about)
- [The branches](#the-branches)
- [Quickstart](#quickstart)
- [Testing it](#testing-it)
- [Project layout](#project-layout)
- [What I would do differently at scale](#what-i-would-do-differently-at-scale)

## Why I built this

[`websocket-presence-board`](https://github.com/i-safonoff/websocket-presence-board)
answered "how do you keep a socket open" by building every piece of the
answer by hand on FastAPI. This project asks a narrower, different
question: what does a framework that *already* answers that question
give you, and what does it quietly not? Django Channels turns "one group
per album, broadcast on upload" into a few dozen lines instead of a
hand-rolled Redis bridge — and the first time this project actually
killed its Redis container to see what happened, Channels' answer was a
bare, uncaught `ConnectionError` turning a *successful* database write
into a client-visible 500. Getting the free version required finding,
and fixing, the exact failure mode the hand-built version in the other
project was designed around from day one.

The rest of the project is a second, independent question: what happens
to a file once "upload" stops meaning "send it to my server." Presigned
S3 URLs mean Django's own process never touches a photo's bytes, and
imgproxy means no resized copy of one is ever stored — every thumbnail
is generated from the original, on request, on the fly.

Five things I wanted to be able to explain afterwards, and now can:

- Why a presigned URL that works from the app container 403s from a
  browser, and why swapping the hostname in the URL doesn't fix it.
- What actually happens when the thing your WebSocket broadcast depends
  on goes down mid-request — not what the docs say happens.
- Why MinIO doesn't need the CORS configuration every S3 tutorial tells
  you to set.
- What Django Channels gives you for free that a hand-built ASGI service
  doesn't, and what it costs to get it.
- Why an event should only ever go out after a write is verified, never
  after a client merely claims it happened.

## What it does

```
 browser ──PUT (direct)──► MinIO (S3) ◄──HEAD, resize──┐
    │                                                   │
    ├──POST /uploads/──► Django ──confirm──► Postgres   │
    │                       │                            imgproxy
    └───────ws://──────► Daphne ──group_send──► Redis ──► every
                        (Channels)                        connected
                                                            viewer
```

One Postgres table for who-uploaded-what, one Redis channel layer for
who's-watching-what, S3 for the bytes, imgproxy for every size anyone
ever sees. nginx in front of a single Daphne instance for the
WebSocket upgrade.

## The problems this project is actually about

### 1. A presigned URL is signed for one host, not one bucket

Inside Docker Compose, Django reaches MinIO as `minio:9000`; a browser
on the host has never heard of that name. SigV4 signs the `Host` header
into the request, so the obvious fix — sign once, rewrite the URL's host
before handing it to the browser — doesn't work: rewriting it
invalidates the signature computed against the old one, and the PUT
comes back `SignatureDoesNotMatch`. Fixed with two boto3 clients, one
configured for each host, each only ever making the request it was
actually built for. [`apps/gallery/storage.py`](apps/gallery/storage.py).

### 2. An event only goes out after the write is verified, not claimed

`confirm_upload` calls `head_object` against S3 *before* touching the
database. A client that calls it without ever having PUT the file — or
whose PUT failed partway — gets a 409, not a WebSocket message pointing
every connected viewer at a thumbnail that 404s the moment they try to
load it. [`docs/DECISIONS.md`](docs/DECISIONS.md#2-an-event-only-goes-out-after-the-write-is-verified-not-claimed).

### 3. MinIO doesn't need the CORS policy every tutorial tells you to set

The first version of this project's bucket bootstrap called
`put_bucket_cors`, following the standard "a presigned PUT needs CORS"
advice — correct for real AWS S3, and it failed immediately against
MinIO, on both boto3 and MinIO's own `mc` CLI, with an identical
`NotImplemented` error. `curl -X OPTIONS` against the bucket with *no*
CORS policy ever set already returned a correct preflight response —
this MinIO release answers CORS unconditionally, and `PutBucketCors` is
vestigial here, though not on real S3.
[`docs/DECISIONS.md`](docs/DECISIONS.md#4-no-put_bucket_cors-call----minio-doesnt-need-one).

### 4. A confirmation shouldn't lie about the write it describes

Found by actually stopping the Redis container mid-request:
`channels_redis`' `group_send` raises a bare `ConnectionError`, uncaught
by anything Channels provides. The naive version let it propagate — a
Django 500, on a request whose photo was *already* CONFIRMED in
Postgres by the time the exception fired. Fixed on
[`fix/redis-broadcast-failure`](../../tree/fix/redis-broadcast-failure):
the broadcast is caught and logged, best-effort; the confirmation, which
had already succeeded, is what the response actually reports.
[`docs/DECISIONS.md`](docs/DECISIONS.md#3-the-broadcast-is-best-effort-the-confirmation-is-not).

### 5. What a framework's abstraction costs when it fails

Channels turned this project's entire pub/sub layer into a few dozen
lines — no hand-rolled Redis bridge, no reconnect protocol for the
bridge itself, all of it given away. The cost showed up exactly once,
and exactly where problem 4 lives: the framework hid the decision of
"what happens when the pub/sub layer itself is unavailable" instead of
making it, which is a decision `websocket-presence-board`'s hand-built
Redis bridge had to make explicitly from the start. Full comparison:
[`docs/vs-fastapi-websockets.md`](docs/vs-fastapi-websockets.md).

## The branches

| Branch | | |
|---|---|---|
| [`fix/redis-broadcast-failure`](../../tree/fix/redis-broadcast-failure) | merged | The bug found by actually killing Redis mid-request, and the regression test that doesn't need to kill it again |

One branch this time, not several — the rest of the build (models,
presigned uploads, the consumer, the confirm flow, the containerized
stack) is one continuous, tightly coupled feature with no seam worth
cutting artificially. The Redis failure mode was a genuinely separate,
later discovery with its own clear before/after, which is what earns it
a branch of its own.

## Quickstart

```bash
git clone https://github.com/i-safonoff/shutter-relay.git
cd shutter-relay
cp .env.example .env   # fill in IMGPROXY_KEY / IMGPROXY_SALT: openssl rand -hex 32, twice
make up
```

```bash
curl -X POST http://localhost:8020/albums/ \
  -H "Content-Type: application/json" -d '{"name": "Trip to Lisbon"}'
```

Open <http://localhost:8020/albums/trip-to-lisbon/>, upload a photo, and
open the same URL in a second tab to watch it appear there without a
refresh.

```bash
make down
```

To iterate on the app itself without rebuilding a container on every
change:

```bash
make infra                                    # just Postgres/Redis/MinIO/imgproxy
pip install -r requirements-dev.txt
python manage.py migrate && python manage.py bootstrap_storage
make dev                                      # daphne on :8010, autoreload via your editor
```

## Testing it

```bash
make test        # everything that needs no containers
make test-all     # including the live flow against the real stack
```

The live suite drives a real `WebsocketCommunicator` against the real
ASGI app, a real Redis channel layer, and a real presigned PUT to real
MinIO with actual PNG bytes — a placeholder like `b"fake png data"`
would sail through the S3 upload and only ever fail deep inside
imgproxy, nowhere near the test that's supposed to explain why. It
confirms three things no amount of mocking would: a connected viewer
gets the broadcast, a second album's viewer never does, and a confirm
called without ever having PUT the file is rejected before the database
or the channel layer hear about it.

## Project layout

```
apps/gallery/
├── models.py       Album, Photo, and a status a row is in before any bytes exist
├── storage.py       presigned PUT URLs, and the two-client fix for SigV4 + Docker networking
├── imgproxy.py       signed thumbnail/preview URLs, no resize ever stored
├── consumers.py       one WebSocket consumer, one group per album
├── views.py           create/list/request-upload/confirm -- confirm is where the guarantee lives
└── management/commands/bootstrap_storage.py   idempotent bucket setup

templates/gallery/album.html   the whole frontend: one socket, one upload flow, no framework
relay/asgi.py                   ProtocolTypeRouter -- one process serves HTTP and WS both
ops/nginx.conf                   the Upgrade header map every WebSocket proxy needs
ops/entrypoint.sh                 migrate, bootstrap the bucket, then exec daphne
docs/DECISIONS.md                  five decisions, each traceable to a real command that was run
docs/vs-fastapi-websockets.md       what Channels gives away for free, and what that costs
tests/                               12 tests, three of them against the real stack
```

## What I would do differently at scale

Honest limitations, not a roadmap:

- **No backpressure.** `AsyncWebsocketConsumer.send()` has the identical
  exposure `websocket-presence-board`'s raw uvicorn did — nothing bounds
  what happens if a viewer's connection stalls mid-broadcast, and
  Channels gives no primitive for it. The bounded-queue-and-evict design
  from that project's `feat/backpressure` branch would need rebuilding
  here, not reusing, because Channels doesn't expose the same hook.
- **No heartbeat, no resume.** Both missing for the same reason they're
  hard everywhere: the browser's `WebSocket` API can't send or observe
  ping/pong frames at all. Out of scope here on purpose — this project
  measured S3 and imgproxy, not connection liveness a second time after
  `websocket-presence-board` already did.
- **A missed broadcast has no retry.** A viewer connected at the exact
  moment Redis is down sees the photo on their next page load, not
  automatically. A per-connection catch-up mechanism is closer to that
  other project's `feat/resume-after-reconnect` than to anything this
  project's scope justified building twice.
- **File size is enforced; content is not.** `confirm_upload` rejects
  and deletes anything over `MAX_PHOTO_BYTES`, checked against what S3
  actually recorded rather than what the client's PUT claimed
  (`docs/DECISIONS.md`, decision 6) -- but nothing scans, re-encodes, or
  even confirms the bytes are a decodable image before a photo exists in
  the bucket. A real deployment needs a second-stage worker for that,
  not more logic in the request path. The size check also can't stop an
  oversized upload from actually transferring first -- a presigned PUT
  URL carries no size condition the way a presigned POST policy could,
  so rejection is still bandwidth spent, not bandwidth prevented.
- **One Daphne instance.** Multiple instances behind nginx, with the
  cross-instance fan-out story that requires, is exactly what
  `websocket-presence-board` already built and measured; repeating it
  here would test Channels' `RedisChannelLayer` under the same load
  rather than anything new.

## License

MIT — see [LICENSE](LICENSE).
