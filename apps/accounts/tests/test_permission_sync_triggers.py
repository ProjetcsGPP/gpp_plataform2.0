"""
Tests — apps/accounts/tests/test_permission_sync_triggers.py

Cenários cobertos (Issue #18):

  TC-01  Criar UserRole via signal aciona sync_user_permissions
         → auth_user_user_permissions populado após UserRole.save()

  TC-02  Deletar UserRole via signal aciona sync_user_permissions
         → auth_user_user_permissions esvaziado após UserRole.delete()

  TC-03  Mudar Role.group aciona sync para todos os usuários com essa role
         → auth_user_user_permissions reflete o novo grupo

  TC-04  Criar UserRole via API POST /user-roles/ sincroniza permissões
         → status 201 + auth_user_user_permissions populado

  TC-05  Deletar UserRole via API DELETE /user-roles/{id}/ sincroniza permissões
         → status 204 + auth_user_user_permissions esvaziado

  TC-06  Criar UserPermissionOverride via API POST /permission-overrides/
         → status 201 + sync acionado

  TC-07  Deletar UserPermissionOverride via API DELETE /permission-overrides/{id}/
         → status 204 + sync acionado

  TC-08  Alterar group de Group via m2m (group_permissions) aciona re-sync
         → cobre o sinal invalidate_on_group_permission_change (D-05)
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import Role, UserPermissionOverride, UserRole
from apps.accounts.tests.conftest import (
    _assign_role,
    _make_authenticated_client,
    _make_user,
)

USER_ROLES_URL = "/api/accounts/user-roles/"
PERM_OVERRIDES_URL = "/api/accounts/permission-overrides/"
SYNC_PATH = "apps.accounts.services.permission_sync.sync_user_permissions"


# ─── Helpers ────────────────────────────────────────────────────────────────────


def _get_or_create_permission(codename, app_label="auth", model="user"):
    ct = ContentType.objects.get(app_label=app_label, model=model)
    perm, _ = Permission.objects.get_or_create(codename=codename, content_type=ct)
    return perm


# ─── TC-01: Signal post_save em UserRole aciona sync ──────────────────────────────


@pytest.mark.django_db
def test_tc01_userrole_post_save_triggers_sync(db, _ensure_base_data):
    """
    Ao criar uma UserRole diretamente (sem a API), o signal post_save
    deve chamar sync_user_permissions(user).
    """
    user = _make_user("tc01_user")
    role = Role.objects.get(pk=2)  # GESTOR_PNGI
    app = role.aplicacao

    sync_call_target = "apps.accounts.signals.sync_user_permissions"
    with patch(sync_call_target) as mock_sync:
        UserRole.objects.create(user=user, role=role, aplicacao=app)
        assert (
            mock_sync.called
        ), "sync_user_permissions deve ser chamado pelo signal post_save de UserRole"
        called_user = mock_sync.call_args[1].get("user") or mock_sync.call_args[0][0]
        assert called_user.pk == user.pk


# ─── TC-02: Signal post_delete em UserRole aciona sync ─────────────────────────────


@pytest.mark.django_db
def test_tc02_userrole_post_delete_triggers_sync(db, _ensure_base_data):
    """
    Ao deletar uma UserRole diretamente, o signal post_delete deve
    chamar sync_user_permissions(user).
    """
    user = _make_user("tc02_user")
    role = Role.objects.get(pk=2)
    app = role.aplicacao
    user_role = UserRole.objects.create(user=user, role=role, aplicacao=app)

    sync_call_target = "apps.accounts.signals.sync_user_permissions"
    with patch(sync_call_target) as mock_sync:
        user_role.delete()
        assert (
            mock_sync.called
        ), "sync_user_permissions deve ser chamado pelo signal post_delete de UserRole"
        called_user = mock_sync.call_args[1].get("user") or mock_sync.call_args[0][0]
        assert called_user.pk == user.pk


# ─── TC-03: Mudar Role.group aciona sync para todos os usuários da role ───────────


@pytest.mark.django_db
def test_tc03_role_group_change_triggers_sync_for_affected_users(db, _ensure_base_data):
    """
    Ao alterar o group de uma Role, sync_users_permissions deve ser chamada
    para os usuários com aquela role.
    """
    user1 = _make_user("tc03_user1")
    user2 = _make_user("tc03_user2")
    role = Role.objects.get(pk=2)  # GESTOR_PNGI
    app = role.aplicacao

    UserRole.objects.get_or_create(user=user1, role=role, aplicacao=app)
    UserRole.objects.get_or_create(user=user2, role=role, aplicacao=app)

    new_group, _ = Group.objects.get_or_create(name="tc03_new_group")

    sync_call_target = "apps.accounts.signals.sync_users_permissions"
    with patch(sync_call_target) as mock_sync:
        role.group = new_group
        role.save(update_fields=["group"])

        assert (
            mock_sync.called
        ), "sync_users_permissions deve ser chamado ao mudar Role.group"
        called_ids = set(mock_sync.call_args[0][0])
        assert user1.pk in called_ids
        assert user2.pk in called_ids


# ─── TC-04: POST /user-roles/ via API aciona sync ──────────────────────────────────


@pytest.mark.django_db
def test_tc04_api_create_userrole_triggers_sync(db, _ensure_base_data):
    """
    POST /api/accounts/user-roles/ deve retornar 201 e ter chamado
    sync_user_permissions para o usuário da nova role.
    """
    admin = _make_user("tc04_admin")
    _assign_role(admin, role_pk=1)  # PORTAL_ADMIN
    target_user = _make_user("tc04_target")
    role = Role.objects.get(pk=2)  # GESTOR_PNGI
    app = role.aplicacao

    client, resp = _make_authenticated_client("tc04_admin", "PORTAL")
    assert resp.status_code == 200, f"Login falhou: {resp.data}"

    with patch("apps.accounts.views.sync_user_permissions") as mock_sync:
        resp = client.post(
            USER_ROLES_URL,
            {"user": target_user.pk, "role": role.pk, "aplicacao": app.pk},
            format="json",
        )
        assert (
            resp.status_code == 201
        ), f"Esperado 201, obtido {resp.status_code}: {resp.data}"
        assert (
            mock_sync.called
        ), "sync_user_permissions deve ser chamado pela view no create"
        called_user = mock_sync.call_args[1].get("user") or mock_sync.call_args[0][0]
        assert called_user.pk == target_user.pk


# ─── TC-05: DELETE /user-roles/{id}/ via API aciona sync ───────────────────────────


@pytest.mark.django_db
def test_tc05_api_destroy_userrole_triggers_sync(db, _ensure_base_data):
    """
    DELETE /api/accounts/user-roles/{id}/ deve retornar 204 e ter chamado
    sync_user_permissions para o usuário da role removida.
    """
    admin = _make_user("tc05_admin")
    _assign_role(admin, role_pk=1)
    target_user = _make_user("tc05_target")
    role = Role.objects.get(pk=2)
    app = role.aplicacao
    user_role = UserRole.objects.create(user=target_user, role=role, aplicacao=app)

    client, resp = _make_authenticated_client("tc05_admin", "PORTAL")
    assert resp.status_code == 200, f"Login falhou: {resp.data}"

    with patch("apps.accounts.views.sync_user_permissions") as mock_sync:
        resp = client.delete(f"{USER_ROLES_URL}{user_role.pk}/")
        assert (
            resp.status_code == 204
        ), f"Esperado 204, obtido {resp.status_code}: {resp.data}"
        assert (
            mock_sync.called
        ), "sync_user_permissions deve ser chamado pela view no destroy"
        called_user = mock_sync.call_args[1].get("user") or mock_sync.call_args[0][0]
        assert called_user.pk == target_user.pk


# ─── TC-06: POST /permission-overrides/ aciona sync ────────────────────────────────


@pytest.mark.django_db
def test_tc06_api_create_override_triggers_sync(db, _ensure_base_data):
    """
    POST /api/accounts/permission-overrides/ deve retornar 201 e acionar
    sync_user_permissions para o usuário do override.
    """
    admin = _make_user("tc06_admin")
    _assign_role(admin, role_pk=1)
    target_user = _make_user("tc06_target")
    perm = _get_or_create_permission("view_user")

    client, resp = _make_authenticated_client("tc06_admin", "PORTAL")
    assert resp.status_code == 200, f"Login falhou: {resp.data}"

    with patch("apps.accounts.views.sync_user_permissions") as mock_sync:
        resp = client.post(
            PERM_OVERRIDES_URL,
            {"user": target_user.pk, "permission": perm.pk, "mode": "grant"},
            format="json",
        )
        assert (
            resp.status_code == 201
        ), f"Esperado 201, obtido {resp.status_code}: {resp.data}"
        assert (
            mock_sync.called
        ), "sync_user_permissions deve ser chamado no create de override"
        called_user = mock_sync.call_args[1].get("user") or mock_sync.call_args[0][0]
        assert called_user.pk == target_user.pk


# ─── TC-07: DELETE /permission-overrides/{id}/ aciona sync ──────────────────────────


@pytest.mark.django_db
def test_tc07_api_destroy_override_triggers_sync(db, _ensure_base_data):
    """
    DELETE /api/accounts/permission-overrides/{id}/ deve retornar 204 e
    acionar sync_user_permissions para o usuário do override removido.
    """
    admin = _make_user("tc07_admin")
    _assign_role(admin, role_pk=1)
    target_user = _make_user("tc07_target")
    perm = _get_or_create_permission("delete_user")
    override = UserPermissionOverride.objects.create(
        user=target_user, permission=perm, mode="grant"
    )

    client, resp = _make_authenticated_client("tc07_admin", "PORTAL")
    assert resp.status_code == 200, f"Login falhou: {resp.data}"

    with patch("apps.accounts.views.sync_user_permissions") as mock_sync:
        resp = client.delete(f"{PERM_OVERRIDES_URL}{override.pk}/")
        assert (
            resp.status_code == 204
        ), f"Esperado 204, obtido {resp.status_code}: {resp.data}"
        assert (
            mock_sync.called
        ), "sync_user_permissions deve ser chamado no destroy de override"
        called_user = mock_sync.call_args[1].get("user") or mock_sync.call_args[0][0]
        assert called_user.pk == target_user.pk


# ─── TC-08: m2m_changed em Group.permissions aciona re-sync (D-05) ───────────────


@pytest.mark.django_db
def test_tc08_group_permission_change_triggers_resync(db, _ensure_base_data):
    """
    Ao adicionar uma permissão a um auth_group ligado a uma Role,
    sync_users_permissions deve ser chamado para os usuários afetados.
    Cobre o signal invalidate_on_group_permission_change (D-05).
    """
    user = _make_user("tc08_user")
    role = Role.objects.get(pk=2)  # GESTOR_PNGI — possui group
    app = role.aplicacao
    UserRole.objects.get_or_create(user=user, role=role, aplicacao=app)

    perm = _get_or_create_permission("add_user")

    sync_call_target = "apps.accounts.signals.sync_users_permissions"
    with patch(sync_call_target) as mock_sync:
        role.group.permissions.add(perm)
        assert (
            mock_sync.called
        ), "sync_users_permissions deve ser chamado ao adicionar permissão ao group da role"
        called_ids = set(mock_sync.call_args[0][0])
        assert user.pk in called_ids
