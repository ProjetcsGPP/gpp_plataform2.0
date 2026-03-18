"""
UserRolePolicy

Responsabilidade:
    Encapsula as regras de autorização sobre a entidade UserRole.
    UserRole representa a concessão de acesso de um usuário a uma aplicação.
    Domínio puro — sem conhecimento de request, DRF ou views.

Regras centrais:
  - Criar UserRole: apenas PORTAL_ADMIN ou SuperUser, e apenas em apps
    isappbloqueada=False E isappproductionready=True.
  - Deletar UserRole: apenas PORTAL_ADMIN ou SuperUser.
    Ninguém remove o próprio UserRole (nem PORTAL_ADMIN).
    Remoção é permitida mesmo com app bloqueada.
  - Visualizar UserRole: PORTAL_ADMIN/SuperUser veem todos.
    Gestores (pode_editar_usuario=True) veem vínculos de usuários
    na mesma aplicação.
    Usuário comum vê apenas os próprios vínculos.

Notas de implementação:
  - userrole.aplicacao=None indica um vínculo global (ex: PORTAL_ADMIN) não
    vinculado a nenhuma app específica. Checks de isappbloqueada e
    isappproductionready não se aplicam a vínculos globais —
    ausência de app = ausência de restrição de app.

Usage:
    policy = UserRolePolicy(actor, userrole)
    policy.can_view_userrole()
    policy.can_create_userrole()
    policy.can_delete_userrole()
    policy.can_view_userroles_of_user(target_user)
"""

import logging

security_logger = logging.getLogger("gpp.security")


