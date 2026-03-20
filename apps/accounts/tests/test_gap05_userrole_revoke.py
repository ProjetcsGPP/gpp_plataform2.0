"""
GAP-05 Fase 5 — Testes: UserRoleViewSet.destroy() + revoke_user_permissions_from_group

Cenários cobertos (T-01..T-10):
  T-01  DELETE UserRole com permissões exclusivas         → 204, permissões exclusivas removidas
  T-02  DELETE UserRole com permissão compartilhada       → 204, permissão compartilhada mantida
  T-03  Usuário com 2 roles em apps diferentes; remove 1  → permissões não sobrepostas removidas
  T-04  DELETE com role.group=None                        → 204, sem erro, WARNING logado
  T-05  Falha simulada na revogação (mock)                → 500, UserRole NÃO deletado (rollback)
  T-06  DELETE sem autenticação                           → 401
  T-07  DELETE autenticado sem PORTAL_ADMIN               → 403
  T-08  DELETE de UserRole inexistente                    → 404
  T-09  auth_user_user_permissions após T-01              → somente permissões das roles remanescentes
  T-10  Usuário sem role remanescente após DELETE         → auth_user_user_permissions vazio

Pós-Fase-0: autenticação via force_login + patch_security.
Removidos: _fetch_token, _make_authenticated_client, TOKEN_URL, Bearer, /api/auth/token/.
"""
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserProfile, UserRole
from apps.accounts.services.permission_sync import revoke_user_permissions_from_group
from apps.accounts.signals import auto_create_group_for_role
from apps.core.tests.utils import patch_security

USER_ROLES_URL = "/api/accounts/user-roles/"


# ─── Helpers ─────────────────────────────────────────────────────────────────────────────────

def make_user(username, role_pk=None):
    user = User.objects.create_user(
        username=username, password="Senha@123", email=f"{username}@test.com",
    )
    UserProfile.objects.create(
        user=user, name=username, orgao="TEST",
        status_usuario_id=1, tipo_usuario_id=1, classificacao_usuario_id=1,
        idusuariocriacao=user,
    )
    if role_pk is not None:
        role = Role.objects.get(pk=role_pk)
        UserRole.objects.create(user=user, role=role, aplicacao=role.aplicacao)
    return user


def make_aplicacao(codigo, nome):
    return Aplicacao.objects.create(
        codigointerno=codigo, nomeaplicacao=nome,
        base_url=f"http://{codigo.lower()}.test",
        isshowinportal=False,
    )


def make_role(aplicacao, nome, codigo, group=None):
    return Role.objects.create(
        aplicacao=aplicacao, nomeperfil=nome, codigoperfil=codigo, group=group,
    )


def make_role_without_group(aplicacao, nome, codigo):
    post_save.disconnect(auto_create_group_for_role, sender=Role)
    try:
        role = Role.objects.create(
            aplicacao=aplicacao, nomeperfil=nome, codigoperfil=codigo, group=None,
        )
    finally:
        post_save.connect(auto_create_group_for_role, sender=Role)
    return role


def make_permission(codename, name=None):
    ct = ContentType.objects.get_for_model(User)
    perm, _ = Permission.objects.get_or_create(
        codename=codename, content_type=ct,
        defaults={"name": name or codename},
    )
    return perm


def _admin_client(admin_user):
    c = APIClient()
    c.force_login(admin_user)
    return c


def _patched_delete(client, actor, url, is_portal_admin=True):
    patches = patch_security(actor, is_portal_admin=is_portal_admin)
    with patches[0], patches[1], patches[2]:
        return client.delete(url)


# ─── TestUserRoleRevoke (T-01..T-10) ────────────────────────────────────────────────

