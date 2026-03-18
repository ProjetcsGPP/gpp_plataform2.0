"""
AttributePolicy

Responsabilidade:
    Encapsula as regras de autorização sobre Attribute (ABAC).
    Atributos ABAC são dados sensíveis que podem condicionar acesso
    em outros sistemas — tratados com rigor de ownership.

Regras centrais:
  - Visualizar: PORTAL_ADMIN/SuperUser veem todos.
    Usuário vê apenas os próprios atributos.
    Gestores com interseção de app veem atributos de usuários da mesma app.
  - Criar: apenas PORTAL_ADMIN ou SuperUser,
    e apenas para apps não bloqueadas e prontas para produção.
  - Editar/Deletar: apenas PORTAL_ADMIN ou SuperUser.

Usage:
    policy = AttributePolicy(actor, attribute)
    policy.can_view_attribute()
    policy.can_create_attribute()
    policy.can_edit_attribute()
    policy.can_delete_attribute()
"""

import logging

security_logger = logging.getLogger("gpp.security")


class AttributePolicy:
    def __init__(self, actor, attribute):
        """
        actor: auth.User
        attribute: Attribute alvo
        """
        self.actor = actor
        self.attribute = attribute
        self._is_admin = None
        self._actor_apps = None

    # ── API pública ────────────────────────────────────────────

    def can_view_attribute(self) -> bool:
        """
        PORTAL_ADMIN / SuperUser: True.
        attribute.user == actor: True (próprio atributo).
        Gestor (pode_editar_usuario=True) com UserRole na mesma app
        do attribute: True.
        Demais: False, reason=not_own_attribute | no_role_in_same_app
        """
        if self._is_privileged():
            return True
        if self._is_own_attribute():
            return True
        if self._actor_is_manager_in_attribute_app():
            return True
        security_logger.warning(
            "can_view_attribute denied",
            extra={"actor": self.actor.pk, "attribute_user": self.attribute.user_id, "reason": "not_own_attribute"},
        )
        return False

    def can_create_attribute(self) -> bool:
        """
        Apenas PORTAL_ADMIN ou SuperUser.
        Se attribute.aplicacao não é None:
          - isappbloqueada=True → deny (reason: app_blocked)
          - isappproductionready=False → deny (reason: app_not_production_ready)
        reason: not_portal_admin | app_blocked | app_not_production_ready
        """
        if not self._is_privileged():
            security_logger.warning(
                "can_create_attribute denied",
                extra={"actor": self.actor.pk, "reason": "not_portal_admin"},
            )
            return False
        if self.attribute.aplicacao is not None:
            if self._app_is_blocked():
                security_logger.warning(
                    "can_create_attribute denied",
                    extra={"actor": self.actor.pk, "reason": "app_blocked"},
                )
                return False
            if not self._app_is_production_ready():
                security_logger.warning(
                    "can_create_attribute denied",
                    extra={"actor": self.actor.pk, "reason": "app_not_production_ready"},
                )
                return False
        return True

    def can_edit_attribute(self) -> bool:
        """
        Apenas PORTAL_ADMIN ou SuperUser.
        reason: not_portal_admin
        """
        if self._is_privileged():
            return True
        security_logger.warning(
            "can_edit_attribute denied",
            extra={"actor": self.actor.pk, "reason": "not_portal_admin"},
        )
        return False

    def can_delete_attribute(self) -> bool:
        """
        Apenas PORTAL_ADMIN ou SuperUser.
        reason: not_portal_admin
        """
        if self._is_privileged():
            return True
        security_logger.warning(
            "can_delete_attribute denied",
            extra={"actor": self.actor.pk, "reason": "not_portal_admin"},
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

    def _is_own_attribute(self) -> bool:
        return self.actor.pk == self.attribute.user_id

    def _get_actor_applications(self) -> set:
        if self._actor_apps is not None:
            return self._actor_apps
        from apps.accounts.models import UserRole
        self._actor_apps = set(
            UserRole.objects.filter(user=self.actor)
            .values_list("aplicacao_id", flat=True)
        )
        return self._actor_apps

    def _actor_has_role_in_attribute_app(self) -> bool:
        if self.attribute.aplicacao_id is None:
            return False
        return self.attribute.aplicacao_id in self._get_actor_applications()

    def _actor_is_manager_in_attribute_app(self) -> bool:
        """Retorna True se o actor possui pode_editar_usuario=True
        em alguma UserRole vinculada à mesma app do atributo.
        """
        if self.attribute.aplicacao_id is None:
            return False
        from apps.accounts.models import UserRole
        return UserRole.objects.filter(
            user=self.actor,
            aplicacao_id=self.attribute.aplicacao_id,
            pode_editar_usuario=True,
        ).exists()

    def _app_is_blocked(self) -> bool:
        return bool(
            self.attribute.aplicacao and self.attribute.aplicacao.isappbloqueada
        )

    def _app_is_production_ready(self) -> bool:
        return bool(
            self.attribute.aplicacao and self.attribute.aplicacao.isappproductionready
        )
