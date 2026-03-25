"""
AuthorizationMiddleware

Responsabilidade:
  Última camada de segurança antes de chegar na view.
  Bloqueia requests de usuários sem autenticação ou sem role
  para a aplicação atual.

Depende de:
  - request.user          (SessionAuthentication via Django AuthenticationMiddleware)
  - request.user_roles    (RoleContextMiddleware)
  - request.is_portal_admin (RoleContextMiddleware)
  - request.app_context   (AppContextMiddleware de apps.accounts)

Regras:
  1. Rotas isentas (AUTHORIZATION_EXEMPT_PATHS) → passa sempre
  2. PORTAL_ADMIN → passa sempre
  3. Usuário não autenticado → 401
  4. Usuário sem nenhuma role para a app atual → 403
  5. Path bate com AUTHORIZATION_REQUIRED_ROLES e usuário não tem
     nenhuma das roles requeridas → 403 permission_denied

FIX: EXEMPT_PATHS e REQUIRED_ROLES_MAP são lidos de settings a cada
     request (via `django.conf.settings`) em vez de no __init__ (load time).
     Isso garante que @override_settings nos testes funcione corretamente
     sem precisar de workarounds ou recriação do middleware.
"""
import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse

security_logger = logging.getLogger("gpp.security")


class AuthorizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Rotas isentas — nunca bloquear
        # Lido de settings a cada request para suportar @override_settings nos testes
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
                detail="Autenticação necessária.",
            )

        # Usuário autenticado mas sem role para esta aplicação
        user_roles = getattr(request, "user_roles", [])
        if not user_roles:
            app_context = self._resolve_app_context(request)
            security_logger.warning(
                "403_FORBIDDEN user_id=%s path=%s app=%s reason=no_role",
                request.user.id, request.path, app_context,
            )
            return self._json_response(
                status=403,
                code="permission_denied",
                detail=(
                    f"Você não possui perfil de acesso para a aplicação '{app_context}'. "
                    "Entre em contato com o administrador."
                ),
            )

        # Verifica restrição de roles por path pattern (AUTHORIZATION_REQUIRED_ROLES)
        required_roles = self._get_required_roles(request.path)
        if required_roles:
            user_role_codes = {ur.role.codigoperfil for ur in user_roles}
            if not user_role_codes.intersection(set(required_roles)):
                app_context = self._resolve_app_context(request)
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
        """
        Verifica se o path está isento de autenticação.
        Lido de settings a cada chamada para respeitar @override_settings nos testes.
        """
        exempt_paths = getattr(
            settings,
            "AUTHORIZATION_EXEMPT_PATHS",
            ["/api/accounts/login/", "/api/accounts/logout/", "/admin/", "/api/health/"],
        )
        return any(path.startswith(p) for p in exempt_paths)

    @staticmethod
    def _get_required_roles(path):
        """
        Retorna a lista de roles requeridas para o path, ou None se não há restrição.
        Lido de settings a cada chamada para respeitar @override_settings nos testes.
        """
        required_roles_map = getattr(settings, "AUTHORIZATION_REQUIRED_ROLES", {})
        for pattern, roles in required_roles_map.items():
            if path.startswith(pattern):
                return roles
        return None

    @staticmethod
    def _resolve_app_context(request):
        """
        Resolve o código da aplicação atual para uso em logs e mensagens de erro.
        Usa request.app_context (Fase-0) com fallback para request.application.
        """
        app_context = getattr(request, "app_context", None)
        if not app_context:
            application = getattr(request, "application", None)
            app_context = application.codigointerno if application else "unknown"
        return app_context

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
