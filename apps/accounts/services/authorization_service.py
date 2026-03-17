"""
AuthorizationService

Responsabilidade:
  Valida se um usuário pode executar uma ação em determinado recurso,
  combinando RBAC (roles/permissions do Django) com ABAC (atributos).

Método principal:
    service = AuthorizationService(user, application)
    pode = service.can("view_acao")
    pode = service.can("change_acao", context={"eixo": "X"})

Estratégia de cache:
    Chave: authz:{user_id}:{version}:{app_code}
    TTL:   300s
    Version key: authz_version:{user_id}
    Invalidação: signals em UserRole, Role, auth_group_permissions
"""

import logging
from typing import Optional

from django.core.cache import cache

security_logger = logging.getLogger("gpp.security")

CACHE_TTL = 300


class AuthorizationService:

    def __init__(self, user, application=None):
        self.user = user
        self.application = application

        self._permissions: Optional[set] = None
        self._attributes: Optional[dict] = None
        self._roles: Optional[list] = None

        # caches internos por request
        self._is_admin: Optional[bool] = None
        self._user_apps: Optional[set] = None

    # ─────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────

    def can(self, permission_codename: str, context: dict = None) -> bool:

        if not self.user or not self.user.is_authenticated:
            return False

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_ALLOW user_id=%s perm=%s reason=portal_admin",
                self.user.id,
                permission_codename,
            )
            return True

        if not self._has_valid_role():
            security_logger.warning(
                "AUTHZ_DENY user_id=%s perm=%s reason=no_valid_role app=%s",
                self.user.id,
                permission_codename,
                getattr(self.application, "codigointerno", "none"),
            )
            return False

        permissions = self._load_permissions()

        if permission_codename not in permissions:
            security_logger.warning(
                "AUTHZ_DENY user_id=%s perm=%s reason=no_permission app=%s",
                self.user.id,
                permission_codename,
                getattr(self.application, "codigointerno", "none"),
            )
            return False

        if context:
            if not self._check_abac(permission_codename, context):
                security_logger.warning(
                    "AUTHZ_DENY user_id=%s perm=%s reason=abac_filter app=%s context=%s",
                    self.user.id,
                    permission_codename,
                    getattr(self.application, "codigointerno", "none"),
                    context,
                )
                return False

        security_logger.info(
            "AUTHZ_ALLOW user_id=%s perm=%s app=%s",
            self.user.id,
            permission_codename,
            getattr(self.application, "codigointerno", "none"),
        )

        return True

    def get_permissions(self) -> set:
        return self._load_permissions()

    def get_attributes(self) -> dict:
        return self._load_attributes()

    def get_roles(self) -> list:
        return self._load_roles()

    # ─────────────────────────────────────────────
    # PORTAL ADMIN
    # ─────────────────────────────────────────────

    def _is_portal_admin(self) -> bool:

        if self._is_admin is not None:
            return self._is_admin

        from apps.accounts.models import UserRole

        self._is_admin = UserRole.objects.filter(
            user=self.user,
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()

        return self._is_admin

    # ─────────────────────────────────────────────
    # ClassificacaoUsuario
    # ─────────────────────────────────────────────

    def _get_classificacao(self):
        try:
            return self.user.profile.classificacao_usuario
        except Exception:
            return None

    def user_can_create_users(self) -> bool:

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_USER_CREATE user_id=%s reason=portal_admin",
                self.user.id,
            )
            return True

        classificacao = self._get_classificacao()

        if classificacao is None:
            security_logger.warning(
                "AUTHZ_DENY_USER_CREATE user_id=%s reason=no_classificacao",
                self.user.id,
            )
            return False

        result = bool(classificacao.pode_criar_usuario)

        log_level = security_logger.info if result else security_logger.warning

        log_level(
            "AUTHZ_USER_CREATE user_id=%s classificacao_id=%s classificacao=%s result=%s",
            self.user.id,
            classificacao.pk,
            classificacao.strdescricao,
            result,
        )

        return result

    def user_can_edit_users(self) -> bool:

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_USER_EDIT user_id=%s reason=portal_admin",
                self.user.id,
            )
            return True

        classificacao = self._get_classificacao()

        if classificacao is None:
            security_logger.warning(
                "AUTHZ_DENY_USER_EDIT user_id=%s reason=no_classificacao",
                self.user.id,
            )
            return False

        result = bool(classificacao.pode_editar_usuario)

        log_level = security_logger.info if result else security_logger.warning

        log_level(
            "AUTHZ_USER_EDIT user_id=%s classificacao_id=%s classificacao=%s result=%s",
            self.user.id,
            classificacao.pk,
            classificacao.strdescricao,
            result,
        )

        return result

    # ─────────────────────────────────────────────
    # Helpers de aplicação
    # ─────────────────────────────────────────────

    def _get_user_applications(self) -> set:

        if self._user_apps is not None:
            return self._user_apps

        from apps.accounts.models import UserRole

        self._user_apps = set(
            UserRole.objects
            .filter(user=self.user)
            .values_list("aplicacao_id", flat=True)
        )

        return self._user_apps

    def _has_application_intersection(self, target_user) -> bool:

        from apps.accounts.models import UserRole

        user_apps = self._get_user_applications()

        return UserRole.objects.filter(
            user=target_user,
            aplicacao_id__in=user_apps,
        ).exists()

    # ─────────────────────────────────────────────
    # Gerenciamento de usuários por aplicação
    # ─────────────────────────────────────────────

    def user_can_create_user_in_application(self, aplicacao) -> bool:

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_CREATE_IN_APP_ALLOW user_id=%s app=%s reason=portal_admin",
                self.user.id,
                getattr(aplicacao, "codigointerno", aplicacao),
            )
            return True

        if not self.user_can_create_users():
            security_logger.warning(
                "AUTHZ_CREATE_IN_APP_DENY user_id=%s app=%s reason=no_create_permission",
                self.user.id,
                getattr(aplicacao, "codigointerno", aplicacao),
            )
            return False

        from apps.accounts.models import UserRole

        has_role = UserRole.objects.filter(
            user=self.user,
            aplicacao=aplicacao,
        ).exists()

        if has_role:
            security_logger.info(
                "AUTHZ_CREATE_IN_APP_ALLOW user_id=%s app=%s reason=has_role_in_app",
                self.user.id,
                getattr(aplicacao, "codigointerno", aplicacao),
            )
        else:
            security_logger.warning(
                "AUTHZ_CREATE_IN_APP_DENY user_id=%s app=%s reason=no_role_in_app",
                self.user.id,
                getattr(aplicacao, "codigointerno", aplicacao),
            )

        return has_role

    def user_can_edit_target_user(self, target_user) -> bool:

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_EDIT_TARGET_ALLOW user_id=%s target_user_id=%s reason=portal_admin",
                self.user.id,
                target_user.id,
            )
            return True

        if not self.user_can_edit_users():
            security_logger.warning(
                "AUTHZ_EDIT_TARGET_DENY user_id=%s target_user_id=%s reason=no_edit_permission",
                self.user.id,
                target_user.id,
            )
            return False

        has_intersection = self._has_application_intersection(target_user)

        if has_intersection:
            security_logger.info(
                "AUTHZ_EDIT_TARGET_ALLOW user_id=%s target_user_id=%s reason=app_intersection",
                self.user.id,
                target_user.id,
            )
        else:
            security_logger.warning(
                "AUTHZ_EDIT_TARGET_DENY user_id=%s target_user_id=%s reason=no_app_intersection",
                self.user.id,
                target_user.id,
            )

        return has_intersection

    def user_can_manage_target_user(self, target_user) -> bool:

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_MANAGE_USER_ALLOW user_id=%s target_user_id=%s reason=portal_admin",
                self.user.id,
                target_user.id,
            )
            return True

        if not self.user_can_edit_users():
            security_logger.warning(
                "AUTHZ_MANAGE_USER_DENY user_id=%s target_user_id=%s reason=no_edit_permission",
                self.user.id,
                target_user.id,
            )
            return False

        has_intersection = self._has_application_intersection(target_user)

        if has_intersection:
            security_logger.info(
                "AUTHZ_MANAGE_USER_ALLOW user_id=%s target_user_id=%s reason=app_intersection",
                self.user.id,
                target_user.id,
            )
        else:
            security_logger.warning(
                "AUTHZ_MANAGE_USER_DENY user_id=%s target_user_id=%s reason=no_app_intersection",
                self.user.id,
                target_user.id,
            )

        return has_intersection

    # ─────────────────────────────────────────────
    # RBAC / ABAC
    # ─────────────────────────────────────────────

    def _has_valid_role(self) -> bool:
        roles = self._load_roles()
        return len(roles) > 0

    def _check_abac(self, permission_codename: str, context: dict) -> bool:

        attributes = self._load_attributes()

        for key, expected_value in context.items():

            user_value = attributes.get(key)

            if user_value is None:
                return False

            if str(user_value) != str(expected_value):
                return False

        return True

    # ─────────────────────────────────────────────
    # Cache loaders
    # ─────────────────────────────────────────────

    def _load_permissions(self) -> set:

        if self._permissions is not None:
            return self._permissions

        cache_key = self._permissions_cache_key()

        cached = cache.get(cache_key)

        if cached is not None:
            self._permissions = cached
            return self._permissions

        from django.contrib.auth.models import Permission
        from apps.accounts.models import UserRole

        roles = self._load_roles()

        group_ids = [
            ur.role.group_id
            for ur in roles
            if ur.role.group_id is not None
        ]

        if group_ids:
            perms = (
                Permission.objects
                .filter(group__id__in=group_ids)
                .values_list("codename", flat=True)
            )
            self._permissions = set(perms)
        else:
            self._permissions = set()

        cache.set(cache_key, self._permissions, CACHE_TTL)

        return self._permissions

    def _load_roles(self) -> list:

        if self._roles is not None:
            return self._roles

        from apps.accounts.models import UserRole

        qs = (
            UserRole.objects
            .filter(user=self.user)
            .select_related("role", "role__group", "aplicacao")
        )

        if self.application:
            qs = qs.filter(aplicacao=self.application)

        self._roles = list(qs)

        return self._roles

    def _load_attributes(self) -> dict:

        if self._attributes is not None:
            return self._attributes

        from apps.accounts.models import Attribute

        qs = Attribute.objects.filter(user=self.user)

        if self.application:
            qs = qs.filter(aplicacao=self.application)

        self._attributes = {a.key: a.value for a in qs}

        return self._attributes

    def _permissions_cache_key(self) -> str:

        app_code = self.application.codigointerno if self.application else "all"

        version = cache.get(f"authz_version:{self.user.id}") or 1

        return f"authz:{self.user.id}:v{version}:{app_code}"
