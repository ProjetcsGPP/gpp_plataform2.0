"""
GPP Plataform 2.0 — URL Router Principal
Cada app registra suas próprias URLs.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import GPPTokenObtainPairView, TokenRevokeView

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # ── Auth ────────────────────────────────────────────────────────────────
    path("api/auth/token/", GPPTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/token/revoke/", TokenRevokeView.as_view(), name="token_revoke"),

    # ── Apps ─────────────────────────────────────────────────────────────────
    path("api/accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("api/portal/", include("apps.portal.urls", namespace="portal")),
    path("api/acoes-pngi/", include("apps.acoes_pngi.urls", namespace="acoes_pngi")),
    path("api/carga-org-lot/", include("apps.carga_org_lot.urls", namespace="carga_org_lot")),

    # ── Health check ─────────────────────────────────────────────────────────
    path("api/health/", include("common.urls")),
]

# ── Debug Toolbar (apenas em desenvolvimento) ─────────────────────────────────
if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns