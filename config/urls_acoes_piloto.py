"""Superfície HTTP exclusiva de Ações PNGI no piloto opt-in."""

from django.urls import include, path

from common.health import prontidao_acoes

from .health_piloto import acoes_vivas


urlpatterns = [
    path("api/acoes-pngi/", include("apps.acoes_pngi.urls", namespace="acoes_pngi")),
    path("api/health/", acoes_vivas, name="acoes-vivas"),
    path("api/ready/", prontidao_acoes, name="acoes-prontas"),
]
