"""
Testes para AttributePolicy.

Estratégia: zero banco de dados — MagicMock para todas as entidades.
Patch de UserRole.objects.filter via monkeypatch onde necessário.
"""
from unittest.mock import MagicMock, patch
import pytest

from apps.accounts.policies.attribute_policy import AttributePolicy


# ── Helpers de fixture ────────────────────────────────────────────────────────

def make_user(user_id=1, is_superuser=False):
    u = MagicMock()
    u.pk = user_id
    u.id = user_id
    u.is_superuser = is_superuser
    return u


def make_aplicacao(codigointerno="APP", isappbloqueada=False, isappproductionready=True, pk=1):
    app = MagicMock()
    app.pk = pk
    app.codigointerno = codigointerno
    app.isappbloqueada = isappbloqueada
    app.isappproductionready = isappproductionready
    return app


def make_attribute(user_id, aplicacao=None, key="k", value="v"):
    attr = MagicMock()
    attr.user_id = user_id
    attr.aplicacao = aplicacao
    attr.aplicacao_id = aplicacao.pk if aplicacao is not None else None
    attr.key = key
    attr.value = value
    return attr


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def regular_user():
    return make_user(user_id=20)


@pytest.fixture
def other_user():
    return make_user(user_id=30)


@pytest.fixture
def superuser():
    return make_user(user_id=10, is_superuser=True)


@pytest.fixture
def portal_admin_user():
    return make_user(user_id=5, is_superuser=False)


@pytest.fixture
def gestor_user():
    return make_user(user_id=40, is_superuser=False)


@pytest.fixture
def app_ready():
    return make_aplicacao(codigointerno="APP_READY", isappbloqueada=False, isappproductionready=True, pk=1)


@pytest.fixture
def app_blocked():
    return make_aplicacao(codigointerno="APP_BLOCKED", isappbloqueada=True, isappproductionready=True, pk=2)


@pytest.fixture
def app_not_ready():
    return make_aplicacao(codigointerno="APP_NOT_READY", isappbloqueada=False, isappproductionready=False, pk=3)


@pytest.fixture
def own_attribute(regular_user, app_ready):
    return make_attribute(user_id=regular_user.pk, aplicacao=app_ready, key="k1", value="v1")


@pytest.fixture
def other_attribute(other_user, app_ready):
    return make_attribute(user_id=other_user.pk, aplicacao=app_ready, key="k2", value="v2")


@pytest.fixture
def attribute_blocked_app(other_user, app_blocked):
    return make_attribute(user_id=other_user.pk, aplicacao=app_blocked)


@pytest.fixture
def attribute_not_ready_app(other_user, app_not_ready):
    return make_attribute(user_id=other_user.pk, aplicacao=app_not_ready)


@pytest.fixture
def attribute_no_app(other_user):
    return make_attribute(user_id=other_user.pk, aplicacao=None)


# ── Patch helpers ─────────────────────────────────────────────────────────────

def _patch_portal_admin(is_admin: bool):
    mock_qs = MagicMock()
    mock_qs.exists.return_value = is_admin
    return patch("apps.accounts.policies.attribute_policy.UserRole.objects.filter", return_value=mock_qs)


def _patch_manager_in_app(is_manager: bool):
    """Patch específico para _actor_is_manager_in_attribute_app."""
    mock_qs = MagicMock()
    mock_qs.exists.return_value = is_manager
    return patch("apps.accounts.policies.attribute_policy.UserRole.objects.filter", return_value=mock_qs)


# ═══════════════════════════════════════════
# TestCanViewAttribute
# ═══════════════════════════════════════════

