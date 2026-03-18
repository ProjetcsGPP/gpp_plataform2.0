"""
SessionPolicy

Responsabilidade:
    Encapsula as regras de autorização sobre AccountsSession.
    Sessões JWT são dados sensíveis de segurança — ownership rigoroso.

Regras centrais:
  - Usuário vê/revoga apenas as próprias sessões.
  - PORTAL_ADMIN / SuperUser: vê e revoga qualquer sessão.
  - Revogar todas as sessões de outro usuário: apenas PORTAL_ADMIN / SuperUser.
  - Sessão já revogada não pode ser "re-revogada" (idempotência com deny informativo).

Usage:
    policy = SessionPolicy(actor, session)
    policy.can_view_session()
    policy.can_revoke_session()
    policy.can_revoke_all_sessions(target_user)
"""

import logging

security_logger = logging.getLogger("gpp.security")


class SessionPolicy:
    def __init__(self, actor, session):
        """
        actor: auth.User
        session: AccountsSession alvo
        """
        self.actor = actor
        self.session = session
        self._is_admin = None

    # ── API pública ────────────────────────────────────────────

    def can_view_session(self) -> bool:
        """
        PORTAL_ADMIN / SuperUser: True.
        session.user == actor: True.
        Demais: False, reason=not_own_session
        """
        if self._is_privileged():
            return True
        if self._is_own_session():
            return True
        security_logger.warning(
            "can_view_session denied",
            extra={"actor": self.actor.pk, "session_user": self.session.user_id, "reason": "not_own_session"},
        )
        return False

    def can_revoke_session(self) -> bool:
        """
        PORTAL_ADMIN / SuperUser: True.
        session.user == actor: True.
        session.revoked == True → False, reason=already_revoked
        Demais: False, reason=not_own_session
        """
        if self.session.revoked:
            security_logger.warning(
                "can_revoke_session denied",
                extra={"actor": self.actor.pk, "session_user": self.session.user_id, "reason": "already_revoked"},
            )
            return False
        if self._is_privileged():
            return True
        if self._is_own_session():
            return True
        security_logger.warning(
            "can_revoke_session denied",
            extra={"actor": self.actor.pk, "session_user": self.session.user_id, "reason": "not_own_session"},
        )
        return False

    def can_revoke_all_sessions(self, target_user) -> bool:
        """
        Revogar TODAS as sessões de um target_user.
        PORTAL_ADMIN / SuperUser: True para qualquer target.
        actor == target_user: True (pode encerrar todas as próprias sessões).
        Demais: False, reason=not_portal_admin
        """
        if self._is_privileged():
            return True
        if self.actor.pk == target_user.pk:
            return True
        security_logger.warning(
            "can_revoke_all_sessions denied",
            extra={"actor": self.actor.pk, "target_user": target_user.pk, "reason": "not_portal_admin"},
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

    def _is_own_session(self) -> bool:
        return self.actor.pk == self.session.user_id
