"""Talks to S3 (MinIO locally): a presigned PUT the browser uses directly,
a HEAD check the server uses to confirm the browser actually used it and
to read the size S3 actually recorded, and a DELETE for the one case
that check exists to catch. Django's own request/response cycle never
sees a photo's bytes.
"""

from __future__ import annotations

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings


def _client(endpoint_url: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name="us-east-1",
        # MinIO doesn't do virtual-hosted-style buckets
        # (bucket.host.tld/key) by default -- it needs the bucket in the
        # path (host.tld/bucket/key), which is also what nginx/Traefik in
        # front of MinIO expects to route on. Auto-style guesses wrong for
        # a non-AWS endpoint and every request 404s against a host that
        # doesn't exist.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


# Two clients, not one, because SigV4 signs the Host header into the
# request -- a presigned URL is only valid against the exact host it was
# signed for. Inside Docker Compose, Django reaches MinIO as `minio:9000`;
# a browser on the host has never heard of that name. Signing with the
# public client and only ever calling head_object with the internal one
# keeps both requests valid on the host they're actually sent to, instead
# of rewriting a URL's host after the fact and invalidating its own
# signature.
def _internal_client():
    return _client(settings.AWS_S3_ENDPOINT_URL)


def _public_client():
    return _client(settings.AWS_S3_PUBLIC_ENDPOINT_URL)


def presigned_put_url(key: str, content_type: str, *, expires_in: int = 300) -> str:
    return _public_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )


def object_size(key: str) -> int | None:
    """None if the object was never uploaded. A size, in bytes, straight
    from S3's own record of what actually landed -- not from whatever
    Content-Length header the client's PUT happened to send, which is
    exactly the number a client controls and this function is not
    interested in trusting.
    """
    try:
        response = _internal_client().head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)
        return response["ContentLength"]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            return None
        raise


def delete_object(key: str) -> None:
    _internal_client().delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)


def ensure_bucket() -> None:
    # No put_bucket_cors call here -- there was one, and it never once
    # worked. Two independent clients (boto3 directly, and MinIO's own
    # `mc cors set`) both got "NotImplemented: A header you provided
    # implies functionality that is not implemented" against this MinIO
    # release, which ruled out a boto3-specific cause (a mandatory
    # x-amz-checksum-crc32 header the newer botocore attaches to this one
    # API, confirmed with request logging) in favour of a simpler
    # explanation: `curl -X OPTIONS` against a bucket with *no* CORS
    # policy set at all already gets a correct preflight response --
    # Origin, method and headers all echoed back, 204. MinIO answers CORS
    # for every bucket unconditionally and PutBucketCors is effectively
    # vestigial here. A real AWS S3 bucket does not do this -- it stays
    # closed to cross-origin requests until a CORS policy is set
    # explicitly -- so this is a MinIO-local simplification, not a
    # property to assume in front of real S3. See docs/DECISIONS.md.
    client = _internal_client()
    try:
        client.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
    except ClientError:
        client.create_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
