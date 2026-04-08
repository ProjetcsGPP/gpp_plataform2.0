"""
UserPolicy

Responsabilidade:
    Encapsula as regras de negócio de autorização de usuários como camada
    de domínio puro. Não conhece request, DRF nem views.

Usage:
    Pode ser utilizada diretamente ou via AuthorizationService.

    policy = UserPolicy(user)
    policy.can_create_user()
    policy.can_edit_user()
    policy.can_create_user_in_application(aplicacao)
    policy.can_edit_target_user(target_user)
    policy.can_manage_target_user(target_user)

ADR-PERM-01:
    auth_user_user_permissions é a única fonte de verdade para autorização
    em runtime. can_create_user() e can_edit_user() lêem essa tabela via
    user.has_perm(), nunca via classificacao_usuario (campo global sem
    contexto de aplicação).
"""

import logging

security_logger = logging.getLogger("gpp.security")


class UserPolicy:
    """
    Camada de domínio: todas as regras de autorização de usuários.

    Recebe apenas o `user` (objeto Django). Nenhuma dependência de
    infraestrutura (request, DRF, cache global). O cache de instância
    (_is_admin, _user_apps) é local ao ciclo de vida do objeto.
    """

    def __init__(self, user):
        self.user = user
        self._is_admin = None
        self._user_apps = None

    # ─────────────────────────────────────────────
    # API pública da Policy
    # ─────────────────────────────────────────────

    def can_create_user(self) -> bool:
        """
        Verifica se o usuário tem permissão global para criar usuários.

        Fonte de verdade: auth_user_user_permissions via user.has_perm().
        A permissão 'auth.add_user' é materializada em auth_user_user_permissions
        por sync_user_permissions() a partir do grupo associado ao Role do usuário.

        ADR-PERM-01: não usa classificacao_usuario (campo global sem contexto).
        """
        if self.user.is_superuser:
            security_logger.info(
                "AUTHZ_USER_CREATE user_id=%s reason=superuser",
                self.user.id,
            )
            return True

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_USER_CREATE user_id=%s reason=portal_admin",
                self.user.id,
            )
            return True

        # Lê auth_user_user_permissions — única fonte de verdade (ADR-PERM-01)
        result = self.user.has_perm("auth.add_user")

        if result:
            security_logger.info(
                "AUTHZ_USER_CREATE user_id=%s reason=has_perm result=True",
                self.user.id,
            )
        else:
            security_logger.warning(
                "AUTHZ_DENY_USER_CREATE user_id=%s reason=no_perm codename=auth.add_user",
                self.user.id,
            )

        return result

    def can_edit_user(self) -> bool:
        """
        Verifica se o usuário tem permissão global para editar usuários.

        Fonte de verdade: auth_user_user_permissions via user.has_perm().
        A permissão 'auth.change_user' é materializada em auth_user_user_permissions
        por sync_user_permissions() a partir do grupo associado ao Role do usuário.

        ADR-PERM-01: não usa classificacao_usuario (campo global sem contexto).
        """
        if self.user.is_superuser:
            security_logger.info(
                "AUTHZ_USER_EDIT user_id=%s reason=superuser",
                self.user.id,
            )
            return True

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_USER_EDIT user_id=%s reason=portal_admin",
                self.user.id,
            )
            return True

        # Lê auth_user_user_permissions — única fonte de verdade (ADR-PERM-01)
        result = self.user.has_perm("auth.change_user")

        if result:
            security_logger.info(
                "AUTHZ_USER_EDIT user_id=%s reason=has_perm result=True",
                self.user.id,
            )
        else:
            security_logger.warning(
                "AUTHZ_DENY_USER_EDIT user_id=%s reason=no_perm codename=auth.change_user",
                self.user.id,
            )

        return result

    def can_create_user_in_application(self, aplicacao) -> bool:
        """
        Verifica se o usuário pode criar usuários em uma aplicação específica.

        Requer:
          1. can_create_user() → True  (permissão global via has_perm)
          2. UserRole ativo para (user, aplicacao) → tem papel nessa aplicação

        Não verifica group.permissions diretamente — isso violaria ADR-PERM-01.
        """
        app_code = getattr(aplicacao, "codigointerno", None) or str(aplicacao)

        if self.user.is_superuser:
            security_logger.info(
                "AUTHZ_CREATE_IN_APP_ALLOW user_id=%s app=%s reason=superuser",
                self.user.id,
                app_code,
            )
            return True

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_CREATE_IN_APP_ALLOW user_id=%s app=%s reason=portal_admin",
                self.user.id,
                app_code,
            )
            return True

        if not self.can_create_user():
            security_logger.warning(
                "AUTHZ_CREATE_IN_APP_DENY user_id=%s app=%s reason=no_create_permission",
                self.user.id,
                app_code,
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
                app_code,
            )
        else:
            security_logger.warning(
                "AUTHZ_CREATE_IN_APP_DENY user_id=%s app=%s reason=no_role_in_app",
                self.user.id,
                app_code,
            )

        return has_role

    def can_edit_target_user(self, target_user) -> bool:
        """
        Verifica se o usuário pode editar um usuário-alvo específico.

        Requer:
          1. can_edit_user() → True  (permissão global via has_perm)
          2. Interseção de aplicações entre editor e alvo (mesmo contexto de app)
        """
        if self.user.is_superuser:
            security_logger.info(
                "AUTHZ_EDIT_TARGET_ALLOW user_id=%s reason=superuser",
                self.user.id,
            )
            return True

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_EDIT_TARGET_ALLOW user_id=%s target_user_id=%s reason=portal_admin",
                self.user.id,
                target_user.id,
            )
            return True

        if not self.can_edit_user():
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

    def can_manage_target_user(self, target_user) -> bool:
        """
        Verifica se o usuário pode gerenciar (acesso administrativo amplo)
        um usuário-alvo específico.

        Requer:
          1. can_edit_user() → True  (permissão global via has_perm)
          2. Interseção de aplicações entre gestor e alvo (mesmo contexto de app)
        """
        if self.user.is_superuser:
            security_logger.info(
                "AUTHZ_MANAGE_USER_ALLOW user_id=%s reason=superuser",
                self.user.id,
            )
            return True

        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_MANAGE_USER_ALLOW user_id=%s target_user_id=%s reason=portal_admin",
                self.user.id,
                target_user.id,
            )
            return True

        if not self.can_edit_user():
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
    # Helpers privados (domínio puro)
    # ─────────────────────────────────────────────

    def _is_portal_admin(self) -> bool:
        """Cache de instância: evita múltiplas queries na mesma requisição."""
        if self._is_admin is not None:
            return self._is_admin

        from apps.accounts.models import UserRole

        self._is_admin = UserRole.objects.filter(
            user=self.user,
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()

        return self._is_admin

    def _get_classificacao(self):
        """
        Retorna a classificacao_usuario do perfil do usuário.

        .. deprecated::
            Não deve ser usado em can_create_user() nem can_edit_user()
            — substituído por user.has_perm() conforme ADR-PERM-01.
            Mantido para uso residual em outros contextos (ex.: display,
            relatórios) que não envolvam decisão de autorização.
        """
        try:
            return self.user.profile.classificacao_usuario
        except AttributeError:
            return None

    def _get_user_applications(self) -> set:
        """Cache de instância: coleta aplicações do usuário uma única vez."""
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
        """
        Verifica se o usuário e o alvo compartilham ao menos uma aplicação comum.
        Usado por can_edit_target_user() e can_manage_target_user() para garantir
        que o editor/gestor só atue dentro do seu contexto de aplicação.
        """
        from apps.accounts.models import UserRole

        user_apps = self._get_user_applications()

        return UserRole.objects.filter(
            user=target_user,
            aplicacao_id__in=user_apps,
        ).exists()
