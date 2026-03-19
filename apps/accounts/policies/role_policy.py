"""
RolePolicy

Responsabilidade:
    Encapsula as regras de autorização sobre a entidade Role (RBAC).
    Domínio puro — sem conhecimento de request, DRF ou views.

Regras centrais:
  - Criar/editar/deletar Role: apenas PORTAL_ADMIN ou SuperUser.
  - Leitura de Role: usuário com UserRole na mesma aplicação da role alvo.
  - Role codigoperfil="PORTAL_ADMIN" é a role raiz protegida:
      * Nunca pode ser deletada (nem SuperUser)
      * Só pode ser editada por SuperUser (não por PORTAL_ADMIN comum)
      * Só pode ser atribuída/revogada por SuperUser
  - Ninguém pode revogar a própria role.

Notas de implementação:
  - role.aplicacao=None indica uma role global (ex: PORTAL_ADMIN) não vinculada
    a nenhuma app específica. Checks de isappbloqueada e isappproductionready
    não se aplicam a roles globais — ausência de app = ausência de restrição de app.

Usage:
    policy = RolePolicy(user, role)
    policy.can_view_role()
    policy.can_create_role()
    policy.can_edit_role()
    policy.can_delete_role()
    policy.can_assign_role_to_user(target_user)
    policy.can_revoke_role_from_user(target_user)
"""

import logging
from apps.accounts.models import UserRole

security_logger = logging.getLogger("gpp.security")


