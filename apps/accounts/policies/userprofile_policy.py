"""
UserProfilePolicy

Responsabilidade:
    Encapsula as regras de autorização sobre a entidade UserProfile.
    Domínio puro — sem conhecimento de request, DRF ou views.

    Esta Policy centraliza a lógica que estava dispersa entre
    UserProfileViewSet, AuthorizationService e CanEditUser permission.

Regras centrais:
  - Auto-edição (profile.user == actor): sempre permitida para campos
    não-sensíveis. Campos sensíveis (classificacao_usuario, status_usuario)
    exigem privilégio.
  - Edição de perfil alheio: requer pode_editar_usuario=True E
    interseção de aplicações entre ator e alvo.
  - Alterar classificacao_usuario: apenas PORTAL_ADMIN ou SuperUser
    (pois altera o nível de poder do usuário no sistema).
  - Alterar status_usuario: apenas PORTAL_ADMIN ou SuperUser
    (ativar/inativar usuário é operação administrativa).
  - PORTAL_ADMIN e SuperUser: bypass total em qualquer operação.

Usage:
    policy = UserProfilePolicy(actor, profile)
    policy.can_view_profile()
    policy.can_edit_profile()
    policy.can_change_classificacao()
    policy.can_change_status()
    policy.can_view_all_profiles()
"""

import logging

security_logger = logging.getLogger("gpp.security")


