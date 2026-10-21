"""ASGI config for GPP Plataform 2.0."""
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django_asgi_application = get_asgi_application()

from apps.carga_org_lot.middleware import AppSessionWebSocketMiddleware  # noqa: E402
from apps.carga_org_lot.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AppSessionWebSocketMiddleware(
            URLRouter(websocket_urlpatterns)
        ),
    }
)
