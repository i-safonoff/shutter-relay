"""Against the real stack: a real presigned PUT to real MinIO, a real
Redis channel layer, a real WebSocket consumer. `make up` first.
"""

from __future__ import annotations

import base64

import httpx
import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import Client

from apps.gallery.models import Album, Photo
from relay.asgi import application

pytestmark = pytest.mark.live

# A real, valid 1x1 red PNG -- MinIO and imgproxy both parse actual image
# bytes, and a fixture that's just b"fake png data" would sail through
# the S3 upload and then only fail inside imgproxy, far from the test
# that's supposed to explain why.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def album(db):
    return Album.objects.create(slug="live-test-album", name="Live Test Album")


@pytest.mark.django_db(transaction=True)
async def test_a_confirmed_upload_is_broadcast_to_a_connected_viewer(album):
    communicator = WebsocketCommunicator(application, f"/ws/albums/{album.slug}/")
    connected, _ = await communicator.connect()
    assert connected

    client = Client()

    def request_and_upload():
        resp = client.post(
            f"/albums/{album.slug}/uploads/",
            data='{"content_type": "image/png", "uploader": "async-test"}',
            content_type="application/json",
        )
        body = resp.json()
        put = httpx.put(body["upload_url"], content=PNG_1X1, headers={"Content-Type": "image/png"})
        assert put.status_code == 200
        return body["photo_id"]

    photo_id = await sync_to_async(request_and_upload)()

    confirm = await sync_to_async(client.post)(f"/photos/{photo_id}/confirm/")
    assert confirm.status_code == 200

    message = await communicator.receive_json_from(timeout=5)
    assert message["type"] == "photo_added"
    assert message["photo"]["id"] == photo_id
    assert "thumb" in message["photo"]["urls"]

    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_a_second_album_never_hears_the_first_albums_broadcast(album):
    other = await sync_to_async(Album.objects.create)(slug="other-live-album", name="Other")

    mine = WebsocketCommunicator(application, f"/ws/albums/{album.slug}/")
    theirs = WebsocketCommunicator(application, f"/ws/albums/{other.slug}/")
    await mine.connect()
    await theirs.connect()

    client = Client()

    def request_and_upload():
        resp = client.post(
            f"/albums/{album.slug}/uploads/",
            data='{"content_type": "image/png"}',
            content_type="application/json",
        )
        body = resp.json()
        httpx.put(body["upload_url"], content=PNG_1X1, headers={"Content-Type": "image/png"})
        return body["photo_id"]

    photo_id = await sync_to_async(request_and_upload)()
    await sync_to_async(client.post)(f"/photos/{photo_id}/confirm/")

    message = await mine.receive_json_from(timeout=5)
    assert message["photo"]["id"] == photo_id

    assert await theirs.receive_nothing(timeout=1)

    await mine.disconnect()
    await theirs.disconnect()


@pytest.mark.django_db
def test_confirming_a_photo_that_was_never_actually_put_to_s3_is_rejected(album):
    resp = Client().post(
        f"/albums/{album.slug}/uploads/",
        data='{"content_type": "image/png"}',
        content_type="application/json",
    )
    photo_id = resp.json()["photo_id"]
    # No PUT happened -- the presigned URL was requested and never used.
    confirm = Client().post(f"/photos/{photo_id}/confirm/")
    assert confirm.status_code == 409
    assert Photo.objects.get(id=photo_id).status == Photo.Status.PENDING
