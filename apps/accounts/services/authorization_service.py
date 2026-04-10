"""
AuthorizationService

Responsabilidade:
  Valida se um usuário pode executar uma ação em determinado recurso,
  combinando RBAC (roles/permissions do Django) com ABAC (atributos).

Método principal:
    service = AuthorizationService(user, application)
    pode = service.can("view_acao")
    pode = service.can("change_acao", context={"eixo": "X"})

Estrategia de cache:
    Chave: authz:{user_id}:{version}:{app_code}
    TTL:   300s
    Version key: authz_version:{user_id}
    Invalidação: signals em UserRole, Role, auth_group_permissions,
                 UserPermissionOverride

Resolução de permissões (ordem):
    1. Permissões herdadas do grupo da role (auth_group_permissions)
    2. Permissões diretas do usuário    (auth_user_user_permissions)  — D-02
    3. + grant overrides                (UserPermissionOverride)       — D-01
    4. - revoke overrides               (UserPermissionOverride)       — D-01
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

        # cache interno por request
        self._is_admin: Optional[bool] = None

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
    # Delegação para UserPolicy (com cache de instância)
    # ─────────────────────────────────────────────

    def _policy(self):
        """Retorna a instância única de UserPolicy para este ciclo de request."""
        if not hasattr(self, "_user_policy"):
            from apps.accounts.policies import UserPolicy
            self._user_policy = UserPolicy(self.user)
        return self._user_policy

    def user_can_create_users(self) -> bool:
        return self._policy().can_create_user()

    def user_can_edit_users(self) -> bool:
        return self._policy().can_edit_user()

    def user_can_create_user_in_application(self, aplicacao) -> bool:
        return self._policy().can_create_user_in_application(aplicacao)

    def user_can_edit_target_user(self, target_user) -> bool:
        return self._policy().can_edit_target_user(target_user)

    def user_can_manage_target_user(self, target_user) -> bool:
        return self._policy().can_manage_target_user(target_user)

    def can_create_user(self) -> bool:
        """Alias retrocompatível — tests chamam este nome."""
        return self.user_can_create_users()

    def can_edit_user(self) -> bool:
        """Alias retrocompatível — tests chamam este nome."""
        return self.user_can_edit_users()

    def get_user_roles_for_app(self, aplicacao) -> list:
        """
        Retorna lista de UserRole do usuário para a aplicação.
        Usado por TestGetUserRolesForApp em test_authorization_service.py.
        """
        from apps.accounts.models import UserRole
        return list(
            UserRole.objects
            .filter(user=self.user, aplicacao=aplicacao)
            .select_related("role", "role__group", "aplicacao")
        )

    # ─────────────────────────────────────────────
    # PORTAL ADMIN — usado por can() e por core/permissions.py
    # (IsPortalAdmin, ObjectPermission)
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
        """
        Resolve o conjunto final de permissões do usuário.

        Ordem de resolução (ADR-PERM-01):
          1. Permissões herdadas do grupo da role (auth_group_permissions)
          2. Permissões diretas do usuário (auth_user_user_permissions)  [D-02]
          3. + grant overrides (UserPermissionOverride mode='grant')     [D-01]
          4. - revoke overrides (UserPermissionOverride mode='revoke')   [D-01]
        """

        if self._permissions is not None:
            return self._permissions

        cache_key = self._permissions_cache_key()

        cached = cache.get(cache_key)

        if cached is not None:
            self._permissions = cached
            return self._permissions

        from django.contrib.auth.models import Permission
        from apps.accounts.models import UserPermissionOverride

        roles = self._load_roles()

        # 1. Permissões herdadas pelos grupos das roles
        group_ids = [
            ur.role.group_id
            for ur in roles
            if ur.role.group_id is not None
        ]

        if group_ids:
            base_perms = set(
                Permission.objects
                .filter(group__id__in=group_ids)
                .values_list("codename", flat=True)
            )
        else:
            base_perms = set()

        # 2. Permissões diretas do usuário (auth_user_user_permissions) — corrige D-02
        direct_perms = set(
            self.user.user_permissions
            .values_list("codename", flat=True)
        )
        base_perms |= direct_perms

        # 3. Aplicar grant overrides — corrige D-01
        grant_codenames = set(
            UserPermissionOverride.objects
            .filter(user=self.user, mode=UserPermissionOverride.MODE_GRANT)
            .values_list("permission__codename", flat=True)
        )
        base_perms |= grant_codenames

        # 4. Aplicar revoke overrides — corrige D-01
        revoke_codenames = set(
            UserPermissionOverride.objects
            .filter(user=self.user, mode=UserPermissionOverride.MODE_REVOKE)
            .values_list("permission__codename", flat=True)
        )
        base_perms -= revoke_codenames

        self._permissions = base_perms

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
