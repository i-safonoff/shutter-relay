"""ASGI config. `get_asgi_application()` must be called before anything
in `apps.gallery` is imported -- it populates Django's app registry, and
`routing.py` imports a consumer that imports a model, which raises
`AppRegistryNotReady` if that happens first. ProtocolTypeRouter is what
actually makes this one process serve plain HTTP and WebSocket upgrades
on the same port without two servers.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "relay.settings")

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from apps.gallery.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
