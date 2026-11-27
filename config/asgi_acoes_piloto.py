"""ASGI de Ações PNGI sem rotas WebSocket ou de outras aplicações."""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

from .websocket_piloto import RejeitarRotaWebSocketDesconhecida


perfil = os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.acoes_piloto")
if perfil != "config.settings.acoes_piloto":
    raise RuntimeError(
        "ASGI de Ações exige DJANGO_SETTINGS_MODULE=config.settings.acoes_piloto"
    )
django_asgi_application = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": URLRouter([
            re_path(r"^.*$", RejeitarRotaWebSocketDesconhecida.as_asgi()),
        ]),
    }
)
