"""Unit-speed tests for confirm_upload's core guarantee: no verified S3
object, no confirmation. Mocks storage so neither test needs the docker
stack -- the live version of the same flow, against a real bucket, is in
test_live_flow.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

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