class RolePolicy:
    def __init__(self, user, role):
        self.user = user
        self.role = role
        self._is_admin = None
        self._actor_role_in_same_app = None

    # ── API pública ────────────────────────────────────────────

    def can_view_role(self) -> bool:
        """
        PORTAL_ADMIN / SuperUser: True (qualquer role, qualquer app).
        Usuário comum:
          - App da role com isappbloqueada=True → deny (reason: app_blocked)
          - Sem UserRole na mesma aplicação da role → deny (reason: no_role_in_same_app)
          - Passou → True
        """
        if self._is_privileged():
            return True

        if self._role_app_is_blocked():
            security_logger.warning(
                "can_view_role denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "app_blocked",
                },
            )
            return False

        if self._get_actor_role_in_same_app() is None:
            security_logger.warning(
                "can_view_role denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "no_role_in_same_app",
                },
            )
            return False

        return True

    def can_create_role(self) -> bool:
        """
        Apenas _is_privileged().
        reason: not_portal_admin
        """
        if self._is_privileged():
            return True

        security_logger.warning(
            "can_create_role denied",
            extra={
                "user_id": self.user.id,
                "reason": "not_portal_admin",
            },
        )
        return False

    def can_edit_role(self) -> bool:
        """
        Apenas _is_privileged().
        Proteção adicional da role raiz:
          - codigoperfil="PORTAL_ADMIN" → somente SuperUser pode editar
          - PORTAL_ADMIN comum tentando editar PORTAL_ADMIN → deny
        reason: not_portal_admin | protected_root_role_requires_superuser
        """
        if not self._is_privileged():
            security_logger.warning(
                "can_edit_role denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "not_portal_admin",
                },
            )
            return False

        if self._is_root_role() and not self._is_superuser():
            security_logger.warning(
                "can_edit_role denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "protected_root_role_requires_superuser",
                },
            )
            return False

        return True

    def can_delete_role(self) -> bool:
        """
        Apenas _is_privileged().
        Proteção total da role raiz:
          - codigoperfil="PORTAL_ADMIN" → NUNCA pode ser deletada (nem SuperUser)
        reason: not_portal_admin | protected_root_role_immutable
        """
        if self._is_root_role():
            security_logger.warning(
                "can_delete_role denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "protected_root_role_immutable",
                },
            )
            return False

        if not self._is_privileged():
            security_logger.warning(
                "can_delete_role denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "not_portal_admin",
                },
            )
            return False

        return True

    def can_assign_role_to_user(self, target_user) -> bool:  # noqa: ARG002
        """
        Apenas _is_privileged().
        Proteção adicional:
          - Atribuir codigoperfil="PORTAL_ADMIN" → somente SuperUser
          - Se role.aplicacao não é None: app deve estar isappbloqueada=False
            E isappproductionready=True
          - role.aplicacao=None (role global) → sem restrição de app
        reason: not_portal_admin | cannot_assign_admin_role | app_blocked | app_not_production_ready
        """
        if not self._is_privileged():
            security_logger.warning(
                "can_assign_role_to_user denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "not_portal_admin",
                },
            )
            return False

        if self._is_root_role() and not self._is_superuser():
            security_logger.warning(
                "can_assign_role_to_user denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "cannot_assign_admin_role",
                },
            )
            return False

        if self._role_app_is_blocked():
            security_logger.warning(
                "can_assign_role_to_user denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "app_blocked",
                },
            )
            return False

        if not self._role_app_is_production_ready():
            security_logger.warning(
                "can_assign_role_to_user denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "app_not_production_ready",
                },
            )
            return False

        return True

    def can_revoke_role_from_user(self, target_user) -> bool:
        """
        Apenas _is_privileged().
        Proteções:
          - user == target_user → NUNCA (ninguém remove a própria role)
          - Revogar codigoperfil="PORTAL_ADMIN" → somente SuperUser
          - Remoção é permitida mesmo com app bloqueada
            (precisa poder remover acessos durante bloqueio)
        reason: not_portal_admin | cannot_revoke_own_role | cannot_revoke_admin_role
        """
        # Verificação de auto-revogação tem precedência absoluta
        if self.user == target_user:
            security_logger.warning(
                "can_revoke_role_from_user denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "cannot_revoke_own_role",
                },
            )
            return False

        if not self._is_privileged():
            security_logger.warning(
                "can_revoke_role_from_user denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "not_portal_admin",
                },
            )
            return False

        if self._is_root_role() and not self._is_superuser():
            security_logger.warning(
                "can_revoke_role_from_user denied",
                extra={
                    "user_id": self.user.id,
                    "role_id": self.role.pk,
                    "reason": "cannot_revoke_admin_role",
                },
            )
            return False

        return True

    # ── Helpers privados ───────────────────────────────────────

    def _is_portal_admin(self) -> bool:
        """Cópia isolada — não importar de outras policies."""
        if self._is_admin is not None:
            return self._is_admin

        self._is_admin = UserRole.objects.filter(
            user=self.user,
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()
        return self._is_admin

    def _is_superuser(self) -> bool:
        return bool(self.user.is_superuser)

    def _is_privileged(self) -> bool:
        return self._is_superuser() or self._is_portal_admin()

    def _is_root_role(self) -> bool:
        """Role raiz — imutável e protegida."""
        return self.role.codigoperfil == "PORTAL_ADMIN"

    def _get_actor_role_in_same_app(self):
        """Cache do UserRole do ator na mesma aplicação da role alvo."""
        if self._actor_role_in_same_app is not None:
            return self._actor_role_in_same_app

        self._actor_role_in_same_app = (
            UserRole.objects.filter(
                user=self.user,
                aplicacao=self.role.aplicacao,
            )
            .select_related("role")
            .first()
        )
        return self._actor_role_in_same_app

    def _role_app_is_blocked(self) -> bool:
        """
        Retorna True se a app da role está bloqueada.
        role.aplicacao=None (role global) → False (sem restrição de app).
        """
        return bool(self.role.aplicacao and self.role.aplicacao.isappbloqueada)

    def _role_app_is_production_ready(self) -> bool:
        """
        Retorna True se a app da role está pronta para produção.
        role.aplicacao=None (role global) → True (sem restrição de app).
        Uma role global não está vinculada a nenhuma app específica, portanto
        a verificação de isappproductionready não se aplica.
        """
        if self.role.aplicacao is None:
            return True
        return bool(self.role.aplicacao.isappproductionready)
