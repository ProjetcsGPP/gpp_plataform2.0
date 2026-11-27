"""ASGI IAM/Portal do piloto de quatro processos, sem WebSocket de domínio."""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

from .websocket_piloto import RejeitarRotaWebSocketDesconhecida


perfil = os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "config.settings.plataforma_quatro_piloto"
)
if perfil != "config.settings.plataforma_quatro_piloto":
    raise RuntimeError(
        "ASGI da plataforma de quatro processos exige "
        "DJANGO_SETTINGS_MODULE=config.settings.plataforma_quatro_piloto"
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
