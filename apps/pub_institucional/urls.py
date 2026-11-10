"""Rotas administrativas de Publicações Institucionais."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.pub_institucional.visoes import (
    VisaoColetaEflow, VisaoColetaMensalEdocs, VisaoColetaPatriarcasEdocs,
    VisaoDefinicaoFluxoEflow, VisaoDivergenciaPatriarcaEdocs,
    VisaoEventoAuditoriaColetaMensalEdocs, VisaoEventoAuditoriaEflow,
    VisaoEventoAuditoriaPatriarcaEdocs, VisaoEventoAuditoriaPreferenciaEflow,
    VisaoFonteBrutaColetaMensalEdocs, VisaoPatriarcaEdocs,
    VisaoPreferenciaExibicaoEflow, VisaoResultadoCalculoEflow,
    VisaoResultadoMensalOrganizacaoEdocs, VisaoResultadoMensalPatriarcaEdocs)

app_name = "pub_institucional"

roteador = DefaultRouter()
roteador.register(r"patriarcas", VisaoPatriarcaEdocs, basename="patriarca-edocs")
roteador.register(r"coletas", VisaoColetaPatriarcasEdocs, basename="coleta-edocs")
roteador.register(
    r"coletas-mensais-edocs",
    VisaoColetaMensalEdocs,
    basename="coleta-mensal-edocs",
)
roteador.register(
    r"resultados-mensais-patriarcas-edocs",
    VisaoResultadoMensalPatriarcaEdocs,
    basename="resultado-mensal-patriarca-edocs",
)
roteador.register(
    r"resultados-mensais-organizacoes-edocs",
    VisaoResultadoMensalOrganizacaoEdocs,
    basename="resultado-mensal-organizacao-edocs",
)
roteador.register(
    r"fontes-brutas-coletas-mensais-edocs",
    VisaoFonteBrutaColetaMensalEdocs,
    basename="fonte-bruta-coleta-mensal-edocs",
)
roteador.register(
    r"auditoria-coletas-mensais-edocs",
    VisaoEventoAuditoriaColetaMensalEdocs,
    basename="auditoria-coleta-mensal-edocs",
)
roteador.register(
    r"coletas-eflow",
    VisaoColetaEflow,
    basename="coleta-eflow",
)
roteador.register(
    r"definicoes-eflow",
    VisaoDefinicaoFluxoEflow,
    basename="definicao-eflow",
)
roteador.register(
    r"resultados-eflow",
    VisaoResultadoCalculoEflow,
    basename="resultado-eflow",
)
roteador.register(
    r"preferencias-eflow",
    VisaoPreferenciaExibicaoEflow,
    basename="preferencia-eflow",
)
roteador.register(
    r"auditoria-preferencias-eflow",
    VisaoEventoAuditoriaPreferenciaEflow,
    basename="auditoria-preferencia-eflow",
)
roteador.register(
    r"auditoria-eflow",
    VisaoEventoAuditoriaEflow,
    basename="auditoria-eflow",
)
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
