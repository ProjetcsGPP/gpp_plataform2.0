"""
ApplicationPolicy

Responsabilidade:
    Encapsula as regras de autorização sobre a entidade Aplicacao.
    Domínio puro — sem conhecimento de request, DRF ou views.

Regras centrais:
  - Criar e alterar Aplicacao: apenas PORTAL_ADMIN ou SuperUser.
  - Usuários comuns: somente leitura de apps não bloqueadas e prontas
    para produção onde possuem UserRole.
  - isappbloqueada=True bloqueia QUALQUER operação de usuário comum,
    independentemente de isappproductionready.
  - isappproductionready=False impede visualização por usuários comuns
    mesmo que não esteja bloqueada (app em homologação).

Usage:
    policy = ApplicationPolicy(user, aplicacao)
    policy.can_view_application()
    policy.can_manage_application()
    policy.can_block_application()
    policy.can_assign_role_in_application()
    policy.can_remove_role_from_application()
"""

import logging

security_logger = logging.getLogger("gpp.security")


class ApplicationPolicy:
    """
    Camada de domínio: todas as regras de autorização sobre Aplicacao.

    Recebe o `user` (objeto Django) e a `aplicacao` (instância do model).
    Nenhuma dependência de infraestrutura (request, DRF, cache global).
    O cache de instância (_is_admin, _user_role_in_app) é local ao ciclo
    de vida do objeto.
    """

    def __init__(self, user, aplicacao):
        self.user = user
        self.aplicacao = aplicacao
        self._is_admin = None
        self._user_role_in_app = None

    # ── API pública ────────────────────────────────────────────

    def can_view_application(self) -> bool:
        """
        PORTAL_ADMIN e SuperUser: sempre True (precisam ver apps bloqueadas
        para poder gerenciá-las).
        Usuário comum:
          - isappbloqueada=True → deny (reason: app_blocked)
          - isappproductionready=False → deny (reason: app_not_production_ready)
          - Sem UserRole nessa app → deny (reason: no_role_in_app)
          - Passou tudo → True
        """
        app_code = self._app_code()

        if self._is_privileged():
            security_logger.info(
                "AUTHZ_APP_VIEW_ALLOW user_id=%s app=%s reason=privileged",
                self.user.id,
                app_code,
            )
            return True

        if self._app_is_blocked():
            security_logger.warning(
                "AUTHZ_APP_VIEW_DENY user_id=%s app=%s reason=app_blocked",
                self.user.id,
                app_code,
            )
            return False

        if not self._app_is_production_ready():
            security_logger.warning(
                "AUTHZ_APP_VIEW_DENY user_id=%s app=%s reason=app_not_production_ready",
                self.user.id,
                app_code,
            )
            return False

        if self._get_user_role_in_app() is None:
            security_logger.warning(
                "AUTHZ_APP_VIEW_DENY user_id=%s app=%s reason=no_role_in_app",
                self.user.id,
                app_code,
            )
            return False

        security_logger.info(
            "AUTHZ_APP_VIEW_ALLOW user_id=%s app=%s reason=has_role_in_app",
            self.user.id,
            app_code,
        )
        return True

    def can_manage_application(self) -> bool:
        """
        Criar, editar campos, alterar flags de uma Aplicacao.
        Apenas PORTAL_ADMIN ou SuperUser.
        reason: not_portal_admin
        """
        app_code = self._app_code()

        if self._is_privileged():
            security_logger.info(
                "AUTHZ_APP_MANAGE_ALLOW user_id=%s app=%s reason=privileged",
                self.user.id,
                app_code,
            )
            return True

        security_logger.warning(
            "AUTHZ_APP_MANAGE_DENY user_id=%s app=%s reason=not_portal_admin",
            self.user.id,
            app_code,
        )
        return False

    def can_block_application(self) -> bool:
        """
        Ativar/desativar isappbloqueada.
        Apenas PORTAL_ADMIN ou SuperUser.
        Proteção extra: não pode bloquear a própria app do portal
        (codigointerno="PORTAL") — isso bloquearia o sistema inteiro.
        reason: not_portal_admin | cannot_block_portal_app
        """
        app_code = self._app_code()

        if not self._is_privileged():
            security_logger.warning(
                "AUTHZ_APP_BLOCK_DENY user_id=%s app=%s reason=not_portal_admin",
                self.user.id,
                app_code,
            )
            return False

        if getattr(self.aplicacao, "codigointerno", None) == "PORTAL":
            security_logger.warning(
                "AUTHZ_APP_BLOCK_DENY user_id=%s app=%s reason=cannot_block_portal_app",
                self.user.id,
                app_code,
            )
            return False

        security_logger.info(
            "AUTHZ_APP_BLOCK_ALLOW user_id=%s app=%s reason=privileged",
            self.user.id,
            app_code,
        )
        return True

    def can_set_production_ready(self) -> bool:
        """
        Alterar isappproductionready.
        Apenas PORTAL_ADMIN ou SuperUser.
        reason: not_portal_admin
        """
        app_code = self._app_code()

        if self._is_privileged():
            security_logger.info(
                "AUTHZ_APP_SET_PROD_ALLOW user_id=%s app=%s reason=privileged",
                self.user.id,
                app_code,
            )
            return True

        security_logger.warning(
            "AUTHZ_APP_SET_PROD_DENY user_id=%s app=%s reason=not_portal_admin",
            self.user.id,
            app_code,
        )
        return False

    def can_assign_role_in_application(self) -> bool:
        """
        Criar UserRole nesta aplicação para qualquer usuário.
        Apenas PORTAL_ADMIN ou SuperUser.
        Regra adicional: a app deve estar isappproductionready=True
        E isappbloqueada=False para aceitar novos vínculos.
        reason: not_portal_admin | app_blocked | app_not_production_ready
        """
        app_code = self._app_code()

        if not self._is_privileged():
            security_logger.warning(
                "AUTHZ_APP_ASSIGN_ROLE_DENY user_id=%s app=%s reason=not_portal_admin",
                self.user.id,
                app_code,
            )
            return False

        if self._app_is_blocked():
            security_logger.warning(
                "AUTHZ_APP_ASSIGN_ROLE_DENY user_id=%s app=%s reason=app_blocked",
                self.user.id,
                app_code,
            )
            return False

        if not self._app_is_production_ready():
            security_logger.warning(
                "AUTHZ_APP_ASSIGN_ROLE_DENY user_id=%s app=%s reason=app_not_production_ready",
                self.user.id,
                app_code,
            )
            return False

        security_logger.info(
            "AUTHZ_APP_ASSIGN_ROLE_ALLOW user_id=%s app=%s reason=privileged_app_ready",
            self.user.id,
            app_code,
        )
        return True

    def can_remove_role_from_application(self) -> bool:
        """
        Remover UserRole desta aplicação.
        Apenas PORTAL_ADMIN ou SuperUser.
        DIFERENTE de can_assign: remoção é permitida mesmo com app bloqueada
        (precisa poder remover acessos durante bloqueio).
        reason: not_portal_admin
        """
        app_code = self._app_code()

        if self._is_privileged():
            security_logger.info(
                "AUTHZ_APP_REMOVE_ROLE_ALLOW user_id=%s app=%s reason=privileged",
                self.user.id,
                app_code,
            )
            return True

        security_logger.warning(
            "AUTHZ_APP_REMOVE_ROLE_DENY user_id=%s app=%s reason=not_portal_admin",
            self.user.id,
            app_code,
        )
        return False

    # ── Helpers privados ───────────────────────────────────────

    def _is_portal_admin(self) -> bool:
        """Cópia isolada — não importar de UserPolicy."""
        if self._is_admin is not None:
            return self._is_admin
        from apps.accounts.models import UserRole
        self._is_admin = UserRole.objects.filter(
            user=self.user,
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()
        return self._is_admin

    def _is_superuser(self) -> bool:
        return bool(self.user.is_superuser)

    def _is_privileged(self) -> bool:
        """PORTAL_ADMIN ou SuperUser — bypass total."""
        return self._is_portal_admin() or self._is_superuser()

    def _get_user_role_in_app(self):
        """Cache de instância do UserRole do ator nesta aplicação."""
        if self._user_role_in_app is not None:
            return self._user_role_in_app
        from apps.accounts.models import UserRole
        self._user_role_in_app = UserRole.objects.filter(
            user=self.user,
            aplicacao=self.aplicacao,
        ).select_related("role").first()
        return self._user_role_in_app

    def _app_is_blocked(self) -> bool:
        return bool(self.aplicacao.isappbloqueada)

    def _app_is_production_ready(self) -> bool:
        return bool(self.aplicacao.isappproductionready)

    def _app_code(self) -> str:
        """Retorna codigointerno ou repr da app para uso nos logs."""
        return getattr(self.aplicacao, "codigointerno", None) or str(self.aplicacao)
