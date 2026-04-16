"""
Testes de UserRolePolicy.

Estratégia: zero banco de dados.
Todos os objetos são MagicMock. Chamadas ao ORM são interceptadas via
unittest.mock.patch aplicado por teste ou via autouse fixture.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.policies.userrole_policy import UserRolePolicy
from apps.accounts.tests.policies.conftest import make_aplicacao, make_role, make_user

# ── Factories locais ─────────────────────────────────────────────


def make_userrole(
    user=None, aplicacao=None, role=None, user_id=None, aplicacao_id=None
):
    ur = MagicMock()
    ur.user = user or make_user(user_id=20)
    ur.user_id = user_id if user_id is not None else ur.user.id
    ur.aplicacao = aplicacao or make_aplicacao()
    ur.aplicacao_id = aplicacao_id if aplicacao_id is not None else 1
    ur.role = role or make_role()
    ur.pk = 99
    return ur


def make_classificacao(pode_editar=False):
    c = MagicMock()
    c.pode_editar_usuario = pode_editar
    return c


def make_gestor(user_id=40):
    """Usuário com pode_editar_usuario=True."""
    user = make_user(user_id=user_id, is_superuser=False)
    user.pk = user_id
    classificacao = make_classificacao(pode_editar=True)
    user.profile.classificacao_usuario = classificacao
    return user


# ── Fixtures específicas de UserRole ─────────────────────────────


@pytest.fixture
def app_ready():
    return make_aplicacao(
        codigointerno="APP_READY", isappbloqueada=False, isappproductionready=True
    )


@pytest.fixture
def app_blocked():
    return make_aplicacao(
        codigointerno="APP_BLOCKED", isappbloqueada=True, isappproductionready=True
    )


@pytest.fixture
def app_not_ready():
    return make_aplicacao(
        codigointerno="APP_NOT_READY", isappbloqueada=False, isappproductionready=False
    )


@pytest.fixture
def regular_user():
    u = make_user(user_id=20, is_superuser=False)
    u.pk = 20
    return u


@pytest.fixture
def superuser():
    u = make_user(user_id=10, is_superuser=True)
    u.pk = 10
    return u


@pytest.fixture
def other_user():
    u = make_user(user_id=30, is_superuser=False)
    u.pk = 30
    return u


@pytest.fixture
def portal_admin_user():
    """Usuário PORTAL_ADMIN (não superuser). _is_portal_admin mockado nos testes."""
    u = make_user(user_id=50, is_superuser=False)
    u.pk = 50
    return u


@pytest.fixture
def regular_role(app_ready):
    return make_role(codigoperfil="VIEWER", aplicacao=app_ready)


@pytest.fixture
def admin_role(app_ready):
    return make_role(codigoperfil="PORTAL_ADMIN", aplicacao=app_ready)


@pytest.fixture
def userrole_regular(regular_user, app_ready, regular_role):
    """UserRole de regular_user em app_ready com role comum."""
    return make_userrole(
        user=regular_user,
        aplicacao=app_ready,
        role=regular_role,
        user_id=regular_user.id,
        aplicacao_id=1,
    )


@pytest.fixture
def userrole_admin(portal_admin_user, app_ready, admin_role):
    """UserRole de portal_admin_user com role PORTAL_ADMIN."""
    return make_userrole(
        user=portal_admin_user,
        aplicacao=app_ready,
        role=admin_role,
        user_id=portal_admin_user.id,
        aplicacao_id=1,
    )


@pytest.fixture
def actor_gestor():
    """User com pode_editar_usuario=True e UserRole simulado em app_ready (aplicacao_id=1)."""
    return make_gestor(user_id=40)


# ── Helpers de patch ──────────────────────────────────────────


def _patch_admin(monkeypatch, policy, is_admin: bool):
    """Força _is_portal_admin() sem DB."""
    monkeypatch.setattr(policy, "_is_portal_admin", lambda: is_admin)


def _patch_can_edit(monkeypatch, policy, can_edit: bool):
    """Força _can_edit_users() — evita que MagicMock auto-crie atributos truthy."""
    monkeypatch.setattr(policy, "_can_edit_users", lambda: can_edit)


def _patch_actor_apps(monkeypatch, policy, app_ids: set):
    """Força _get_actor_applications() sem DB."""
    monkeypatch.setattr(policy, "_get_actor_applications", lambda: app_ids)


def _patch_intersection(monkeypatch, policy, result: bool):
    """Força _has_intersection_with_target() sem DB."""
    monkeypatch.setattr(policy, "_has_intersection_with_target", lambda _: result)


# ═════════════════════════════════════════════════════════════════
# TestCanViewUserrole
# ═════════════════════════════════════════════════════════════════


class TestCanViewUserrole:

    def test_portal_admin_can_view_any_userrole(
        self, monkeypatch, portal_admin_user, userrole_regular
    ):
        policy = UserRolePolicy(portal_admin_user, userrole_regular)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_view_userrole() is True

    def test_superuser_can_view_any_userrole(self, superuser, userrole_regular):
        policy = UserRolePolicy(superuser, userrole_regular)
        with patch(
            "apps.accounts.policies.userrole_policy.UserRolePolicy._is_portal_admin",
            return_value=False,
        ):
            assert policy.can_view_userrole() is True

    def test_user_can_view_own_userrole(
        self, monkeypatch, regular_user, userrole_regular
    ):
        # userrole_regular.user_id == regular_user.id == 20
        policy = UserRolePolicy(regular_user, userrole_regular)
        _patch_admin(monkeypatch, policy, False)
        assert policy.can_view_userrole() is True

    def test_gestor_can_view_userrole_in_same_app(
        self, monkeypatch, actor_gestor, userrole_regular
    ):
        policy = UserRolePolicy(actor_gestor, userrole_regular)
        _patch_admin(monkeypatch, policy, False)
        _patch_actor_apps(monkeypatch, policy, {1})
        assert policy.can_view_userrole() is True

    def test_regular_user_cannot_view_other_userrole(
        self, monkeypatch, other_user, userrole_regular
    ):
        """other_user.id=30 != userrole_regular.user_id=20, sem privilégio."""
        policy = UserRolePolicy(other_user, userrole_regular)
        _patch_admin(monkeypatch, policy, False)
        _patch_can_edit(monkeypatch, policy, False)
        assert policy.can_view_userrole() is False

    def test_gestor_without_role_in_same_app_cannot_view_userrole(
        self, monkeypatch, actor_gestor, app_ready, regular_role, other_user
    ):
        """
        Gestor com pode_editar_usuario=True MAS sem UserRole na mesma app
        do userrole alvo → nega acesso.
        Cobre linhas 70–78 de userrole_policy.py (branch: no_role_in_same_app).
        """
        # userrole alvo está em aplicacao_id=1; gestor não tem role em app 1
        ur = make_userrole(
            user=other_user,
            aplicacao=app_ready,
            role=regular_role,
            user_id=other_user.id,
            aplicacao_id=1,
        )
        policy = UserRolePolicy(actor_gestor, ur)
        _patch_admin(monkeypatch, policy, False)
        _patch_can_edit(monkeypatch, policy, True)  # é gestor
        _patch_actor_apps(monkeypatch, policy, {99})  # mas está em app 99, não em app 1
        assert policy.can_view_userrole() is False


# ═════════════════════════════════════════════════════════════════
# TestCanCreateUserrole
# ═════════════════════════════════════════════════════════════════


class TestCanCreateUserrole:

    def test_portal_admin_can_create_in_ready_unblocked_app(
        self, monkeypatch, portal_admin_user, app_ready, regular_role
    ):
        ur = make_userrole(
            user=portal_admin_user, aplicacao=app_ready, role=regular_role, user_id=50
        )
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_create_userrole() is True

    def test_portal_admin_cannot_create_in_blocked_app(
        self, monkeypatch, portal_admin_user, app_blocked, regular_role
    ):
        ur = make_userrole(
            user=portal_admin_user, aplicacao=app_blocked, role=regular_role, user_id=50
        )
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_create_userrole() is False

    def test_portal_admin_cannot_create_in_not_ready_app(
        self, monkeypatch, portal_admin_user, app_not_ready, regular_role
    ):
        ur = make_userrole(
            user=portal_admin_user,
            aplicacao=app_not_ready,
            role=regular_role,
            user_id=50,
        )
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_create_userrole() is False

    def test_portal_admin_cannot_assign_admin_role(
        self, monkeypatch, portal_admin_user, app_ready, admin_role
    ):
        ur = make_userrole(
            user=portal_admin_user, aplicacao=app_ready, role=admin_role, user_id=50
        )
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_create_userrole() is False

    def test_superuser_can_assign_admin_role(self, superuser, app_ready, admin_role):
        ur = make_userrole(
            user=superuser, aplicacao=app_ready, role=admin_role, user_id=10
        )
        policy = UserRolePolicy(superuser, ur)
        with patch(
            "apps.accounts.policies.userrole_policy.UserRolePolicy._is_portal_admin",
            return_value=False,
        ):
            assert policy.can_create_userrole() is True

    def test_regular_user_cannot_create_userrole(
        self, monkeypatch, regular_user, app_ready, regular_role
    ):
        ur = make_userrole(
            user=regular_user, aplicacao=app_ready, role=regular_role, user_id=20
        )
        policy = UserRolePolicy(regular_user, ur)
        _patch_admin(monkeypatch, policy, False)
        assert policy.can_create_userrole() is False

    def test_portal_admin_can_create_global_userrole(
        self, monkeypatch, portal_admin_user, regular_role
    ):
        """
        userrole.aplicacao=None (vínculo global) → _app_is_blocked()=False e
        _app_is_production_ready()=True — sem restrição de app.
        Cobre linhas 257–261 e 270 de userrole_policy.py.
        """
        ur = make_userrole(user=portal_admin_user, role=regular_role, user_id=50)
        ur.aplicacao = None
        ur.aplicacao_id = None
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_create_userrole() is True


# ═════════════════════════════════════════════════════════════════
# TestCanDeleteUserrole
# ═════════════════════════════════════════════════════════════════


class TestCanDeleteUserrole:

    def test_portal_admin_can_delete_userrole_of_other_user(
        self, monkeypatch, portal_admin_user, other_user, app_ready, regular_role
    ):
        """portal_admin(id=50) deletando UserRole cujo user_id=30 (other_user)."""
        ur = make_userrole(
            user=other_user, aplicacao=app_ready, role=regular_role, user_id=30
        )
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_delete_userrole() is True

    def test_portal_admin_cannot_delete_own_userrole(
        self, monkeypatch, portal_admin_user, app_ready, regular_role
    ):
        """portal_admin(id=50) tentando deletar seu próprio UserRole."""
        ur = make_userrole(
            user=portal_admin_user, aplicacao=app_ready, role=regular_role, user_id=50
        )
        portal_admin_user.pk = 50
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_delete_userrole() is False

    def test_portal_admin_cannot_revoke_admin_role(
        self, monkeypatch, portal_admin_user, other_user, app_ready, admin_role
    ):
        """portal_admin tentando revogar UserRole com codigoperfil=PORTAL_ADMIN."""
        ur = make_userrole(
            user=other_user, aplicacao=app_ready, role=admin_role, user_id=30
        )
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_delete_userrole() is False

    def test_superuser_can_revoke_admin_role_of_other_user(
        self, superuser, other_user, app_ready, admin_role
    ):
        ur = make_userrole(
            user=other_user, aplicacao=app_ready, role=admin_role, user_id=30
        )
        policy = UserRolePolicy(superuser, ur)
        with patch(
            "apps.accounts.policies.userrole_policy.UserRolePolicy._is_portal_admin",
            return_value=False,
        ):
            assert policy.can_delete_userrole() is True

    def test_portal_admin_can_delete_userrole_even_in_blocked_app(
        self, monkeypatch, portal_admin_user, other_user, app_blocked, regular_role
    ):
        ur = make_userrole(
            user=other_user, aplicacao=app_blocked, role=regular_role, user_id=30
        )
        policy = UserRolePolicy(portal_admin_user, ur)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_delete_userrole() is True

    def test_regular_user_cannot_delete_userrole(
        self, monkeypatch, regular_user, other_user, app_ready, regular_role
    ):
        ur = make_userrole(
            user=other_user, aplicacao=app_ready, role=regular_role, user_id=30
        )
        policy = UserRolePolicy(regular_user, ur)
        _patch_admin(monkeypatch, policy, False)
        assert policy.can_delete_userrole() is False


# ═════════════════════════════════════════════════════════════════
# TestCanViewUserrolesOfUser
# ═════════════════════════════════════════════════════════════════


class TestCanViewUserrolesOfUser:

    def test_portal_admin_can_view_all_userroles_of_any_user(
        self, monkeypatch, portal_admin_user, other_user, userrole_regular
    ):
        policy = UserRolePolicy(portal_admin_user, userrole_regular)
        _patch_admin(monkeypatch, policy, True)
        assert policy.can_view_userroles_of_user(other_user) is True

    def test_user_can_view_own_userroles(
        self, monkeypatch, regular_user, userrole_regular
    ):
        """Actor == target_user: sempre True."""
        policy = UserRolePolicy(regular_user, userrole_regular)
        _patch_admin(monkeypatch, policy, False)
        regular_user.pk = 20
        target = make_user(user_id=20)
        target.pk = 20
        assert policy.can_view_userroles_of_user(target) is True

    def test_gestor_can_view_userroles_of_user_in_same_app(
        self, monkeypatch, actor_gestor, other_user, userrole_regular
    ):
        policy = UserRolePolicy(actor_gestor, userrole_regular)
        _patch_admin(monkeypatch, policy, False)
        _patch_intersection(monkeypatch, policy, True)
        assert policy.can_view_userroles_of_user(other_user) is True

    def test_gestor_cannot_view_userroles_of_user_in_other_app(
        self, monkeypatch, actor_gestor, other_user, userrole_regular
    ):
        policy = UserRolePolicy(actor_gestor, userrole_regular)
        _patch_admin(monkeypatch, policy, False)
        _patch_intersection(monkeypatch, policy, False)
        assert policy.can_view_userroles_of_user(other_user) is False

    def test_regular_user_cannot_view_userroles_of_other_user(
        self, monkeypatch, regular_user, other_user, userrole_regular
    ):
        policy = UserRolePolicy(regular_user, userrole_regular)
        _patch_admin(monkeypatch, policy, False)
        _patch_can_edit(monkeypatch, policy, False)
        assert policy.can_view_userroles_of_user(other_user) is False
