"""
Testes para RolePolicy.

Estratégia:
  - Zero banco de dados (pytest-django não necessário aqui)
  - MagicMock para todas as entidades
  - patch em apps.accounts.policies.role_policy.UserRole para isolar queries
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.policies.role_policy import RolePolicy
from apps.accounts.tests.policies.conftest import make_role, make_user

# ── Patch path ───────────────────────────────────────────────────────────────────

USERROLE_PATH = "apps.accounts.policies.role_policy.UserRole"


# ── Helpers de patch ────────────────────────────────────────────────────────────


def _patch_is_portal_admin(is_admin: bool):
    """Patch UserRole.objects.filter(...).exists() para _is_portal_admin."""
    mock_qs = MagicMock()
    mock_qs.exists.return_value = is_admin
    return mock_qs


def _patch_actor_role_in_app(user_role):
    """Patch UserRole.objects.filter(...).select_related(...).first() para _get_actor_role_in_same_app."""
    mock_qs = MagicMock()
    mock_qs.select_related.return_value.first.return_value = user_role
    return mock_qs


# ── Fixture: portal_admin_user ─────────────────────────────────────────────────────


@pytest.fixture
def portal_admin_user():
    """Usuário com role PORTAL_ADMIN (não superuser)."""
    return make_user(user_id=1, is_superuser=False)


# ── TestCanViewRole ──────────────────────────────────────────────────────────────


class TestCanViewRole:
    def test_portal_admin_can_view_any_role(self, portal_admin_user, regular_role):
        policy = RolePolicy(portal_admin_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_view_role() is True

    def test_superuser_can_view_any_role(self, superuser, regular_role):
        policy = RolePolicy(superuser, regular_role)
        # SuperUser não precisa de query — _is_superuser() curto-circuita
        assert policy.can_view_role() is True

    def test_user_with_role_in_app_can_view_role_of_same_app(
        self, regular_user, regular_role
    ):
        policy = RolePolicy(regular_user, regular_role)
        mock_user_role = MagicMock()
        with patch(USERROLE_PATH) as mock_ur:
            # Primeira call → _is_portal_admin (exists=False)
            # Segunda call → _get_actor_role_in_same_app (first=mock_user_role)
            mock_ur.objects.filter.side_effect = [
                _patch_is_portal_admin(False),
                _patch_actor_role_in_app(mock_user_role),
            ]
            assert policy.can_view_role() is True

    def test_user_without_role_cannot_view_role(self, regular_user, regular_role):
        policy = RolePolicy(regular_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.side_effect = [
                _patch_is_portal_admin(False),
                _patch_actor_role_in_app(None),
            ]
            assert policy.can_view_role() is False

    def test_user_cannot_view_role_of_blocked_app(self, regular_user, app_blocked):
        blocked_role = make_role(codigoperfil="VIEWER", aplicacao=app_blocked)
        policy = RolePolicy(regular_user, blocked_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(False)
            assert policy.can_view_role() is False


# ── TestCanCreateRole ─────────────────────────────────────────────────────────────


class TestCanCreateRole:
    def test_portal_admin_can_create_role(self, portal_admin_user, regular_role):
        policy = RolePolicy(portal_admin_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_create_role() is True

    def test_superuser_can_create_role(self, superuser, regular_role):
        policy = RolePolicy(superuser, regular_role)
        assert policy.can_create_role() is True

    def test_regular_user_cannot_create_role(self, regular_user, regular_role):
        policy = RolePolicy(regular_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(False)
            assert policy.can_create_role() is False


# ── TestCanEditRole ──────────────────────────────────────────────────────────────


class TestCanEditRole:
    def test_portal_admin_can_edit_regular_role(self, portal_admin_user, regular_role):
        policy = RolePolicy(portal_admin_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_edit_role() is True

    def test_superuser_can_edit_regular_role(self, superuser, regular_role):
        policy = RolePolicy(superuser, regular_role)
        assert policy.can_edit_role() is True

    def test_portal_admin_cannot_edit_portal_admin_role(
        self, portal_admin_user, admin_role
    ):
        policy = RolePolicy(portal_admin_user, admin_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_edit_role() is False

    def test_superuser_can_edit_portal_admin_role(self, superuser, admin_role):
        policy = RolePolicy(superuser, admin_role)
        assert policy.can_edit_role() is True

    def test_regular_user_cannot_edit_any_role(self, regular_user, regular_role):
        policy = RolePolicy(regular_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(False)
            assert policy.can_edit_role() is False


# ── TestCanDeleteRole ─────────────────────────────────────────────────────────────


class TestCanDeleteRole:
    def test_portal_admin_can_delete_regular_role(
        self, portal_admin_user, regular_role
    ):
        policy = RolePolicy(portal_admin_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_delete_role() is True

    def test_superuser_cannot_delete_portal_admin_role(self, superuser, admin_role):
        policy = RolePolicy(superuser, admin_role)
        # Root role é imutável mesmo para SuperUser
        assert policy.can_delete_role() is False

    def test_portal_admin_cannot_delete_portal_admin_role(
        self, portal_admin_user, admin_role
    ):
        policy = RolePolicy(portal_admin_user, admin_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_delete_role() is False

    def test_regular_user_cannot_delete_any_role(self, regular_user, regular_role):
        policy = RolePolicy(regular_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(False)
            assert policy.can_delete_role() is False


# ── TestCanAssignRole ─────────────────────────────────────────────────────────────


class TestCanAssignRole:
    def test_portal_admin_can_assign_regular_role_in_ready_app(
        self, portal_admin_user, regular_role, other_user
    ):
        policy = RolePolicy(portal_admin_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_assign_role_to_user(other_user) is True

    def test_portal_admin_cannot_assign_portal_admin_role(
        self, portal_admin_user, admin_role, other_user
    ):
        policy = RolePolicy(portal_admin_user, admin_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_assign_role_to_user(other_user) is False

    def test_superuser_can_assign_portal_admin_role(
        self, superuser, admin_role, other_user
    ):
        policy = RolePolicy(superuser, admin_role)
        assert policy.can_assign_role_to_user(other_user) is True

    def test_portal_admin_cannot_assign_role_in_blocked_app(
        self, portal_admin_user, app_blocked, other_user
    ):
        blocked_role = make_role(codigoperfil="VIEWER", aplicacao=app_blocked)
        policy = RolePolicy(portal_admin_user, blocked_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_assign_role_to_user(other_user) is False

    def test_portal_admin_cannot_assign_role_in_not_ready_app(
        self, portal_admin_user, app_not_ready, other_user
    ):
        not_ready_role = make_role(codigoperfil="VIEWER", aplicacao=app_not_ready)
        policy = RolePolicy(portal_admin_user, not_ready_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_assign_role_to_user(other_user) is False

    def test_regular_user_cannot_assign_any_role(
        self, regular_user, regular_role, other_user
    ):
        policy = RolePolicy(regular_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(False)
            assert policy.can_assign_role_to_user(other_user) is False

    def test_portal_admin_can_assign_global_role(self, portal_admin_user, other_user):
        """
        role.aplicacao=None (role global, ex: PORTAL_ADMIN sem app vinculada) →
        _role_app_is_production_ready() retorna True (linha 269) sem consultar
        atributos da app, e can_assign_role_to_user retorna True (linha 290).
        Cobre linhas 269 e 290 de role_policy.py.
        """
        global_role = MagicMock()
        global_role.codigoperfil = "VIEWER"
        global_role.aplicacao = None
        policy = RolePolicy(portal_admin_user, global_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_assign_role_to_user(other_user) is True


# ── TestCanRevokeRole ─────────────────────────────────────────────────────────────


class TestCanRevokeRole:
    def test_portal_admin_can_revoke_regular_role_from_other_user(
        self, portal_admin_user, regular_role, other_user
    ):
        policy = RolePolicy(portal_admin_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_revoke_role_from_user(other_user) is True

    def test_cannot_revoke_own_role_regular_user(self, regular_user, regular_role):
        """Usuário comum não pode revogar a própria role."""
        policy = RolePolicy(regular_user, regular_role)
        assert policy.can_revoke_role_from_user(regular_user) is False

    def test_cannot_revoke_own_role_portal_admin(self, portal_admin_user, regular_role):
        """Nem PORTAL_ADMIN pode revogar a própria role."""
        policy = RolePolicy(portal_admin_user, regular_role)
        # Mesmo sendo admin, auto-revogação é negada antes de qualquer check de privilégio
        assert policy.can_revoke_role_from_user(portal_admin_user) is False

    def test_portal_admin_cannot_revoke_portal_admin_role(
        self, portal_admin_user, admin_role, other_user
    ):
        policy = RolePolicy(portal_admin_user, admin_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            assert policy.can_revoke_role_from_user(other_user) is False

    def test_superuser_can_revoke_portal_admin_role_from_other_user(
        self, superuser, admin_role, other_user
    ):
        policy = RolePolicy(superuser, admin_role)
        assert policy.can_revoke_role_from_user(other_user) is True

    def test_portal_admin_can_revoke_role_even_from_blocked_app(
        self, portal_admin_user, app_blocked, other_user
    ):
        blocked_role = make_role(codigoperfil="VIEWER", aplicacao=app_blocked)
        policy = RolePolicy(portal_admin_user, blocked_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(True)
            # App bloqueada NÃO impede revogação
            assert policy.can_revoke_role_from_user(other_user) is True

    def test_regular_user_cannot_revoke_any_role(
        self, regular_user, regular_role, other_user
    ):
        policy = RolePolicy(regular_user, regular_role)
        with patch(USERROLE_PATH) as mock_ur:
            mock_ur.objects.filter.return_value = _patch_is_portal_admin(False)
            assert policy.can_revoke_role_from_user(other_user) is False
