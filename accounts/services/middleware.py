# accounts/middleware.py
"""
Middleware JWT Universal - Único método para Web + API
"""

import logging

from django.contrib.auth.models import AnonymousUser, User
from django.shortcuts import redirect
from django.utils.functional import SimpleLazyObject

from .models import UserRole
from .services.token_service import InvalidTokenException, get_token_service

logger = logging.getLogger(__name__)


def get_user_from_jwt(request):
    """
    Extrai usuário AUTENTICANDO APENAS por JWT Bearer token.

    SEM fallback para session - JWT universal!

    1. Authorization: Bearer <token>
    2. Valida com TokenService
    3. Define request.user
    4. Anexa request.token_payload

    Retorna:
        - User autenticado (JWT válido)
        - AnonymousUser (JWT inválido/ausente)
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")

    # Verifica Bearer token
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        token_service = get_token_service()

        try:
            payload = token_service.validate_access_token(token)

            # ✅ Token válido
            user_id = payload.get("sub")
            user = User.objects.get(id=user_id, is_active=True)

            # Anexa payload ao request
            request.token_payload = payload

            logger.debug(
                f"JWT universal: user={user.email}, "
                f"app={payload.get('app_code')}, "
                f"role={payload.get('role_code')}"
            )

            return user

        except (InvalidTokenException, User.DoesNotExist) as e:
            logger.debug(f"JWT inválido: {str(e)}")

    # ✨ 2. Cookie access_token (Web templates)
    elif "access_token" in request.COOKIES:
        token = request.COOKIES["access_token"]
        auth_header = f"Bearer {token}"  # Trata igual
        try:
            payload = token_service.validate_access_token(token)

            # ✅ Token válido
            user_id = payload.get("sub")
            user = User.objects.get(id=user_id, is_active=True)

            # Anexa payload ao request
            request.token_payload = payload

            logger.debug(
                f"JWT universal: user={user.email}, "
                f"app={payload.get('app_code')}, "
                f"role={payload.get('role_code')}"
            )

            return user

        except (InvalidTokenException, User.DoesNotExist) as e:
            logger.debug(f"JWT inválido: {str(e)}")

    # ❌ Sem token JWT = não autenticado
    logger.debug("Sem token JWT - usuário anônimo")
    return AnonymousUser()


class JWTUniversalAuthenticationMiddleware:
    """
    Middleware JWT Universal - ÚNICO método para Web + API

    Características:
    ✅ Web tradicional (Django templates) usa JWT
    ✅ APIs (Next.js) usam JWT
    ✅ SEM sessions para autenticação
    ✅ Cookies podem armazenar tokens (HttpOnly/Secure)
    ✅ request.token_payload disponível em todas views

    Posição: APÓS AuthenticationMiddleware
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Lazy loading - autentica SOMENTE por JWT
        request.user = SimpleLazyObject(lambda: get_user_from_jwt(request))

        response = self.get_response(request)
        return response


# ============================================================================
# MIDDLEWARE DE ROLE ATIVA (PRESERVADO)
# ============================================================================


class ActiveRoleMiddleware:
    """
    Middleware que garante que o usuário tenha um papel ativo selecionado
    para a aplicação que está acessando

    Agora usa request.token_payload para detectar app_code
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_urls = [
            "/accounts/login/",
            "/accounts/logout/",
            "/accounts/select-role/",
            "/accounts/auth/",
            "/admin/",
            "/static/",
            "/media/",
        ]

    def __call__(self, request):
        # Se não está autenticado ou URL isenta, prossegue
        if not request.user.is_authenticated or self._is_exempt(request.path):
            return self.get_response(request)

        # ✨ MELHORADO: Usa token_payload OU path
        app_code = self._get_app_code(request)

        if app_code:
            # Verifica role ativa na sessão (armazenamento local do JWT funciona também)
            session_key = f"active_role_{app_code}"
            active_role_id = request.session.get(session_key)

            # Valida se o papel ainda existe
            if active_role_id:
                try:
                    active_role = UserRole.objects.select_related(
                        "role", "aplicacao"
                    ).get(
                        id=active_role_id,
                        user=request.user,
                        aplicacao__codigointerno=app_code,
                    )
                    request.active_role = active_role
                except UserRole.DoesNotExist:
                    # Papel inválido
                    if hasattr(request, "session"):
                        request.session.pop(session_key, None)
                    return redirect("accounts:select_role", app_code=app_code)
            else:
                # Não tem role ativa
                return redirect("accounts:select_role", app_code=app_code)

        response = self.get_response(request)
        return response

    def _is_exempt(self, path):
        return any(path.startswith(url) for url in self.exempt_urls)

    def _get_app_code(self, request):
        """
        Detecta app_code:
        1. request.token_payload['app_code'] (JWT)
        2. Path da URL (fallback)
        """
        # 1. JWT token_payload (prioridade)
        if hasattr(request, "token_payload"):
            app_code = request.token_payload.get("app_code")
            if app_code:
                return app_code

        # 2. Fallback: path da URL
        path = request.path
        if path.startswith("/acoes-pngi/"):
            return "ACOES_PNGI"
        elif path.startswith("/carga_org_lot/"):
            return "CARGA_ORG_LOT"
        elif path.startswith("/portal/"):
            return "PORTAL"
        return None
