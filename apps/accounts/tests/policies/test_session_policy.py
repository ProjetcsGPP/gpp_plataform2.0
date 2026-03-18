"""
Testes para SessionPolicy.

Estratégia: zero banco de dados — MagicMock para todas as entidades.
Patch de UserRole.objects.filter via monkeypatch onde necessário.
"""
from unittest.mock import MagicMock, patch
import pytest

from apps.accounts.policies.session_policy import SessionPolicy


# ── Helpers de fixture ────────────────────────────────────────────────────────

def make_session(user_id, revoked=False):
    session = MagicMock()
    session.user_id = user_id
    session.revoked = revoked
    return session


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def regular_user():
    u = MagicMock()
    u.pk = 20
    u.id = 20
    u.is_superuser = False
    return u


@pytest.fixture
def other_user():
    u = MagicMock()
    u.pk = 30
    u.id = 30
    u.is_superuser = False
    return u


@pytest.fixture
def superuser():
    u = MagicMock()
    u.pk = 10
    u.id = 10
    u.is_superuser = True
    return u


@pytest.fixture
def portal_admin_user():
    u = MagicMock()
    u.pk = 5
    u.id = 5
    u.is_superuser = False
    return u


@pytest.fixture
def own_session(regular_user):
    return make_session(user_id=regular_user.pk, revoked=False)


@pytest.fixture
def other_session(other_user):
    return make_session(user_id=other_user.pk, revoked=False)


@pytest.fixture
def revoked_session(regular_user):
    return make_session(user_id=regular_user.pk, revoked=True)


# ── Patch helper ──────────────────────────────────────────────────────────────

def _patch_is_portal_admin(is_admin: bool):
    """Retorna um patcher para UserRole.objects.filter que controla is_portal_admin."""
    mock_qs = MagicMock()
    mock_qs.exists.return_value = is_admin
    return patch("apps.accounts.policies.session_policy.UserRole.objects.filter", return_value=mock_qs)


# ═══════════════════════════════════════════
# TestCanViewSession
# ═══════════════════════════════════════════

class TestCanViewSession:

    def test_portal_admin_can_view_any_session(self, portal_admin_user, other_session):
        with _patch_is_portal_admin(True):
            policy = SessionPolicy(portal_admin_user, other_session)
            assert policy.can_view_session() is True

    def test_superuser_can_view_any_session(self, superuser, other_session):
        with _patch_is_portal_admin(False):
            policy = SessionPolicy(superuser, other_session)
            assert policy.can_view_session() is True

    def test_user_can_view_own_session(self, regular_user, own_session):
        with _patch_is_portal_admin(False):
            policy = SessionPolicy(regular_user, own_session)
            assert policy.can_view_session() is True

    def test_user_cannot_view_other_session(self, regular_user, other_session):
        with _patch_is_portal_admin(False):
            policy = SessionPolicy(regular_user, other_session)
            result = policy.can_view_session()
        assert result is False


# ═══════════════════════════════════════════
# TestCanRevokeSession
# ═══════════════════════════════════════════

class TestCanRevokeSession:

    def test_portal_admin_can_revoke_any_session(self, portal_admin_user, other_session):
        with _patch_is_portal_admin(True):
            policy = SessionPolicy(portal_admin_user, other_session)
            assert policy.can_revoke_session() is True

    def test_user_can_revoke_own_session(self, regular_user, own_session):
        with _patch_is_portal_admin(False):
            policy = SessionPolicy(regular_user, own_session)
            assert policy.can_revoke_session() is True

    def test_user_cannot_revoke_other_session(self, regular_user, other_session):
        with _patch_is_portal_admin(False):
            policy = SessionPolicy(regular_user, other_session)
            result = policy.can_revoke_session()
        assert result is False

    def test_cannot_revoke_already_revoked_session(self, regular_user, revoked_session):
        with _patch_is_portal_admin(False):
            policy = SessionPolicy(regular_user, revoked_session)
            result = policy.can_revoke_session()
        assert result is False

    def test_portal_admin_cannot_revoke_already_revoked_session(self, portal_admin_user, revoked_session):
        """already_revoked tem precedência sobre privilégio."""
        with _patch_is_portal_admin(True):
            policy = SessionPolicy(portal_admin_user, revoked_session)
            result = policy.can_revoke_session()
        assert result is False


# ═══════════════════════════════════════════
# TestCanRevokeAllSessions
# ═══════════════════════════════════════════

class TestCanRevokeAllSessions:

    def test_portal_admin_can_revoke_all_sessions_of_any_user(self, portal_admin_user, other_session, other_user):
        with _patch_is_portal_admin(True):
            policy = SessionPolicy(portal_admin_user, other_session)
            assert policy.can_revoke_all_sessions(other_user) is True

    def test_user_can_revoke_all_own_sessions(self, regular_user, own_session):
        with _patch_is_portal_admin(False):
            policy = SessionPolicy(regular_user, own_session)
            assert policy.can_revoke_all_sessions(regular_user) is True

    def test_regular_user_cannot_revoke_all_sessions_of_other_user(self, regular_user, other_session, other_user):
        with _patch_is_portal_admin(False):
            policy = SessionPolicy(regular_user, other_session)
            result = policy.can_revoke_all_sessions(other_user)
        assert result is False
