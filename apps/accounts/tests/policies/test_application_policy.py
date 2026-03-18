"""
Testes de ApplicationPolicy.

Cobertura:
  - can_view_application
  - can_manage_application
  - can_block_application
  - can_assign_role_in_application
  - can_remove_role_from_application

Fixtures definidas em conftest.py (model_bakery).
"""
import pytest
from apps.accounts.policies import ApplicationPolicy


# ─────────────────────────────────────────────────────────────────────────────
# can_view_application
# ─────────────────────────────────────────────────────────────────────────────

class TestCanViewApplication:

    def test_portal_admin_can_view_blocked_app(
        self, portal_admin_user, app_blocked
    ):
        """Admin vê app bloqueada — necessário para gestão."""
        policy = ApplicationPolicy(portal_admin_user, app_blocked)
        assert policy.can_view_application() is True

    def test_portal_admin_can_view_not_ready_app(
        self, portal_admin_user, app_not_ready
    ):
        """Admin vê app em homologação."""
        policy = ApplicationPolicy(portal_admin_user, app_not_ready)
        assert policy.can_view_application() is True

    def test_superuser_can_view_blocked_app(self, superuser, app_blocked):
        """SuperUser tem bypass total."""
        policy = ApplicationPolicy(superuser, app_blocked)
        assert policy.can_view_application() is True

    def test_regular_user_with_role_can_view_ready_unblocked_app(
        self, regular_user, app_ready
    ):
        """Usuário com role na app pronta e não bloqueada pode ver."""
        policy = ApplicationPolicy(regular_user, app_ready)
        assert policy.can_view_application() is True

    def test_regular_user_cannot_view_blocked_app(
        self, regular_user, app_blocked, caplog
    ):
        """App bloqueada → deny, log reason=app_blocked."""
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(regular_user, app_blocked)
            result = policy.can_view_application()

        assert result is False
        assert "reason=app_blocked" in caplog.text

    def test_regular_user_cannot_view_not_ready_app(
        self, regular_user, app_not_ready, caplog
    ):
        """App não production-ready → deny, log reason=app_not_production_ready."""
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(regular_user, app_not_ready)
            result = policy.can_view_application()

        assert result is False
        assert "reason=app_not_production_ready" in caplog.text

    def test_regular_user_without_role_cannot_view_app(
        self, db, app_ready, caplog
    ):
        """Usuário sem role na app → deny, log reason=no_role_in_app."""
        import logging
        from model_bakery import baker

        user_no_role = baker.make("accounts.User", is_superuser=False, is_active=True)

        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(user_no_role, app_ready)
            result = policy.can_view_application()

        assert result is False
        assert "reason=no_role_in_app" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# can_manage_application
# ─────────────────────────────────────────────────────────────────────────────

class TestCanManageApplication:

    def test_portal_admin_can_manage(self, portal_admin_user, app_ready):
        policy = ApplicationPolicy(portal_admin_user, app_ready)
        assert policy.can_manage_application() is True

    def test_superuser_can_manage(self, superuser, app_ready):
        policy = ApplicationPolicy(superuser, app_ready)
        assert policy.can_manage_application() is True

    def test_regular_user_cannot_manage(self, regular_user, app_ready, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(regular_user, app_ready)
            result = policy.can_manage_application()

        assert result is False
        assert "reason=not_portal_admin" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# can_block_application
# ─────────────────────────────────────────────────────────────────────────────

class TestCanBlockApplication:

    def test_portal_admin_can_block_regular_app(
        self, portal_admin_user, app_ready
    ):
        policy = ApplicationPolicy(portal_admin_user, app_ready)
        assert policy.can_block_application() is True

    def test_superuser_can_block_regular_app(self, superuser, app_ready):
        policy = ApplicationPolicy(superuser, app_ready)
        assert policy.can_block_application() is True

    def test_cannot_block_portal_app(
        self, portal_admin_user, app_portal, caplog
    ):
        """Bloqueio da app PORTAL deve ser vetado mesmo para admin."""
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(portal_admin_user, app_portal)
            result = policy.can_block_application()

        assert result is False
        assert "reason=cannot_block_portal_app" in caplog.text

    def test_regular_user_cannot_block(self, regular_user, app_ready, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(regular_user, app_ready)
            result = policy.can_block_application()

        assert result is False
        assert "reason=not_portal_admin" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# can_assign_role_in_application
# ─────────────────────────────────────────────────────────────────────────────

class TestCanAssignRole:

    def test_portal_admin_can_assign_role_in_ready_app(
        self, portal_admin_user, app_ready
    ):
        policy = ApplicationPolicy(portal_admin_user, app_ready)
        assert policy.can_assign_role_in_application() is True

    def test_portal_admin_cannot_assign_role_in_blocked_app(
        self, portal_admin_user, app_blocked, caplog
    ):
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(portal_admin_user, app_blocked)
            result = policy.can_assign_role_in_application()

        assert result is False
        assert "reason=app_blocked" in caplog.text

    def test_portal_admin_cannot_assign_role_in_not_ready_app(
        self, portal_admin_user, app_not_ready, caplog
    ):
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(portal_admin_user, app_not_ready)
            result = policy.can_assign_role_in_application()

        assert result is False
        assert "reason=app_not_production_ready" in caplog.text

    def test_regular_user_cannot_assign_role(
        self, regular_user, app_ready, caplog
    ):
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(regular_user, app_ready)
            result = policy.can_assign_role_in_application()

        assert result is False
        assert "reason=not_portal_admin" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# can_remove_role_from_application
# ─────────────────────────────────────────────────────────────────────────────

class TestCanRemoveRole:

    def test_portal_admin_can_remove_role_even_from_blocked_app(
        self, portal_admin_user, app_blocked
    ):
        """Remoção de acesso deve ser possível mesmo com app bloqueada."""
        policy = ApplicationPolicy(portal_admin_user, app_blocked)
        assert policy.can_remove_role_from_application() is True

    def test_regular_user_cannot_remove_role(
        self, regular_user, app_ready, caplog
    ):
        import logging
        with caplog.at_level(logging.WARNING, logger="gpp.security"):
            policy = ApplicationPolicy(regular_user, app_ready)
            result = policy.can_remove_role_from_application()

        assert result is False
        assert "reason=not_portal_admin" in caplog.text
