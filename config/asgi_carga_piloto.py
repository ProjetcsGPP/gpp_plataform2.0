"""ASGI de Carga para o ensaio local opt-in."""

import os
from importlib import import_module

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

from .websocket_piloto import RejeitarRotaWebSocketDesconhecida

perfil = os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.carga_piloto")
if perfil != "config.settings.carga_piloto":
    raise RuntimeError(
        "ASGI de Carga exige DJANGO_SETTINGS_MODULE=config.settings.carga_piloto"
    )
django_asgi_application = get_asgi_application()

middleware = getattr(
    import_module("apps.core.middleware.websocket"),
    "MiddlewareSessaoAplicacaoWebSocket",
)
rotas_carga = getattr(
    import_module("apps.carga_org_lot.routing"),
    "websocket_urlpatterns",
)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": middleware(
            URLRouter(
                [
                    *rotas_carga,
                    re_path(
                        r"^.*$",
                        RejeitarRotaWebSocketDesconhecida.as_asgi(),
                    ),
                ]
            ),
            contextos_por_prefixo={"ws/carga-org-lot/": "CARGA_ORG_LOT"},
        ),
    }
)