class TestUserRoleRevoke(TestCase):
    fixtures = ["initial_data"]

    @classmethod
    def setUpTestData(cls):
        cls.app_a = make_aplicacao("TST_REVOKE_A", "App Revoke A")
        cls.app_b = make_aplicacao("TST_REVOKE_B", "App Revoke B")

        cls.group_a = Group.objects.create(name="tst_grp_revoke_a")
        cls.group_b = Group.objects.create(name="tst_grp_revoke_b")

        cls.perm_exclusive_a = make_permission("tst_revoke_exclusive_a", "Exclusiva Grupo A")
        cls.perm_shared = make_permission("tst_revoke_shared", "Compartilhada A e B")
        cls.perm_exclusive_b = make_permission("tst_revoke_exclusive_b", "Exclusiva Grupo B")

        cls.group_a.permissions.add(cls.perm_exclusive_a, cls.perm_shared)
        cls.group_b.permissions.add(cls.perm_exclusive_b, cls.perm_shared)

        cls.role_a = make_role(cls.app_a, "Role A Revoke", "TST_REVOKE_ROLE_A", group=cls.group_a)
        cls.role_b = make_role(cls.app_b, "Role B Revoke", "TST_REVOKE_ROLE_B", group=cls.group_b)

        cls.admin_user = make_user("tst_admin_revoke", role_pk=1)

    def setUp(self):
        self.admin_client = _admin_client(self.admin_user)
        self.anon_client = APIClient()

    def _create_userrole(self, user, role, aplicacao):
        from apps.accounts.services.permission_sync import sync_user_permissions_from_group
        ur = UserRole.objects.create(user=user, role=role, aplicacao=aplicacao)
        sync_user_permissions_from_group(user=user, group=role.group)
        return ur

    def _user_perm_ids(self, user):
        user.refresh_from_db()
        return set(user.user_permissions.values_list("pk", flat=True))

    # ── T-06: sem autenticação → 401 ──────────────────────────────────
    def test_t06_unauthenticated_returns_401(self):
        response = self.anon_client.delete(f"{USER_ROLES_URL}99999/")
        self.assertEqual(response.status_code, 401)

    # ── T-07: autenticado sem PORTAL_ADMIN → 403 ─────────────────────────
    def test_t07_no_portal_admin_returns_403(self):
        common_user = make_user("tst_common_revoke_t07", role_pk=2)
        client = _admin_client(common_user)
        patches = patch_security(common_user, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            response = client.delete(f"{USER_ROLES_URL}99999/")
        self.assertEqual(response.status_code, 403)

    # ── T-08: DELETE de UserRole inexistente → 404 ───────────────────────
    def test_t08_nonexistent_userrole_returns_404(self):
        response = _patched_delete(self.admin_client, self.admin_user, f"{USER_ROLES_URL}99999/")
        self.assertEqual(response.status_code, 404)

    # ── T-01: DELETE com permissões exclusivas → 204, exclusivas removidas ──
    def test_t01_exclusive_permissions_revoked(self):
        target_user = make_user("tst_target_t01")
        ur = self._create_userrole(target_user, self.role_a, self.app_a)
        perm_ids_before = self._user_perm_ids(target_user)
        self.assertIn(self.perm_exclusive_a.pk, perm_ids_before)
        self.assertIn(self.perm_shared.pk, perm_ids_before)
        response = _patched_delete(self.admin_client, self.admin_user, f"{USER_ROLES_URL}{ur.pk}/")
        self.assertEqual(response.status_code, 204)
        perm_ids_after = self._user_perm_ids(target_user)
        self.assertNotIn(self.perm_exclusive_a.pk, perm_ids_after)
        self.assertNotIn(self.perm_shared.pk, perm_ids_after)

    # ── T-02: DELETE com permissão compartilhada → 204, compartilhada mantida ─
    def test_t02_shared_permission_preserved(self):
        target_user = make_user("tst_target_t02")
        ur_a = self._create_userrole(target_user, self.role_a, self.app_a)
        ur_b = self._create_userrole(target_user, self.role_b, self.app_b)
        perm_ids_before = self._user_perm_ids(target_user)
        self.assertIn(self.perm_shared.pk, perm_ids_before)
        response = _patched_delete(self.admin_client, self.admin_user, f"{USER_ROLES_URL}{ur_a.pk}/")
        self.assertEqual(response.status_code, 204)
        perm_ids_after = self._user_perm_ids(target_user)
        self.assertNotIn(self.perm_exclusive_a.pk, perm_ids_after)
        self.assertIn(self.perm_shared.pk, perm_ids_after)
        self.assertIn(self.perm_exclusive_b.pk, perm_ids_after)

    # ── T-03: 2 roles em apps diferentes; remove 1 ───────────────────────
    def test_t03_two_roles_different_apps_remove_one(self):
        target_user = make_user("tst_target_t03")
        ur_a = self._create_userrole(target_user, self.role_a, self.app_a)
        ur_b = self._create_userrole(target_user, self.role_b, self.app_b)
        response = _patched_delete(self.admin_client, self.admin_user, f"{USER_ROLES_URL}{ur_b.pk}/")
        self.assertEqual(response.status_code, 204)
        perm_ids_after = self._user_perm_ids(target_user)
        self.assertNotIn(self.perm_exclusive_b.pk, perm_ids_after)
        self.assertIn(self.perm_exclusive_a.pk, perm_ids_after)
        self.assertIn(self.perm_shared.pk, perm_ids_after)
        self.assertFalse(UserRole.objects.filter(pk=ur_b.pk).exists())

    # ── T-04: DELETE com role.group=None → 204, sem erro, WARNING logado ───
    def test_t04_role_group_none_returns_204_no_error(self):
        target_user = make_user("tst_target_t04")
        role_no_group = make_role_without_group(self.app_a, "Role Sem Grupo T04", "TST_REVOKE_NO_GRP")
        ur = UserRole.objects.create(
            user=target_user, role=role_no_group, aplicacao=self.app_a
        )
        with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
            response = _patched_delete(self.admin_client, self.admin_user, f"{USER_ROLES_URL}{ur.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(UserRole.objects.filter(pk=ur.pk).exists())
        self.assertTrue(
            any("PERM_REVOKE_SKIP" in msg for msg in log_ctx.output),
            "Esperado log WARNING PERM_REVOKE_SKIP",
        )

    # ── T-05: falha simulada na revogação → 500 + rollback ──────────────
    def test_t05_revocation_failure_triggers_rollback(self):
        target_user = make_user("tst_target_t05")
        ur = self._create_userrole(target_user, self.role_a, self.app_a)
        ur_pk = ur.pk
        patches = patch_security(self.admin_user, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(
                 "apps.accounts.views.revoke_user_permissions_from_group",
                 side_effect=Exception("Erro simulado na revogação"),
             ):
            with self.assertRaises(Exception):
                self.admin_client.delete(f"{USER_ROLES_URL}{ur_pk}/")
        self.assertTrue(
            UserRole.objects.filter(pk=ur_pk).exists(),
            "UserRole deveria existir após rollback",
        )

    # ── T-09 ───────────────────────────────────────────────────────────────────────────────
    def test_t09_user_permissions_reflect_remaining_roles(self):
        target_user = make_user("tst_target_t09")
        ur_a = self._create_userrole(target_user, self.role_a, self.app_a)
        ur_b = self._create_userrole(target_user, self.role_b, self.app_b)
        response = _patched_delete(self.admin_client, self.admin_user, f"{USER_ROLES_URL}{ur_a.pk}/")
        self.assertEqual(response.status_code, 204)
        perm_ids_after = self._user_perm_ids(target_user)
        expected_perm_ids = set(self.group_b.permissions.values_list("pk", flat=True))
        self.assertTrue(expected_perm_ids.issubset(perm_ids_after), "Permissões do grupo B devem permanecer")
        self.assertNotIn(self.perm_exclusive_a.pk, perm_ids_after)

    # ── T-10 ──────────────────────────────────────────────────────────────────────────────
    def test_t10_no_remaining_roles_permissions_empty(self):
        target_user = make_user("tst_target_t10")
        ur = self._create_userrole(target_user, self.role_a, self.app_a)
        perm_ids_before = self._user_perm_ids(target_user)
        self.assertGreater(len(perm_ids_before), 0)
        response = _patched_delete(self.admin_client, self.admin_user, f"{USER_ROLES_URL}{ur.pk}/")
        self.assertEqual(response.status_code, 204)
        perm_ids_after = self._user_perm_ids(target_user)
        self.assertEqual(len(perm_ids_after), 0, f"Esperado 0 permissões, encontrado: {perm_ids_after}")


# ─── TestRevokePermissionUnit ───────────────────────────────────────────────────────────────

class TestRevokePermissionUnit(TestCase):
    """
    Testes unitários diretos de revoke_user_permissions_from_group().
    Não passam pela API — não precisam de autenticação nem patch_security.
    """
    fixtures = ["initial_data"]

    @classmethod
    def setUpTestData(cls):
        cls.app_x = make_aplicacao("TST_UNIT_REVOKE_X", "App Unit Revoke X")
        cls.app_y = make_aplicacao("TST_UNIT_REVOKE_Y", "App Unit Revoke Y")

        cls.group_x = Group.objects.create(name="tst_grp_unit_x")
        cls.group_y = Group.objects.create(name="tst_grp_unit_y")

        cls.perm_x = make_permission("tst_unit_exclusive_x", "Exclusiva X")
        cls.perm_xy = make_permission("tst_unit_shared_xy", "Compartilhada X e Y")
        cls.perm_y = make_permission("tst_unit_exclusive_y", "Exclusiva Y")

        cls.group_x.permissions.add(cls.perm_x, cls.perm_xy)
        cls.group_y.permissions.add(cls.perm_y, cls.perm_xy)

        cls.role_x = make_role(cls.app_x, "Role X", "TST_UNIT_ROLE_X", group=cls.group_x)
        cls.role_y = make_role(cls.app_y, "Role Y", "TST_UNIT_ROLE_Y", group=cls.group_y)

    def _make_user_with_roles(self, username, roles):
        from apps.accounts.services.permission_sync import sync_user_permissions_from_group
        user = make_user(username)
        for role in roles:
            UserRole.objects.create(user=user, role=role, aplicacao=role.aplicacao)
            sync_user_permissions_from_group(user=user, group=role.group)
        return user

    def test_revoke_group_none_returns_zero(self):
        user = make_user("tst_unit_none_grp")
        result = revoke_user_permissions_from_group(user=user, group_removed=None)
        self.assertEqual(result, 0)

    def test_revoke_removes_exclusive_permissions(self):
        user = self._make_user_with_roles("tst_unit_exclusive", [self.role_x])
        result = revoke_user_permissions_from_group(user=user, group_removed=self.group_x)
        self.assertGreater(result, 0)
        perm_ids = set(user.user_permissions.values_list("pk", flat=True))
        self.assertNotIn(self.perm_x.pk, perm_ids)

    def test_revoke_preserves_shared_permission_when_other_group_active(self):
        user = self._make_user_with_roles("tst_unit_shared", [self.role_x, self.role_y])
        revoke_user_permissions_from_group(user=user, group_removed=self.group_x)
        perm_ids = set(user.user_permissions.values_list("pk", flat=True))
        self.assertIn(self.perm_xy.pk, perm_ids)
        self.assertNotIn(self.perm_x.pk, perm_ids)
        self.assertIn(self.perm_y.pk, perm_ids)

    def test_revoke_returns_count_of_removed_permissions(self):
        user = self._make_user_with_roles("tst_unit_count", [self.role_x])
        result = revoke_user_permissions_from_group(user=user, group_removed=self.group_x)
        self.assertEqual(result, 2)

    def test_revoke_empty_group_returns_zero(self):
        empty_group = Group.objects.create(name="tst_grp_empty_revoke")
        user = make_user("tst_unit_empty_grp")
        result = revoke_user_permissions_from_group(user=user, group_removed=empty_group)
        self.assertEqual(result, 0)
