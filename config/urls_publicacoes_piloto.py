"""Superfície HTTP exclusiva de Publicações no ensaio de três processos."""

from django.urls import include, path

from common.health import prontidao_publicacoes

from .health_piloto import publicacoes_vivas

urlpatterns = [
    path(
        "api/pub-institucional/",
        include("apps.pub_institucional.urls", namespace="pub_institucional"),
    ),
    path(
        "api/public/v1/publicacoes-institucionais/",
        include("apps.pub_institucional.publico.urls", namespace="publicacoes_publicas"),
    ),
    path("api/health/", publicacoes_vivas, name="publicacoes-vivas"),
    path("api/ready/", prontidao_publicacoes, name="publicacoes-prontas"),
]
