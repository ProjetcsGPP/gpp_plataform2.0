"""
Testes — AuthZ Versioning Layer

Cobre:
  1. Modelo UserAuthzState (criação, unicidade OneToOne, str).
  2. bump_authz_version() — incremento atômico, criação lazy, idempotência.
  3. GET /api/authz/version/ — autenticação, retorno correto, O(1).
  4. Integração: bump chamado via signals de UserRole, UserPermissionOverride,
     m2m_changed (group permissions) e Role post_save.

Padrão de testes:
  - Sem force_authenticate: login real via POST /api/accounts/login/ + app_context.
  - _make_user() + _assign_role() do conftest para criação de usuários com UserProfile.
  - Objetos Aplicacao e Role referenciados pelos pks fixos do bootstrap (pk=1 PORTAL,
    pk=2 ACOES_PNGI, Role pk=1 PORTAL_ADMIN, pk=2 GESTOR_PNGI).
"""
import pytest
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.authz_versioning import UserAuthzState, bump_authz_version
from apps.accounts.models import Aplicacao, Role, UserPermissionOverride, UserRole
from apps.accounts.tests.conftest import (
    DEFAULT_PASSWORD,
    _assign_role,
    _make_authenticated_client,
    _make_user,
)

AUTHZ_VERSION_URL = "/api/accounts/authz/version/"


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def plain_user(db):
    """Usuário sem role (apenas auth.User + UserProfile)."""
    return _make_user("authz_plain_user")


@pytest.fixture
def other_user(db):
    """Segundo usuário sem role — garante isolamento entre usuários."""
    return _make_user("authz_other_user")


@pytest.fixture
def user_with_role(db):
    """Usuário com PORTAL_ADMIN (Role pk=1) para testes de signal integrado."""
    user = _make_user("authz_role_user")
    _assign_role(user, role_pk=1)
    return user


@pytest.fixture
def client_plain(db, plain_user):
    """APIClient autenticado como plain_user via sessão Django real (PORTAL)."""
    client, resp = _make_authenticated_client("authz_plain_user", "PORTAL")
    assert resp.status_code == 200, (
        f"Falha no login do plain_user: status={resp.status_code} data={resp.data}"
    )
    return client


@pytest.fixture
def client_anonimo():
    """APIClient sem nenhuma autenticação."""
    return APIClient()


# ---------------------------------------------------------------------------
# 1. Modelo UserAuthzState
# ---------------------------------------------------------------------------


class TestUserAuthzStateModel(TestCase):
    def setUp(self):
        from apps.accounts.tests.conftest import _make_user

        self.user = _make_user("model_authz_test")

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
def test_bump_creates_state_if_not_exists(plain_user):
    assert not UserAuthzState.objects.filter(user=plain_user).exists()
    bump_authz_version(plain_user)
    state = UserAuthzState.objects.get(user=plain_user)
    assert state.authz_version == 1


@pytest.mark.django_db
def test_bump_increments_existing(plain_user):
    UserAuthzState.objects.create(user=plain_user, authz_version=5)
    bump_authz_version(plain_user)
    state = UserAuthzState.objects.get(user=plain_user)
    assert state.authz_version == 6


@pytest.mark.django_db
def test_bump_accepts_user_id_int(plain_user):
    bump_authz_version(plain_user.pk)
    state = UserAuthzState.objects.get(user=plain_user)
    assert state.authz_version == 1


@pytest.mark.django_db
def test_bump_multiple_times(plain_user):
    for _ in range(5):
        bump_authz_version(plain_user)
    state = UserAuthzState.objects.get(user=plain_user)
    assert state.authz_version == 5


@pytest.mark.django_db
def test_bump_does_not_affect_other_users(plain_user, other_user):
    bump_authz_version(plain_user)
    assert not UserAuthzState.objects.filter(user=other_user).exists()


