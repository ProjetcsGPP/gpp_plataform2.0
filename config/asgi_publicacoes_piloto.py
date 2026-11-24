"""ASGI exclusivo de Publicações para o ensaio local opt-in."""

import os
from importlib import import_module

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

from .websocket_piloto import RejeitarRotaWebSocketDesconhecida

perfil = os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "config.settings.publicacoes_piloto"
)
if perfil != "config.settings.publicacoes_piloto":
    raise RuntimeError(
        "ASGI de Publicações exige DJANGO_SETTINGS_MODULE="
        "config.settings.publicacoes_piloto"
    )
django_asgi_application = get_asgi_application()

middleware = getattr(
    import_module("apps.core.middleware.websocket"),
    "MiddlewareSessaoAplicacaoWebSocket",
)
rotas_publicacoes = getattr(
    import_module("apps.pub_institucional.rotas"),
    "websocket_urlpatterns",
)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": middleware(
            URLRouter([
                *rotas_publicacoes,
                re_path(r"^.*$", RejeitarRotaWebSocketDesconhecida.as_asgi()),
            ]),
            contextos_por_prefixo={"ws/pub-institucional/": "PUB_INSTITUCIONAL"},
        ),
    }
)
