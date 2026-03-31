"""
GPP Plataform 2.0 — Accounts Middleware
FASE-0: AppContextMiddleware

Responsabilidades:
  1. Popula request.app_context e request.session_key a partir da sessão Django.
  2. Bloqueia automaticamente sessões revogadas:
     - AccountsSession.revoked=True → logout forçado + 401 JSON imediato.

Ordem obrigatória em MIDDLEWARE (settings.py):
  "django.contrib.sessions.middleware.SessionMiddleware",
  "django.contrib.auth.middleware.AuthenticationMiddleware",
  "apps.accounts.middleware.AppContextMiddleware",
"""
from django.contrib.auth import logout
from django.http import JsonResponse
from django.contrib.auth.models import AnonymousUser

from .models import AccountsSession


#class AppContextMiddleware:
#    """
#    Middleware de contexto de aplicação e revogação de sessão.
#
#    Popula:
#      request.app_context  → codigointerno da app da sessão atual
#      request.session_key  → chave da sessão Django
#
#    Bloqueia automaticamente:
#      Sessões com AccountsSession.revoked=True recebem logout forçado
#      e resposta 401 JSON imediata — sem propagar para a view.
#    """
#
#    def __init__(self, get_response):
#        self.get_response = get_response
#
#    def __call__(self, request):
#        request.app_context = request.session.get("app_context")
#
#        if request.user.is_authenticated:
#            request.session_key = request.session.session_key
#
#            is_revoked = AccountsSession.objects.filter(
#                session_key=request.session_key,
#                revoked=True
#            ).exists()
#
#            if is_revoked:
#                logout(request)
#                return JsonResponse(
#                    {"detail": "Sessão revogada. Faça login novamente.",
#                     "code": "session_revoked"},
#                    status=401
#                )
#        else:
#            request.session_key = None
#
#        return self.get_response(request)
#


class AppContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Mapear URL → app_context esperado
        app_mapping = {
            "acoes-pngi": "ACOES_PNGI",
            "carga-org-lot": "CARGA_ORG_LOT", 
            "portal": "PORTAL",
            "accounts": "ACCOUNTS",
        }
        
        path_prefix = None
        for prefix, app_ctx in app_mapping.items():
            if f"/api/{prefix}/" in request.path:
                path_prefix = app_ctx
                break
        
        if not path_prefix:
            path_prefix = "PORTAL"  # default
        
        expected_cookie = f"gpp_session_{path_prefix}"
        session_key = request.COOKIES.get(expected_cookie)
        
        if not session_key:
            request.user = AnonymousUser()
            request.app_context = path_prefix
            return self.get_response(request)
        
        # Validar sessão específica do cookie
        is_revoked = AccountsSession.objects.filter(
            session_key=session_key,
            session_cookie_name=expected_cookie,
            revoked=True
        ).exists()
        
        if is_revoked:
            response = JsonResponse(
                {"detail": f"Sessão {path_prefix} revogada. Faça login novamente.", "code": "session_revoked"},
                status=401
            )
            response.delete_cookie(expected_cookie)
            return response
        
        # Sessão válida
        request.session_key = session_key
        request.app_context = path_prefix
        return self.get_response(request)
