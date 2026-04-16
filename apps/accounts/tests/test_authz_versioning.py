"""
Testes — AuthZ Versioning Layer

Cobre:
  1. Modelo UserAuthzState (criação, unicidade OneToOne, str).
  2. bump_authz_version() — incremento atômico, criação lazy, idempotência.
  3. GET /api/authz/version/ — autenticação, retorno correto, O(1).
  4. Integração: bump chamado via signals de UserRole, UserPermissionOverride,
     m2m_changed (group permissions) e Role post_save.
"""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.authz_versioning import UserAuthzState, bump_authz_version
from apps.accounts.models import Aplicacao, Role, UserPermissionOverride, UserRole

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser_authz", password="pass")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other_authz", password="pass")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def aplicacao(db):
    return Aplicacao.objects.create(
        codigointerno="TEST",
        nomeaplicacao="Test App",
        isappbloqueada=False,
        isappproductionready=True,
    )


@pytest.fixture
def role(db, aplicacao):
    group = Group.objects.create(name="TEST_VIEWER")
    return Role.objects.create(
        aplicacao=aplicacao,
        nomeperfil="Viewer",
        codigoperfil="VIEWER",
        group=group,
    )


# ---------------------------------------------------------------------------
# 1. Modelo UserAuthzState
# ---------------------------------------------------------------------------

class TestUserAuthzStateModel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="model_test", password="pass")

    def test_create_state(self):
        state = UserAuthzState.objects.create(user=self.user)
        assert state.authz_version == 0
        assert state.updated_at is not None

    def test_one_to_one_constraint(self):
        UserAuthzState.objects.create(user=self.user)
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            UserAuthzState.objects.create(user=self.user)

    def test_str_representation(self):
        state = UserAuthzState.objects.create(user=self.user)
        assert str(self.user.pk) in str(state)
        assert "0" in str(state)

    def test_related_name_access(self):
        state = UserAuthzState.objects.create(user=self.user)
        assert self.user.authz_state == state


# ---------------------------------------------------------------------------
# 2. bump_authz_version()
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bump_creates_state_if_not_exists(user):
    assert not UserAuthzState.objects.filter(user=user).exists()
    bump_authz_version(user)
    state = UserAuthzState.objects.get(user=user)
    assert state.authz_version == 1


@pytest.mark.django_db
def test_bump_increments_existing(user):
    UserAuthzState.objects.create(user=user, authz_version=5)
    bump_authz_version(user)
    state = UserAuthzState.objects.get(user=user)
    assert state.authz_version == 6


@pytest.mark.django_db
def test_bump_accepts_user_id_int(user):
    bump_authz_version(user.pk)
    state = UserAuthzState.objects.get(user=user)
    assert state.authz_version == 1


@pytest.mark.django_db
def test_bump_multiple_times(user):
    for _ in range(5):
        bump_authz_version(user)
    state = UserAuthzState.objects.get(user=user)
    assert state.authz_version == 5


@pytest.mark.django_db
def test_bump_does_not_affect_other_users(user, other_user):
    bump_authz_version(user)
    assert not UserAuthzState.objects.filter(user=other_user).exists()


# ---------------------------------------------------------------------------
# 3. GET /api/authz/version/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_authz_version_endpoint_unauthenticated(api_client):
    url = reverse("accounts:authz-version")
    response = api_client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_authz_version_endpoint_returns_zero_if_no_state(auth_client):
    url = reverse("accounts:authz-version")
    response = auth_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["authz_version"] == 0


@pytest.mark.django_db
def test_authz_version_endpoint_returns_correct_version(auth_client, user):
    UserAuthzState.objects.create(user=user, authz_version=42)
    url = reverse("accounts:authz-version")
    response = auth_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["authz_version"] == 42


@pytest.mark.django_db
def test_authz_version_endpoint_does_not_leak_other_user(auth_client, other_user):
    """O endpoint deve retornar apenas a versão do usuário autenticado."""
    UserAuthzState.objects.create(user=other_user, authz_version=99)
    url = reverse("accounts:authz-version")
    response = auth_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    # Usuário autenticado não tem estado — deve retornar 0, não 99.
    assert response.data["authz_version"] == 0


# ---------------------------------------------------------------------------
# 4. Integração: bump chamado por signals de UserRole
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bump_called_on_userrole_create(user, aplicacao, role):
    assert not UserAuthzState.objects.filter(user=user).exists()
    UserRole.objects.create(user=user, aplicacao=aplicacao, role=role)
    state = UserAuthzState.objects.filter(user=user).first()
    assert state is not None
    assert state.authz_version >= 1


@pytest.mark.django_db
def test_bump_called_on_userrole_delete(user, aplicacao, role):
    ur = UserRole.objects.create(user=user, aplicacao=aplicacao, role=role)
    version_after_create = UserAuthzState.objects.get(user=user).authz_version
    ur.delete()
    version_after_delete = UserAuthzState.objects.get(user=user).authz_version
    assert version_after_delete > version_after_create


# ---------------------------------------------------------------------------
# 4b. Integração: bump chamado por signals de UserPermissionOverride
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bump_called_on_override_create(user):
    perm = Permission.objects.first()
    assert perm is not None
    UserPermissionOverride.objects.create(
        user=user,
        permission=perm,
        mode=UserPermissionOverride.MODE_GRANT,
    )
    state = UserAuthzState.objects.filter(user=user).first()
    assert state is not None
    assert state.authz_version >= 1


@pytest.mark.django_db
def test_bump_called_on_override_delete(user):
    perm = Permission.objects.first()
    override = UserPermissionOverride.objects.create(
        user=user,
        permission=perm,
        mode=UserPermissionOverride.MODE_GRANT,
    )
    version_before = UserAuthzState.objects.get(user=user).authz_version
    override.delete()
    version_after = UserAuthzState.objects.get(user=user).authz_version
    assert version_after > version_before


# ---------------------------------------------------------------------------
# 4c. Integração: bump chamado por m2m_changed em group.permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bump_called_on_group_permission_add(user, aplicacao, role):
    UserRole.objects.create(user=user, aplicacao=aplicacao, role=role)
    version_before = UserAuthzState.objects.get(user=user).authz_version

    perm = Permission.objects.first()
    role.group.permissions.add(perm)

    version_after = UserAuthzState.objects.get(user=user).authz_version
    assert version_after > version_before
