"""
AuthorizationMiddleware

Responsabilidade:
  Última camada de segurança antes de chegar na view.
  Bloqueia requests de usuários sem autenticação ou sem role
  para a aplicação atual.

Depende de:
  - request.user          (JWTAuthenticationMiddleware)
  - request.user_roles    (RoleContextMiddleware)
  - request.is_portal_admin (RoleContextMiddleware)

Regras:
  1. Rotas isentas (AUTHORIZATION_EXEMPT_PATHS) → passa sempre
  2. PORTAL_ADMIN → passa sempre
  3. Usuário não autenticado → 401
  4. Usuário sem nenhuma role para a app atual → 403
  5. Path bate com AUTHORIZATION_REQUIRED_ROLES e usuário não tem
     nenhuma das roles requeridas → 403 permission_denied
"""
import json
import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse

security_logger = logging.getLogger("gpp.security")

EXEMPT_PATHS = getattr(
    settings,
    "AUTHORIZATION_EXEMPT_PATHS",
    ["/api/auth/token/", "/api/auth/token/refresh/", "/admin/", "/api/health/"],
)

REQUIRED_ROLES_MAP = getattr(settings, "AUTHORIZATION_REQUIRED_ROLES", {})


class AuthorizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Rotas isentas — nunca bloquear
        if self._is_exempt(request.path):
            return self.get_response(request)

        # PORTAL_ADMIN — acesso irrestrito
        if getattr(request, "is_portal_admin", False):
            return self.get_response(request)

        # Usuário não autenticado
        if not request.user or isinstance(request.user, AnonymousUser):
            security_logger.warning(
                "401_UNAUTHORIZED path=%s method=%s",
                request.path, request.method,
            )
            return self._json_response(
                status=401,
                code="not_authenticated",
                detail="Autenticação necessária. Forneça um token Bearer válido.",
            )

        # Usuário autenticado mas sem role para esta aplicação
        user_roles = getattr(request, "user_roles", [])
        if not user_roles:
            application = getattr(request, "application", None)
            app_code = application.codigointerno if application else "unknown"
            security_logger.warning(
                "403_FORBIDDEN user_id=%s path=%s app=%s reason=no_role",
                request.user.id, request.path, app_code,
            )
            return self._json_response(
                status=403,
                code="permission_denied",
                detail=(
                    f"Você não possui perfil de acesso para a aplicação '{app_code}'. "
                    "Entre em contato com o administrador."
                ),
            )

        # Verifica restrição de roles por path pattern (AUTHORIZATION_REQUIRED_ROLES)
        required_roles = self._get_required_roles(request.path)
        if required_roles:
            user_role_codes = {ur.role.codigoperfil for ur in user_roles}
            if not user_role_codes.intersection(set(required_roles)):
                application = getattr(request, "application", None)
                app_code = application.codigointerno if application else "unknown"
                security_logger.warning(
                    "403_FORBIDDEN_ROLE user_id=%s path=%s required_roles=%s user_roles=%s",
                    request.user.id, request.path, required_roles, list(user_role_codes),
                )
                return self._json_response(
                    status=403,
                    code="permission_denied",
                    detail=(
                        f"Você não possui o perfil necessário para acessar este recurso. "
                        f"Perfis requeridos: {', '.join(required_roles)}."
                    ),
                )

        return self.get_response(request)

    @staticmethod
    def _is_exempt(path):
        return any(path.startswith(p) for p in EXEMPT_PATHS)

    @staticmethod
    def _get_required_roles(path):
        """
        Retorna a lista de roles requeridas para o path, ou None se não há restrição configurada.
        Itera sobre AUTHORIZATION_REQUIRED_ROLES em settings.
        Relê a configuração a cada chamada para suportar @override_settings em testes.
        """
        required_roles_map = getattr(settings, "AUTHORIZATION_REQUIRED_ROLES", {})
        for pattern, roles in required_roles_map.items():
            if path.startswith(pattern):
                return roles
        return None

    @staticmethod
    def _json_response(status, code, detail):
        return JsonResponse(
            {
                "success": False,
                "status_code": status,
                "errors": {"code": code, "detail": detail},
            },
            status=status,
        )