class UserRolePolicy:
    def __init__(self, actor, userrole):
        """
        actor: auth.User — usuário realizando a ação
        userrole: UserRole — vínculo alvo da operação
        """
        self.actor = actor
        self.userrole = userrole
        self._is_admin = None
        self._actor_apps = None
        self._actor_classificacao = None

    # ── API pública ────────────────────────────────────────────

    def can_view_userrole(self) -> bool:
        """
        PORTAL_ADMIN / SuperUser: True.
        Próprio vínculo (userrole.user == actor): True.
        Gestor (pode_editar_usuario=True) com UserRole na mesma app: True.
        Demais: False.
        reason: no_permission | no_role_in_same_app
        """
        if self._is_privileged():
            return True

        if self._is_own_userrole():
            return True

        if self._can_edit_users():
            if self._actor_has_role_in_same_app():
                return True
            security_logger.warning(
                "can_view_userrole denied",
                extra={
                    "actor_id": self.actor.id,
                    "userrole_id": getattr(self.userrole, "pk", None),
                    "reason": "no_role_in_same_app",
                },
            )
            return False

        security_logger.warning(
            "can_view_userrole denied",
            extra={
                "actor_id": self.actor.id,
                "userrole_id": getattr(self.userrole, "pk", None),
                "reason": "no_permission",
            },
        )
        return False

    def can_create_userrole(self) -> bool:
        """
        Apenas PORTAL_ADMIN ou SuperUser.
        Restrições da aplicação alvo:
          - isappbloqueada=True → deny (reason: app_blocked)
          - isappproductionready=False → deny (reason: app_not_production_ready)
          - userrole.aplicacao=None (vínculo global) → sem restrição de app
        Restrição da role alvo:
          - codigoperfil="PORTAL_ADMIN" → somente SuperUser pode atribuir
        reason: not_portal_admin | app_blocked | app_not_production_ready
                | cannot_assign_admin_role
        """
        if not self._is_privileged():
            security_logger.warning(
                "can_create_userrole denied",
                extra={
                    "actor_id": self.actor.id,
                    "reason": "not_portal_admin",
                },
            )
            return False

        if self._app_is_blocked():
            security_logger.warning(
                "can_create_userrole denied",
                extra={
                    "actor_id": self.actor.id,
                    "userrole_aplicacao_id": getattr(self.userrole.aplicacao, "pk", None),
                    "reason": "app_blocked",
                },
            )
            return False

        if not self._app_is_production_ready():
            security_logger.warning(
                "can_create_userrole denied",
                extra={
                    "actor_id": self.actor.id,
                    "userrole_aplicacao_id": getattr(self.userrole.aplicacao, "pk", None),
                    "reason": "app_not_production_ready",
                },
            )
            return False

        if self._is_admin_role() and not self._is_superuser():
            security_logger.warning(
                "can_create_userrole denied",
                extra={
                    "actor_id": self.actor.id,
                    "role_codigoperfil": self.userrole.role.codigoperfil,
                    "reason": "cannot_assign_admin_role",
                },
            )
            return False

        return True

    def can_delete_userrole(self) -> bool:
        """
        Apenas PORTAL_ADMIN ou SuperUser.
        Proteção de auto-remoção: actor == userrole.user → NUNCA
          (ninguém remove o próprio acesso, nem PORTAL_ADMIN)
        Remoção de UserRole com codigoperfil="PORTAL_ADMIN":
          somente SuperUser pode revogar
        Remoção permitida mesmo com app bloqueada.
        reason: not_portal_admin | cannot_revoke_own_role
                | cannot_revoke_admin_role
        """
        # Auto-remoção tem precedência absoluta
        if self._is_own_userrole():
            security_logger.warning(
                "can_delete_userrole denied",
                extra={
                    "actor_id": self.actor.id,
                    "userrole_id": getattr(self.userrole, "pk", None),
                    "reason": "cannot_revoke_own_role",
                },
            )
            return False

        if not self._is_privileged():
            security_logger.warning(
                "can_delete_userrole denied",
                extra={
                    "actor_id": self.actor.id,
                    "reason": "not_portal_admin",
                },
            )
            return False

        if self._is_admin_role() and not self._is_superuser():
            security_logger.warning(
                "can_delete_userrole denied",
                extra={
                    "actor_id": self.actor.id,
                    "userrole_id": getattr(self.userrole, "pk", None),
                    "reason": "cannot_revoke_admin_role",
                },
            )
            return False

        return True

    def can_view_userroles_of_user(self, target_user) -> bool:
        """
        Listar TODOS os vínculos (UserRoles) de um usuário específico.
        PORTAL_ADMIN / SuperUser: True.
        Actor == target_user: True (ver os próprios vínculos).
        Gestor com interseção de apps com target_user: True.
        Demais: False.
        reason: no_permission | no_app_intersection
        """
        if self._is_privileged():
            return True

        if self.actor.pk == target_user.pk:
            return True

        if self._can_edit_users():
            if self._has_intersection_with_target(target_user):
                return True
            security_logger.warning(
                "can_view_userroles_of_user denied",
                extra={
                    "actor_id": self.actor.id,
                    "target_user_id": target_user.id,
                    "reason": "no_app_intersection",
                },
            )
            return False

        security_logger.warning(
            "can_view_userroles_of_user denied",
            extra={
                "actor_id": self.actor.id,
                "target_user_id": target_user.id,
                "reason": "no_permission",
            },
        )
        return False

    # ── Helpers privados ───────────────────────────────────────

    def _is_portal_admin(self) -> bool:
        if self._is_admin is not None:
            return self._is_admin
        from apps.accounts.models import UserRole
        self._is_admin = UserRole.objects.filter(
            user=self.actor,
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()
        return self._is_admin

    def _is_superuser(self) -> bool:
        return bool(self.actor.is_superuser)

    def _is_privileged(self) -> bool:
        return self._is_portal_admin() or self._is_superuser()

    def _is_own_userrole(self) -> bool:
        return self.actor.pk == self.userrole.user_id

    def _is_admin_role(self) -> bool:
        return self.userrole.role.codigoperfil == "PORTAL_ADMIN"

    def _get_actor_classificacao(self):
        if self._actor_classificacao is not None:
            return self._actor_classificacao
        try:
            self._actor_classificacao = self.actor.profile.classificacao_usuario
        except AttributeError:
            self._actor_classificacao = None
        return self._actor_classificacao

    def _can_edit_users(self) -> bool:
        classificacao = self._get_actor_classificacao()
        return bool(classificacao and classificacao.pode_editar_usuario)

    def _get_actor_applications(self) -> set:
        if self._actor_apps is not None:
            return self._actor_apps
        from apps.accounts.models import UserRole
        self._actor_apps = set(
            UserRole.objects.filter(user=self.actor)
            .values_list("aplicacao_id", flat=True)
        )
        return self._actor_apps

    def _actor_has_role_in_same_app(self) -> bool:
        return self.userrole.aplicacao_id in self._get_actor_applications()

    def _has_intersection_with_target(self, target_user) -> bool:
        from apps.accounts.models import UserRole
        actor_apps = self._get_actor_applications()
        return UserRole.objects.filter(
            user=target_user,
            aplicacao_id__in=actor_apps,
        ).exists()

    def _app_is_blocked(self) -> bool:
        """
        Retorna True se a app do vínculo está bloqueada.
        userrole.aplicacao=None (vínculo global) → False (sem restrição de app).
        """
        return bool(
            self.userrole.aplicacao and self.userrole.aplicacao.isappbloqueada
        )

    def _app_is_production_ready(self) -> bool:
        """
        Retorna True se a app do vínculo está pronta para produção.
        userrole.aplicacao=None (vínculo global) → True (sem restrição de app).
        Um vínculo global não está vinculado a nenhuma app específica, portanto
        a verificação de isappproductionready não se aplica.
        """
        if self.userrole.aplicacao is None:
            return True
        return bool(self.userrole.aplicacao.isappproductionready)