# ---------------------------------------------------------------------------
# 3. GET /api/authz/version/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_authz_version_endpoint_unauthenticated(client_anonimo):
    response = client_anonimo.get(AUTHZ_VERSION_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_authz_version_endpoint_returns_zero_if_no_state(client_plain, plain_user):
    # plain_user não tem UserAuthzState — endpoint deve retornar 0 (default lazy)
    UserAuthzState.objects.filter(user=plain_user).delete()
    response = client_plain.get(AUTHZ_VERSION_URL)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["authz_version"] == 0


@pytest.mark.django_db
def test_authz_version_endpoint_returns_correct_version(client_plain, plain_user):
    UserAuthzState.objects.filter(user=plain_user).delete()
    UserAuthzState.objects.create(user=plain_user, authz_version=42)
    response = client_plain.get(AUTHZ_VERSION_URL)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["authz_version"] == 42


@pytest.mark.django_db
def test_authz_version_endpoint_does_not_leak_other_user(
    client_plain, plain_user, other_user
):
    """O endpoint deve retornar apenas a versão do usuário autenticado."""
    UserAuthzState.objects.filter(user=plain_user).delete()
    UserAuthzState.objects.create(user=other_user, authz_version=99)
    response = client_plain.get(AUTHZ_VERSION_URL)
    assert response.status_code == status.HTTP_200_OK
    # plain_user não tem estado — deve retornar 0, não 99.
    assert response.data["authz_version"] == 0


# ---------------------------------------------------------------------------
# 4. Integração: bump chamado por signals de UserRole
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bump_called_on_userrole_create(plain_user):
    """Criação de UserRole deve disparar bump_authz_version."""
    # plain_user sem state — qualquer UserRole criada deve gerar versão >= 1
    UserAuthzState.objects.filter(user=plain_user).delete()
    app = Aplicacao.objects.get(pk=2)  # ACOES_PNGI
    role = Role.objects.get(pk=2)  # GESTOR_PNGI
    UserRole.objects.create(user=plain_user, aplicacao=app, role=role)
    state = UserAuthzState.objects.filter(user=plain_user).first()
    assert state is not None
    assert state.authz_version >= 1


@pytest.mark.django_db
def test_bump_called_on_userrole_delete(plain_user):
    """Remoção de UserRole deve incrementar a versão."""
    app = Aplicacao.objects.get(pk=2)
    role = Role.objects.get(pk=2)
    ur = UserRole.objects.create(user=plain_user, aplicacao=app, role=role)
    version_after_create = UserAuthzState.objects.get(user=plain_user).authz_version
    ur.delete()
    version_after_delete = UserAuthzState.objects.get(user=plain_user).authz_version
    assert version_after_delete > version_after_create


# ---------------------------------------------------------------------------
# 4b. Integração: bump chamado por signals de UserPermissionOverride
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bump_called_on_override_create(plain_user):
    UserAuthzState.objects.filter(user=plain_user).delete()
    perm = Permission.objects.first()
    assert perm is not None
    UserPermissionOverride.objects.create(
        user=plain_user,
        permission=perm,
        mode=UserPermissionOverride.MODE_GRANT,
    )
    state = UserAuthzState.objects.filter(user=plain_user).first()
    assert state is not None
    assert state.authz_version >= 1


@pytest.mark.django_db
def test_bump_called_on_override_delete(plain_user):
    perm = Permission.objects.first()
    override = UserPermissionOverride.objects.create(
        user=plain_user,
        permission=perm,
        mode=UserPermissionOverride.MODE_GRANT,
    )
    version_before = UserAuthzState.objects.get(user=plain_user).authz_version
    override.delete()
    version_after = UserAuthzState.objects.get(user=plain_user).authz_version
    assert version_after > version_before


# ---------------------------------------------------------------------------
# 4c. Integração: bump chamado por m2m_changed em group.permissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bump_called_on_group_permission_add(user_with_role):
    """Adicionar permissão ao grupo do role do usuário deve incrementar versão."""
    # user_with_role já tem PORTAL_ADMIN (Role pk=1) — group portal_admin_group
    state_before = UserAuthzState.objects.filter(user=user_with_role).first()
    version_before = state_before.authz_version if state_before else 0

    role = Role.objects.get(pk=1)
    perm = Permission.objects.exclude(
        id__in=role.group.permissions.values_list("id", flat=True)
    ).first()
    if perm:
        role.group.permissions.add(perm)
        state_after = UserAuthzState.objects.filter(user=user_with_role).first()
        version_after = state_after.authz_version if state_after else 0
        assert version_after > version_before
