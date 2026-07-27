from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/albums/(?P<slug>[-\w]+)/$", consumers.AlbumConsumer.as_asgi()),
]
