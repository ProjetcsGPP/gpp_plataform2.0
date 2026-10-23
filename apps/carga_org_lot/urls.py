"""Rotas da aplicação de carga de organograma e lotação."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AlternativaResolucaoValidacaoViewSet,
    CasoValidacaoImportacaoViewSet,
    CargoReferenciaGlobalViewSet,
    ConjuntoLotacaoViewSet,
    CargaOrgLotViewSet,
    DashboardCargaOrgLotView,
    DashboardPublicoCargaOrgLotView,
    EnvioOrganogramaProdestViewSet,
    EventoIntegracaoProdestViewSet,
    HistoricoCargaViewSet,
    ImportacaoPlanilhaViewSet,
    ItemLotacaoViewSet,
    ItemLotacaoImportadoViewSet,
    ItemOrganogramaViewSet,
    MapeamentoCargoPatriarcaViewSet,
    OcorrenciaCargoImportacaoViewSet,
    PatriarcaViewSet,
    ProcessoCargaInicialViewSet,
    ResolucaoValidacaoViewSet,
    StatusCargaViewSet,
    StatusProgressoViewSet,
    TipoCargaViewSet,
    VariacaoCargoGlobalViewSet,
)

app_name = "carga_org_lot"

router = DefaultRouter()
router.register(r"patriarcas", PatriarcaViewSet, basename="patriarca")
router.register(
    r"processos-carga-inicial",
    ProcessoCargaInicialViewSet,
    basename="processo-carga-inicial",
)
router.register(r"status-carga", StatusCargaViewSet, basename="status-carga")
router.register(
    r"status-progresso", StatusProgressoViewSet, basename="status-progresso"
)
router.register(r"tipos-carga", TipoCargaViewSet, basename="tipo-carga")
router.register(
    r"cargos-referencia",
    CargoReferenciaGlobalViewSet,
    basename="cargo-referencia",
)
router.register(
    r"variacoes-cargo",
    VariacaoCargoGlobalViewSet,
    basename="variacao-cargo",
)
router.register(
    r"ocorrencias-cargo",
    OcorrenciaCargoImportacaoViewSet,
    basename="ocorrencia-cargo",
)
router.register(
    r"mapeamentos-cargo-patriarca",
    MapeamentoCargoPatriarcaViewSet,
    basename="mapeamento-cargo-patriarca",
)
router.register(r"importacoes", ImportacaoPlanilhaViewSet, basename="importacao")
router.register(
    r"conjuntos-lotacao",
    ConjuntoLotacaoViewSet,
    basename="conjunto-lotacao",
)
router.register(
    r"itens-organograma",
    ItemOrganogramaViewSet,
    basename="item-organograma",
)
router.register(
    r"itens-lotacao",
    ItemLotacaoViewSet,
    basename="item-lotacao",
)
router.register(
    r"itens-lotacao-importados",
    ItemLotacaoImportadoViewSet,
    basename="item-lotacao-importado",
)
router.register(
    r"casos-validacao-importacao",
    CasoValidacaoImportacaoViewSet,
    basename="caso-validacao-importacao",
)
router.register(
    r"alternativas-resolucao-validacao",
    AlternativaResolucaoValidacaoViewSet,
    basename="alternativa-resolucao-validacao",
)
router.register(
    r"resolucoes-validacao",
    ResolucaoValidacaoViewSet,
    basename="resolucao-validacao",
)
router.register(r"cargas", CargaOrgLotViewSet, basename="carga")
router.register(
    r"envios-organograma-prodest",
    EnvioOrganogramaProdestViewSet,
    basename="envio-organograma-prodest",
)
router.register(
    r"eventos-integracao-prodest",
    EventoIntegracaoProdestViewSet,
    basename="evento-integracao-prodest",
)
router.register(
    r"historico-cargas", HistoricoCargaViewSet, basename="historico-carga"
)

urlpatterns = [
    path("dashboard/", DashboardCargaOrgLotView.as_view(), name="dashboard"),
    path(
        "dashboard-publico/",
        DashboardPublicoCargaOrgLotView.as_view(),
        name="dashboard-publico",
    ),
    path("", include(router.urls)),
]
