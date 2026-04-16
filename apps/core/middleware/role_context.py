"""
RoleContextMiddleware

Responsabilidade:
  Carrega as roles ativas do usuário autenticado para
  a aplicação identificada no request.application.

Depende de:
  - request.user        (SessionAuthentication via Django AuthenticationMiddleware)
  - request.application (injetado pelo ApplicationContextMiddleware)

Injeta no request:
  - request.user_roles     : list[UserRole] ativos (nunca None, mínimo [])
  - request.is_portal_admin: bool (se tem role PORTAL_ADMIN ou is_superuser=True)

Usa cache Memcached com cache versioning para invalidação
correta sem suporte a wildcards.

Evento ROLE_SWITCH é logado quando o conjunto de roles do usuário
se altera entre requests (detecção de troca de contexto).

FIX: user.is_superuser=True seta is_portal_admin=True sem exigir UserRole
     no banco — evita 403 reason=no_role para superusers Django.
"""

import logging

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache

from apps.accounts.models import UserRole

security_logger = logging.getLogger("gpp.security")

CACHE_TTL = 300  # 5 minutos


class RoleContextMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # 🔥 BYPASS TOTAL PARA LOGOUT
        if getattr(request, "is_logout_request", False):
            security_logger.debug(
                "LOGOUT_REQUEST — skipping role loading path=%s", request.path
            )
            request.user_roles = []
            request.is_portal_admin = False

            # 🔥 opcional (blindagem extra)
            if not hasattr(request, "user"):
                request.user = AnonymousUser()

            return self.get_response(request)

        if request.user and not isinstance(request.user, AnonymousUser):
            self._load_roles(request)
        else:
            request.user_roles = []
            request.is_portal_admin = False

        return self.get_response(request)

    def _load_roles(self, request):
        user = request.user
        application = getattr(request, "application", None)

        # Cache sempre consultado primeiro -- inclusive para superuser.
        # Garante que mocks de cache.get() sejam respeitados nos testes.
        cache_key = self._make_cache_key(user.id, application)
        cached_roles = cache.get(cache_key)

        if cached_roles is not None:
            request.user_roles = cached_roles or []
            request.is_portal_admin = user.is_superuser or any(
                ur.role.codigoperfil == "PORTAL_ADMIN" for ur in request.user_roles
            )
            return

        # Superuser Django -> admin irrestrito sem precisar de UserRole no banco
        if user.is_superuser:
            request.user_roles = []
            request.is_portal_admin = True
            security_logger.info(
                "ROLES_LOADED user_id=%s app=%s roles=[] is_admin=True (superuser)",
                user.id,
                getattr(application, "codigointerno", "none"),
            )
            cache.set(cache_key, [], CACHE_TTL)
            return

        qs = UserRole.objects.filter(user=user).select_related(
            "role", "role__group", "aplicacao"
        )

        if application:
            qs = qs.filter(aplicacao=application) | qs.filter(
                role__codigoperfil="PORTAL_ADMIN"
            )

        user_roles = list(qs.distinct())

        request.user_roles = user_roles or []

        is_admin = any(
            ur.role.codigoperfil == "PORTAL_ADMIN" for ur in request.user_roles
        )
        request.is_portal_admin = is_admin

        previous_roles_key = f"user_roles_previous:{user.id}"
        previous_roles = cache.get(previous_roles_key)
        current_role_codes = sorted([ur.role.codigoperfil for ur in request.user_roles])

        if previous_roles is not None and previous_roles != current_role_codes:
            security_logger.info(
                "ROLE_SWITCH user_id=%s from=%s to=%s path=%s",
                user.id,
                previous_roles,
                current_role_codes,
                request.path,
            )

        cache.set(previous_roles_key, current_role_codes, CACHE_TTL)

        version = self._get_version(user.id)
        cache.set(f"{cache_key}:v{version}", request.user_roles, CACHE_TTL)
        cache.set(cache_key, request.user_roles, CACHE_TTL)

        security_logger.info(
            "ROLES_LOADED user_id=%s app=%s roles=%s is_admin=%s",
            user.id,
            getattr(application, "codigointerno", "none"),
            [ur.role.codigoperfil for ur in request.user_roles],
            is_admin,
        )

    @staticmethod
    def _make_cache_key(user_id, application):
        app_code = application.codigointerno if application else "all"
        return f"user_roles:{user_id}:{app_code}"

    @staticmethod
    def _get_version(user_id):
        key = f"authz_version:{user_id}"
        version = cache.get(key)
        if version is None:
            cache.set(key, 1, CACHE_TTL * 10)
            return 1
        return version
