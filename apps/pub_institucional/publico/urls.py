"""URLs públicas, independentes do router administrativo."""

from django.urls import path

from .visoes import (VisaoDetalhePublicacaoPublica, VisaoHistoricoPublico,
                     VisaoPublicacaoVigente, VisaoSeriesPublicacaoPublica)

app_name = "publicacoes_publicas"

urlpatterns = [
    path("vigente/", VisaoPublicacaoVigente.as_view(), name="vigente"),
    path("", VisaoHistoricoPublico.as_view(), name="historico"),
    path(
        "<uuid:publicacao_id>/series/",
        VisaoSeriesPublicacaoPublica.as_view(),
        name="series",
    ),
    path(
        "<uuid:publicacao_id>/",
        VisaoDetalhePublicacaoPublica.as_view(),
        name="detalhe",
    ),
]
