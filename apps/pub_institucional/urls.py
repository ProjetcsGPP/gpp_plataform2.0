"""Rotas administrativas de Publicações Institucionais."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.pub_institucional.visoes import (
    VisaoColetaPatriarcasEdocs,
    VisaoDivergenciaPatriarcaEdocs,
    VisaoEventoAuditoriaPatriarcaEdocs,
    VisaoPatriarcaEdocs,
)

app_name = "pub_institucional"

roteador = DefaultRouter()
roteador.register(r"patriarcas", VisaoPatriarcaEdocs, basename="patriarca-edocs")
roteador.register(r"coletas", VisaoColetaPatriarcasEdocs, basename="coleta-edocs")
roteador.register(
    r"divergencias",
    VisaoDivergenciaPatriarcaEdocs,
    basename="divergencia-edocs",
)
roteador.register(
    r"auditoria",
    VisaoEventoAuditoriaPatriarcaEdocs,
    basename="auditoria-edocs",
)

urlpatterns = [path("", include(roteador.urls))]
