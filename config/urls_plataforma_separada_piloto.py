"""IAM, Portal e Ações sem Carga nem Publicações no ensaio opt-in."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.accounts.views_internas import (
    DecisaoAtividadeIAMInternaView,
    DecisaoAtividadePublicacoesIAMInternaView,
    DecisaoIAMInternaView,
    DecisaoPublicacoesIAMInternaView,
)

from .health_piloto import plataforma_viva

urlpatterns = [
    path(
        "interno/iam/v1/decisoes-atividade-publicacoes/",
        DecisaoAtividadePublicacoesIAMInternaView.as_view(),
        name="iam-decisao-atividade-publicacoes-interna-v1",
    ),
    path(
        "interno/iam/v1/decisoes-publicacoes/",
        DecisaoPublicacoesIAMInternaView.as_view(),
        name="iam-decisao-publicacoes-interna-v1",
    ),
    path(
        "interno/iam/v1/decisoes-atividade/",
        DecisaoAtividadeIAMInternaView.as_view(),
        name="iam-decisao-atividade-interna-v1",
    ),
    path(
        "interno/iam/v1/decisoes/",
        DecisaoIAMInternaView.as_view(),
        name="iam-decisao-interna-v1",
    ),
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("api/portal/", include("apps.portal.urls", namespace="portal")),
    path("api/acoes-pngi/", include("apps.acoes_pngi.urls", namespace="acoes_pngi")),
    path("api/", include("apps.core.urls", namespace="core")),
    path("api/health/", plataforma_viva, name="plataforma-viva"),
]

if settings.DEBUG:
    import debug_toolbar  # pylint: disable=import-outside-toplevel

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ] + urlpatterns
