"""
GPP Plataform 2.0 — Ações PNGI URLs

Rotas registradas:
  /acoes/                        → AcaoViewSet (CRUD)
  /acoes/{acao_pk}/prazos/       → AcaoPrazoViewSet (nested)
  /acoes/{acao_pk}/destaques/    → AcaoDestaqueViewSet (nested)
  /acoes/{acao_pk}/anotacoes/    → AcaoAnotacaoViewSet (nested)
  /eixos/                        → EixoViewSet (read-only)
  /situacoes/                    → SituacaoAcaoViewSet (read-only)
  /vigencias/                    → VigenciaPNGIViewSet (CRUD)
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers

from .views import (
    AcaoAnotacaoViewSet,
    AcaoDestaqueViewSet,
    AcaoPrazoViewSet,
    AcaoViewSet,
    EixoViewSet,
    SituacaoAcaoViewSet,
    VigenciaPNGIViewSet,
)

app_name = "acoes_pngi"

# Router principal
router = DefaultRouter()
router.register(r"acoes",     AcaoViewSet,         basename="acao")
router.register(r"eixos",     EixoViewSet,         basename="eixo")
router.register(r"situacoes", SituacaoAcaoViewSet, basename="situacao")
router.register(r"vigencias", VigenciaPNGIViewSet, basename="vigencia")

# Routers nested sob /acoes/{acao_pk}/
acoes_router = nested_routers.NestedDefaultRouter(router, r"acoes", lookup="acao")
acoes_router.register(r"prazos",    AcaoPrazoViewSet,   basename="acao-prazo")
acoes_router.register(r"destaques", AcaoDestaqueViewSet, basename="acao-destaque")
acoes_router.register(r"anotacoes", AcaoAnotacaoViewSet, basename="acao-anotacao")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(acoes_router.urls)),
]
