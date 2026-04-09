"""
GPP Plataform 2.0 — URL Router Principal
Cada app registra suas próprias URLs.

FASE-0: paths JWT removidos (api/auth/token/, token/refresh/, token/revoke/).
        Autenticação agora via sessão — endpoint em api/accounts/login/.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # ── Apps ──────────────────────────────────────────────────────────────
    path("api/accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("api/portal/", include("apps.portal.urls", namespace="portal")),
    path("api/acoes-pngi/", include("apps.acoes_pngi.urls", namespace="acoes_pngi")),
    path("api/carga-org-lot/", include("apps.carga_org_lot.urls", namespace="carga_org_lot")),
    path("api/", include("apps.core.urls", namespace="core")),

    # ── Health check ─────────────────────────────────────────────────────
    path("api/health/", include("common.urls")),
]

# ── Debug Toolbar (apenas em desenvolvimento) ───────────────────────────────
if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns
