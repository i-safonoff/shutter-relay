"""Unit-speed tests for confirm_upload's two guarantees: no S3 object,
no confirmation; broadcast failure, still a confirmation. Both mock the
one collaborator each is not testing, so neither needs the docker stack
-- the live version of this same flow, against a real bucket and a real
channel layer, is in test_live_flow.py.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from django.test import Client

from apps.gallery.models import Album, Photo


@pytest.fixture
def photo(db):
    album = Album.objects.create(slug="test-album", name="Test Album")
    return Photo.objects.create(album=album, content_type="image/png")


@pytest.mark.django_db
def test_confirming_a_photo_never_uploaded_is_rejected(photo):
    with patch("apps.gallery.views.storage.object_exists", return_value=False):
        response = Client().post(f"/photos/{photo.id}/confirm/")
    assert response.status_code == 409
    photo.refresh_from_db()
    assert photo.status == Photo.Status.PENDING


@pytest.mark.django_db
def test_confirming_a_missing_photo_id_is_a_404():
    response = Client().post(f"/photos/{uuid.uuid4()}/confirm/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_a_broadcast_failure_does_not_undo_a_real_confirmation(photo):
    """The regression test for the bug found by actually stopping Redis:
    channel_layer.group_send raising left a photo CONFIRMED in Postgres
    while the client got a bare 500 -- the write had succeeded and the
    response claimed total failure. group_send is mocked to raise here
    specifically so this stays a fast, deterministic test rather than one
    that has to stop a real Redis container to prove the same point.
    """
    with (
        patch("apps.gallery.views.storage.object_exists", return_value=True),
        patch("apps.gallery.views.get_channel_layer") as mock_layer,
    ):
        # group_send is awaited via async_to_sync in the view, which
        # requires an actual coroutine function -- a plain MagicMock
        # fails with "can't be used in 'await' expression" before the
        # ConnectionError it's meant to simulate ever gets the chance to.
        mock_layer.return_value.group_send = AsyncMock(side_effect=ConnectionError("redis is down"))
        response = Client().post(f"/photos/{photo.id}/confirm/")

    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["id"] == str(photo.id)
    photo.refresh_from_db()
    assert photo.status == Photo.Status.CONFIRMED
