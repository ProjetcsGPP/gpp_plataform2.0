"""Rotas da aplicação de carga de organograma e lotação."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CargaOrgLotViewSet,
    HistoricoCargaViewSet,
    ImportacaoPlanilhaViewSet,
    ItemOrganogramaViewSet,
    PatriarcaViewSet,
    StatusCargaViewSet,
    StatusProgressoViewSet,
    TipoCargaViewSet,
)

app_name = "carga_org_lot"

router = DefaultRouter()
router.register(r"patriarcas", PatriarcaViewSet, basename="patriarca")
router.register(r"status-carga", StatusCargaViewSet, basename="status-carga")
router.register(
    r"status-progresso", StatusProgressoViewSet, basename="status-progresso"
)
router.register(r"tipos-carga", TipoCargaViewSet, basename="tipo-carga")
router.register(r"importacoes", ImportacaoPlanilhaViewSet, basename="importacao")
router.register(
    r"itens-organograma",
    ItemOrganogramaViewSet,
    basename="item-organograma",
)
router.register(r"cargas", CargaOrgLotViewSet, basename="carga")
router.register(
    r"historico-cargas", HistoricoCargaViewSet, basename="historico-carga"
)

urlpatterns = [path("", include(router.urls))]
