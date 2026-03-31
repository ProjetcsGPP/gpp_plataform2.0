"""
GPP Plataform 2.0 — Accounts Middleware
FASE-0: AppContextMiddleware
FIX: /api/accounts/ aceita qualquer cookie gpp_session_* válido (multi-cookie)
"""

from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse

from .models import AccountsSession


class AppContextMiddleware:
    """
    Resolve qual sessão multi-cookie está ativa para a request atual.

    Regras:
      1. Prefixos de app com cookie dedicado (ACOES_PNGI, CARGA_ORG_LOT, PORTAL):
         exige exatamente o cookie  gpp_session_<APP>  para aquela rota.

      2. Prefixo 'accounts' (endpoints de gerenciamento transversais):
         aceita QUALQUER cookie gpp_session_* presente — itera e valida o
         primeiro AccountsSession ativo encontrado no banco.
         Isso permite que portal_admin (com gpp_session_PORTAL) acesse
         /api/accounts/roles/, /api/accounts/users/, /api/accounts/me/ etc.

      3. Path de logout por app (/api/accounts/logout/<slug>/):
         bypass total — AppContextMiddleware não bloqueia logout.
    """

    # Apps com cookie dedicado e rota própria
    APP_COOKIE_MAP = {
        "acoes-pngi":   "ACOES_PNGI",
        "carga-org-lot": "CARGA_ORG_LOT",
        "portal":       "PORTAL",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── 1. Logout por app — bypass total ──────────────────────────────────
        if getattr(request, "is_logout_request", False):
            return self.get_response(request)

        # ── 2. Resolve prefixo da URL ─────────────────────────────────────────
        path = request.path  # e.g. "/api/accounts/roles/"

        # Identifica o segundo segmento: /api/<prefix>/...
        try:
            segments = path.strip("/").split("/")
            prefix = segments[1] if segments[0] == "api" else None
        except IndexError:
            prefix = None

        # ── 3. Endpoints de app dedicada ──────────────────────────────────────
        if prefix in self.APP_COOKIE_MAP:
            app_context = self.APP_COOKIE_MAP[prefix]
            return self._authenticate_specific_cookie(request, app_context)

        # ── 4. Endpoints /api/accounts/ — aceita qualquer sessão ativa ────────
        if prefix == "accounts":
            return self._authenticate_any_cookie(request)

        # ── 5. Qualquer outro path (admin, static, etc.) — passa sem autenticar
        return self.get_response(request)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _authenticate_specific_cookie(self, request, app_context):
        """
        Autentica usando exclusivamente  gpp_session_<app_context>.
        Se ausente ou inválido → AnonymousUser / 401.
        """
        cookie_name = f"gpp_session_{app_context}"
        session_key = request.COOKIES.get(cookie_name)

        if not session_key:
            request.user = AnonymousUser()
            request.app_context = app_context
            return self.get_response(request)

        session = AccountsSession.objects.filter(
            session_key=session_key,
            session_cookie_name=cookie_name,
            revoked=False,
        ).select_related("user").first()

        if not session:
            response = JsonResponse(
                {"detail": f"Sessão {app_context} inválida.", "code": "session_invalid"},
                status=401,
            )
            response.delete_cookie(cookie_name)
            return response

        request.session_key = session_key
        request.app_context = app_context
        request.user = session.user
        return self.get_response(request)

    def _authenticate_any_cookie(self, request):
        """
        Itera sobre TODOS os cookies gpp_session_* presentes na request.
        Valida o primeiro AccountsSession ativo encontrado no banco.
        Usado por /api/accounts/ (endpoints transversais de gerenciamento).
        """
        gpp_cookies = {
            name: value
            for name, value in request.COOKIES.items()
            if name.startswith("gpp_session_")
        }

        if not gpp_cookies:
            request.user = AnonymousUser()
            request.app_context = None
            return self.get_response(request)

        # Tenta cada cookie até achar uma sessão válida
        session = (
            AccountsSession.objects
            .filter(
                session_key__in=list(gpp_cookies.values()),
                session_cookie_name__in=list(gpp_cookies.keys()),
                revoked=False,
            )
            .select_related("user")
            .first()
        )

        if not session:
            request.user = AnonymousUser()
            request.app_context = None
            return self.get_response(request)

        request.session_key = session.session_key
        request.app_context = session.app_context
        request.user = session.user
        return self.get_response(request)
