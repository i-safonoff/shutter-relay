from django.urls import path

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("albums/", views.create_album, name="create_album"),
    path("albums/<slug:slug>/", views.album_page, name="album_page"),
    path("albums/<slug:slug>/photos/", views.list_photos, name="list_photos"),
    path("albums/<slug:slug>/uploads/", views.request_upload, name="request_upload"),
    path("photos/<uuid:photo_id>/confirm/", views.confirm_upload, name="confirm_upload"),
]