class TestCanViewAttribute:

    def test_portal_admin_can_view_any_attribute(self, portal_admin_user, other_attribute):
        with _patch_portal_admin(True):
            policy = AttributePolicy(portal_admin_user, other_attribute)
            assert policy.can_view_attribute() is True

    def test_superuser_can_view_any_attribute(self, superuser, other_attribute):
        with _patch_portal_admin(False):
            policy = AttributePolicy(superuser, other_attribute)
            assert policy.can_view_attribute() is True

    def test_user_can_view_own_attribute(self, regular_user, own_attribute):
        with _patch_portal_admin(False):
            policy = AttributePolicy(regular_user, own_attribute)
            assert policy.can_view_attribute() is True

    def test_gestor_can_view_attribute_of_user_in_same_app(self, gestor_user, other_attribute):
        """Gestor com pode_editar_usuario=True na mesma app do atributo pode visualizar."""
        with _patch_manager_in_app(True):
            policy = AttributePolicy(gestor_user, other_attribute)
            # _is_portal_admin via filter → False (exists=False já que mock retorna True
            # mas apenas na segunda chamada; precisamos de side_effect)
            # Resetamos _is_admin manualmente para simular não-admin
            policy._is_admin = False
            assert policy.can_view_attribute() is True

    def test_regular_user_cannot_view_other_attribute(self, regular_user, other_attribute):
        with _patch_portal_admin(False):
            policy = AttributePolicy(regular_user, other_attribute)
            result = policy.can_view_attribute()
        assert result is False


# ═══════════════════════════════════════════
# TestCanCreateAttribute
# ═══════════════════════════════════════════

class TestCanCreateAttribute:

    def test_portal_admin_can_create_attribute_in_ready_app(self, portal_admin_user, own_attribute):
        with _patch_portal_admin(True):
            policy = AttributePolicy(portal_admin_user, own_attribute)
            assert policy.can_create_attribute() is True

    def test_portal_admin_cannot_create_in_blocked_app(self, portal_admin_user, attribute_blocked_app):
        with _patch_portal_admin(True):
            policy = AttributePolicy(portal_admin_user, attribute_blocked_app)
            result = policy.can_create_attribute()
        assert result is False

    def test_portal_admin_cannot_create_in_not_ready_app(self, portal_admin_user, attribute_not_ready_app):
        with _patch_portal_admin(True):
            policy = AttributePolicy(portal_admin_user, attribute_not_ready_app)
            result = policy.can_create_attribute()
        assert result is False

    def test_portal_admin_can_create_attribute_without_app(self, portal_admin_user, attribute_no_app):
        with _patch_portal_admin(True):
            policy = AttributePolicy(portal_admin_user, attribute_no_app)
            assert policy.can_create_attribute() is True

    def test_regular_user_cannot_create_attribute(self, regular_user, own_attribute):
        with _patch_portal_admin(False):
            policy = AttributePolicy(regular_user, own_attribute)
            result = policy.can_create_attribute()
        assert result is False


# ═══════════════════════════════════════════
# TestCanEditAndDeleteAttribute
# ═══════════════════════════════════════════

class TestCanEditAndDeleteAttribute:

    def test_portal_admin_can_edit_attribute(self, portal_admin_user, other_attribute):
        with _patch_portal_admin(True):
            policy = AttributePolicy(portal_admin_user, other_attribute)
            assert policy.can_edit_attribute() is True

    def test_superuser_can_edit_attribute(self, superuser, other_attribute):
        with _patch_portal_admin(False):
            policy = AttributePolicy(superuser, other_attribute)
            assert policy.can_edit_attribute() is True

    def test_regular_user_cannot_edit_attribute(self, regular_user, other_attribute):
        with _patch_portal_admin(False):
            policy = AttributePolicy(regular_user, other_attribute)
            result = policy.can_edit_attribute()
        assert result is False

    def test_portal_admin_can_delete_attribute(self, portal_admin_user, other_attribute):
        with _patch_portal_admin(True):
            policy = AttributePolicy(portal_admin_user, other_attribute)
            assert policy.can_delete_attribute() is True

    def test_regular_user_cannot_delete_attribute(self, regular_user, other_attribute):
        with _patch_portal_admin(False):
            policy = AttributePolicy(regular_user, other_attribute)
            result = policy.can_delete_attribute()
        assert result is False
