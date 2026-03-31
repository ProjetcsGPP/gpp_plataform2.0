"""
GPP Plataform 2.0 — Accounts Middleware
FASE-0: AppContextMiddleware
"""

from django.contrib.auth import logout
from django.http import JsonResponse
from django.contrib.auth.models import AnonymousUser

from .models import AccountsSession


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
        
        # 🔥 BYPASS PARA LOGOUT (NOVO - 4 linhas)
        if '/auth/logout/' in request.path or '/logout/' in request.path:
            request.app_context = path_prefix
            return self.get_response(request)
        
        if not session_key:
            request.user = AnonymousUser()
            request.app_context = path_prefix
            return self.get_response(request)
        
        # Seu código original (mantido)
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
