"""ASGI de IAM, Portal e Ações no ensaio local opt-in."""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

from .websocket_piloto import RejeitarRotaWebSocketDesconhecida

perfil = os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "config.settings.plataforma_separada_piloto"
)
if perfil != "config.settings.plataforma_separada_piloto":
    raise RuntimeError(
        "ASGI de plataforma separada exige DJANGO_SETTINGS_MODULE="
        "config.settings.plataforma_separada_piloto"
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
