"""ASGI config for GPP Plataform 2.0."""

import os
from importlib import import_module

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django_asgi_application = get_asgi_application()


def _construir_aplicacao():
    """Carrega rotas que dependem do registro Django já inicializado."""

    classe_middleware = getattr(
        import_module("apps.core.middleware.websocket"),
        "MiddlewareSessaoAplicacaoWebSocket",
    )
    padroes_carga = getattr(
        import_module("apps.carga_org_lot.routing"),
        "websocket_urlpatterns",
    )
    padroes_publicacoes = getattr(
        import_module("apps.pub_institucional.rotas"),
        "websocket_urlpatterns",
    )

    return ProtocolTypeRouter(
        {
            "http": django_asgi_application,
            "websocket": classe_middleware(
                URLRouter([*padroes_carga, *padroes_publicacoes]),
                contextos_por_prefixo={
                    "ws/carga-org-lot/": "CARGA_ORG_LOT",
                    "ws/pub-institucional/": "PUB_INSTITUCIONAL",
                },
            ),
        }
    )


application = _construir_aplicacao()
