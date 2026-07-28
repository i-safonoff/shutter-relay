"""Four endpoints. The interesting one is confirm_upload: it is the only
place a photo becomes visible to anyone but the person who uploaded it,
and the only place a WebSocket group ever gets a message.
"""

from __future__ import annotations

import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import imgproxy, storage
from .models import Album, Photo


def _photo_payload(photo: Photo) -> dict:
    return {
        "id": str(photo.id),
        "uploader": photo.uploader,
        "confirmed_at": photo.confirmed_at.isoformat() if photo.confirmed_at else None,
        "urls": imgproxy.variants(photo.s3_key()),
    }


@require_GET
def healthz(request):
    return JsonResponse({"status": "ok"})


@csrf_exempt
@require_POST
def create_album(request):
    body = json.loads(request.body or "{}")
    name = body.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "name is required"}, status=422)
    slug = slugify(name)
    album, _ = Album.objects.get_or_create(slug=slug, defaults={"name": name})
    return JsonResponse({"slug": album.slug, "name": album.name}, status=201)


@require_GET
def album_page(request, slug: str):
    album = get_object_or_404(Album, slug=slug)
    return render(request, "gallery/album.html", {"album": album})


@require_GET
def list_photos(request, slug: str):
    album = get_object_or_404(Album, slug=slug)
    photos = album.photos.filter(status=Photo.Status.CONFIRMED)
    return JsonResponse({"photos": [_photo_payload(p) for p in photos]})


@csrf_exempt
@require_POST
def request_upload(request, slug: str):
    album = get_object_or_404(Album, slug=slug)
    body = json.loads(request.body or "{}")
    content_type = body.get("content_type", "application/octet-stream")
    uploader = body.get("uploader", "")[:100]

    photo = Photo.objects.create(album=album, content_type=content_type, uploader=uploader)
    upload_url = storage.presigned_put_url(photo.s3_key(), content_type)
    return JsonResponse({"photo_id": str(photo.id), "upload_url": upload_url}, status=201)


@csrf_exempt
@require_POST
def confirm_upload(request, photo_id: str):
    photo = get_object_or_404(Photo, id=photo_id)

    # The one rule this whole service exists to enforce: an event only
    # goes out after the write it describes is verified, not after the
    # client merely claims it happened. A client that calls this without
    # ever having PUT the file -- or whose PUT failed partway -- gets a
    # 409 here instead of every viewer's WebSocket getting a photo that
    # 404s when they try to load it.
    if not storage.object_exists(photo.s3_key()):
        return JsonResponse({"error": "object not found in storage"}, status=409)

    photo.status = Photo.Status.CONFIRMED
    photo.confirmed_at = timezone.now()
    photo.save(update_fields=["status", "confirmed_at"])
    payload = _photo_payload(photo)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"album_{photo.album.slug}",
        {"type": "photo_added", "photo": payload},
    )
    return JsonResponse(payload)
