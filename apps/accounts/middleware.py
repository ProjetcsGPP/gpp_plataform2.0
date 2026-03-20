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

from .models import AccountsSession


class AppContextMiddleware:
    """
    Middleware de contexto de aplicação e revogação de sessão.

    Popula:
      request.app_context  → codigointerno da app da sessão atual
      request.session_key  → chave da sessão Django

    Bloqueia automaticamente:
      Sessões com AccountsSession.revoked=True recebem logout forçado
      e resposta 401 JSON imediata — sem propagar para a view.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.app_context = request.session.get("app_context")

        if request.user.is_authenticated:
            request.session_key = request.session.session_key

            is_revoked = AccountsSession.objects.filter(
                session_key=request.session_key,
                revoked=True
            ).exists()

            if is_revoked:
                logout(request)
                return JsonResponse(
                    {"detail": "Sessão revogada. Faça login novamente.",
                     "code": "session_revoked"},
                    status=401
                )
        else:
            request.session_key = None

        return self.get_response(request)