class UserProfilePolicy:
    def __init__(self, actor, profile):
        """
        actor: auth.User — usuário realizando a ação
        profile: UserProfile — perfil alvo da operação
        """
        self.actor = actor
        self.profile = profile
        self._is_admin = None
        self._actor_apps = None
        self._actor_classificacao = None

    # ── API pública ────────────────────────────────────────────

    def can_view_profile(self) -> bool:
        """
        PORTAL_ADMIN / SuperUser: True (qualquer profile).
        Próprio profile: True.
        Gestor (pode_editar_usuario=True): True se interseção de apps.
        Demais: False, reason=no_permission
        """
        if self._is_privileged():
            security_logger.info(
                "AUTHZ_PROFILE_VIEW_ALLOW actor_id=%s target_user_id=%s reason=privileged",
                self.actor.id,
                self.profile.user_id,
            )
            return True

        if self._is_own_profile():
            security_logger.info(
                "AUTHZ_PROFILE_VIEW_ALLOW actor_id=%s target_user_id=%s reason=own_profile",
                self.actor.id,
                self.profile.user_id,
            )
            return True

        if self._can_edit_users():
            if self._has_application_intersection():
                security_logger.info(
                    "AUTHZ_PROFILE_VIEW_ALLOW actor_id=%s target_user_id=%s reason=gestor_app_intersection",
                    self.actor.id,
                    self.profile.user_id,
                )
                return True
            security_logger.warning(
                "AUTHZ_PROFILE_VIEW_DENY actor_id=%s target_user_id=%s reason=no_app_intersection",
                self.actor.id,
                self.profile.user_id,
            )
            return False

        security_logger.warning(
            "AUTHZ_PROFILE_VIEW_DENY actor_id=%s target_user_id=%s reason=no_permission",
            self.actor.id,
            self.profile.user_id,
        )
        return False

    def can_edit_profile(self) -> bool:
        """
        PORTAL_ADMIN / SuperUser: True.
        Auto-edição (actor == profile.user): True para campos comuns.
        Gestor (pode_editar_usuario=True): True se interseção de apps.
        Demais: False.
        reason: no_edit_permission | no_app_intersection
        NOTA: campos sensíveis (classificacao, status) têm métodos próprios.
        """
        if self._is_privileged():
            security_logger.info(
                "AUTHZ_PROFILE_EDIT_ALLOW actor_id=%s target_user_id=%s reason=privileged",
                self.actor.id,
                self.profile.user_id,
            )
            return True

        if self._is_own_profile():
            security_logger.info(
                "AUTHZ_PROFILE_EDIT_ALLOW actor_id=%s target_user_id=%s reason=own_profile",
                self.actor.id,
                self.profile.user_id,
            )
            return True

        if not self._can_edit_users():
            security_logger.warning(
                "AUTHZ_PROFILE_EDIT_DENY actor_id=%s target_user_id=%s reason=no_edit_permission",
                self.actor.id,
                self.profile.user_id,
            )
            return False

        if not self._has_application_intersection():
            security_logger.warning(
                "AUTHZ_PROFILE_EDIT_DENY actor_id=%s target_user_id=%s reason=no_app_intersection",
                self.actor.id,
                self.profile.user_id,
            )
            return False

        security_logger.info(
            "AUTHZ_PROFILE_EDIT_ALLOW actor_id=%s target_user_id=%s reason=gestor_app_intersection",
            self.actor.id,
            self.profile.user_id,
        )
        return True

    def can_change_classificacao(self) -> bool:
        """
        Alterar classificacao_usuario é alterar o nível de poder do usuário.
        Apenas PORTAL_ADMIN ou SuperUser.
        reason: not_portal_admin
        """
        if self._is_privileged():
            security_logger.info(
                "AUTHZ_PROFILE_CLASSIFICACAO_ALLOW actor_id=%s target_user_id=%s reason=privileged",
                self.actor.id,
                self.profile.user_id,
            )
            return True

        security_logger.warning(
            "AUTHZ_PROFILE_CLASSIFICACAO_DENY actor_id=%s target_user_id=%s reason=not_portal_admin",
            self.actor.id,
            self.profile.user_id,
        )
        return False

    def can_change_status(self) -> bool:
        """
        Ativar/inativar usuário (status_usuario).
        Apenas PORTAL_ADMIN ou SuperUser.
        reason: not_portal_admin
        """
        if self._is_privileged():
            security_logger.info(
                "AUTHZ_PROFILE_STATUS_ALLOW actor_id=%s target_user_id=%s reason=privileged",
                self.actor.id,
                self.profile.user_id,
            )
            return True

        security_logger.warning(
            "AUTHZ_PROFILE_STATUS_DENY actor_id=%s target_user_id=%s reason=not_portal_admin",
            self.actor.id,
            self.profile.user_id,
        )
        return False

    def can_view_all_profiles(self) -> bool:
        """
        Listar profiles de todos os usuários do sistema.
        PORTAL_ADMIN / SuperUser: True.
        Demais: False (veem apenas o próprio via get_queryset filtrado).
        reason: not_portal_admin
        """
        if self._is_privileged():
            security_logger.info(
                "AUTHZ_PROFILE_LIST_ALL_ALLOW actor_id=%s reason=privileged",
                self.actor.id,
            )
            return True

        security_logger.warning(
            "AUTHZ_PROFILE_LIST_ALL_DENY actor_id=%s reason=not_portal_admin",
            self.actor.id,
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
        try:
            return bool(self.actor.is_superuser)
        except AttributeError:
            return False

    def _is_privileged(self) -> bool:
        return self._is_portal_admin() or self._is_superuser()

    def _is_own_profile(self) -> bool:
        try:
            return self.actor.pk == self.profile.user_id
        except AttributeError:
            return False

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
        if not classificacao:
            return False
        try:
            return bool(classificacao.pode_editar_usuario)
        except AttributeError:
            return False

    def _get_actor_applications(self) -> set:
        if self._actor_apps is not None:
            return self._actor_apps
        from apps.accounts.models import UserRole
        self._actor_apps = set(
            UserRole.objects.filter(user=self.actor)
            .values_list("aplicacao_id", flat=True)
        )
        return self._actor_apps

    def _has_application_intersection(self) -> bool:
        from apps.accounts.models import UserRole
        actor_apps = self._get_actor_applications()
        return UserRole.objects.filter(
            user=self.profile.user,
            aplicacao_id__in=actor_apps,
        ).exists()
