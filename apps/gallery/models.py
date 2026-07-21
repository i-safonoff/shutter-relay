"""Two tables. An album groups photos; a photo exists in two states
before it is ever visible to anyone but its uploader."""

import secrets
import uuid

from django.db import models


class Album(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


def _object_key() -> str:
    # Random, not derived from the filename -- a filename is client input,
    # and an object key that echoes it is a path-traversal and collision
    # surface for no benefit; nothing here ever needs to reconstruct the
    # original name from the key.
    return f"{secrets.token_hex(16)}"


class Photo(models.Model):
    class Status(models.TextChoices):
        # A row exists the moment a client asks for an upload URL, before
        # any bytes have gone anywhere -- PENDING is "reserved", not
        # "broken". CONFIRMED is the only state anyone but the uploader
        # ever sees, and the only one that ever reaches a WebSocket.
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    album = models.ForeignKey(Album, related_name="photos", on_delete=models.CASCADE)
    object_key = models.CharField(max_length=64, unique=True, default=_object_key)
    content_type = models.CharField(max_length=100)
    uploader = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-confirmed_at"]

    def s3_key(self) -> str:
        return f"{self.album.slug}/{self.object_key}"
