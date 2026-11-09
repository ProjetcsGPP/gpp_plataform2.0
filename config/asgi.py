"""ASGI config for GPP Plataform 2.0."""
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django_asgi_application = get_asgi_application()

from apps.core.middleware.websocket import (  # noqa: E402
    MiddlewareSessaoAplicacaoWebSocket,
)
from apps.carga_org_lot.routing import (  # noqa: E402
    websocket_urlpatterns as padroes_carga,
)
from apps.pub_institucional.rotas import (  # noqa: E402
    websocket_urlpatterns as padroes_publicacoes,
)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": MiddlewareSessaoAplicacaoWebSocket(
            URLRouter([*padroes_carga, *padroes_publicacoes]),
            contextos_por_prefixo={
                "ws/carga-org-lot/": "CARGA_ORG_LOT",
                "ws/pub-institucional/": "PUB_INSTITUCIONAL",
            },
        ),
    }
)
