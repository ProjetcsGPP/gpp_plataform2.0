"""Superfície HTTP exclusiva da Carga no ensaio de isolamento local."""

from django.urls import include, path

from .health_piloto import carga_viva

urlpatterns = [
    path("api/carga-org-lot/", include("apps.carga_org_lot.urls", namespace="carga_org_lot")),
    path("api/health/", carga_viva, name="carga-viva"),
]
