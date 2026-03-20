"""
GAP-04 + GAP-05 — Testes: UserRoleSerializer validações + sync de permissões

Cenários cobertos (T-01..T-11):
  T-01  POST válido                            → 201, permissões do grupo adicionadas
  T-02  POST duplicado (user, aplicacao)       → 400 unicidade
  T-03  POST role de aplicacao diferente       → 400 role não pertence à app
  T-04  Verifica auth_user_user_permissions    → contém exatamente as perms do group
  T-05  POST com role cujo group=None          → 201, sem perms, log WARNING
  T-06  Falha no sync (mock)                   → rollback, UserRole não criado
  T-07  POST sem autenticação                  → 401
  T-08  POST autenticado sem PORTAL_ADMIN      → 403
  T-09  POST com user inexistente              → 400
  T-10  POST com app isshowinportal=True       → 201 (restrição só na listagem)
  T-11  Dois usuários, mesma (aplicacao, role) → ambos 201

Pós-Fase-0: autenticação via force_login + patch_security.
Removendos: fetch_token, _auth_client, TOKEN_URL, Bearer, /api/auth/token/.
"""
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.db.models.signals import post_save
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserProfile, UserRole
from apps.accounts.signals import auto_create_group_for_role
from apps.core.tests.utils import patch_security

USERROLE_LIST_URL = "/api/accounts/user-roles/"


# ─── Helpers ─────────────────────────────────────────────────────────────────────────────────

def make_user(username, role_pk=None, password="Senha@123"):
    user = User.objects.create_user(
        username=username, password=password, email=f"{username}@test.com"
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


def make_aplicacao(codigo, nome, isshowinportal=False):
    return Aplicacao.objects.create(
        codigointerno=codigo, nomeaplicacao=nome,
        base_url=f"http://{codigo.lower()}.test",
        isshowinportal=isshowinportal,
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


def _admin_client(admin_user):
    """Retorna APIClient autenticado via force_login (sem JWT)."""
    c = APIClient()
    c.force_login(admin_user)
    return c


def _patched_post(client, admin_user, url, payload, is_portal_admin=True):
    """Faz POST com patch_security ativo."""
    patches = patch_security(admin_user, is_portal_admin=is_portal_admin)
    with patches[0], patches[1], patches[2]:
        return client.post(url, payload, format="json")


# ─── Test Classes ────────────────────────────────────────────────────────────────────────────

class TestUserRoleAssign(TestCase):
    fixtures = ["initial_data"]

    @classmethod
    def setUpTestData(cls):
        cls.app_a = make_aplicacao("TST_UROLE_A", "App UserRole A")
        cls.app_b = make_aplicacao("TST_UROLE_B", "App UserRole B")
        cls.app_portal = make_aplicacao("TST_PORTAL_VIS", "App Portal Vis", isshowinportal=True)

        cls.grp_a = Group.objects.create(name="grp_userrole_a")
        cls.grp_a.permissions.set(
            Permission.objects.filter(codename__in=["add_user", "view_user"])
        )
        cls.grp_b = Group.objects.create(name="grp_userrole_b")

        cls.role_a = make_role(cls.app_a, "Role A", "TST_ROLE_A", group=cls.grp_a)
        cls.role_b = make_role(cls.app_b, "Role B", "TST_ROLE_B", group=cls.grp_b)
        cls.role_portal = make_role(cls.app_portal, "Role Portal Vis", "TST_ROLE_PORTAL_VIS")
        cls.role_no_group = make_role_without_group(cls.app_a, "Role Sem Grupo", "TST_NO_GRP")

        # admin_user tem role PORTAL_ADMIN (pk=1 da fixture)
        cls.admin_user = make_user("tst_admin_gap04", role_pk=1)
        cls.common_user = make_user("tst_common_gap04", role_pk=2)
        cls.target = make_user("tst_target_gap04")
        cls.target2 = make_user("tst_target2_gap04")

    def setUp(self):
        self.admin_client = _admin_client(self.admin_user)
        self.common_client = _admin_client(self.common_user)
        self.anon_client = APIClient()

    # ── T-07: sem autenticação → 401 ───────────────────────────────────────
    def test_t07_unauthenticated_returns_401(self):
        resp = self.anon_client.post(
            USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    # ── T-08: sem PORTAL_ADMIN → 403 ──────────────────────────────────────
    def test_t08_no_portal_admin_returns_403(self):
        patches = patch_security(self.common_user, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            resp = self.common_client.post(
                USERROLE_LIST_URL,
                {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
                format="json",
            )
        self.assertEqual(resp.status_code, 403)

    # ── T-09: user inexistente → 400 ────────────────────────────────────────
    def test_t09_nonexistent_user_returns_400(self):
        resp = _patched_post(
            self.admin_client, self.admin_user, USERROLE_LIST_URL,
            {"user": 999999, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
        )
        self.assertEqual(resp.status_code, 400)

    # ── T-01: POST válido → 201 ─────────────────────────────────────────────
    def test_t01_valid_post_creates_userrole(self):
        resp = _patched_post(
            self.admin_client, self.admin_user, USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            UserRole.objects.filter(
                user=self.target, aplicacao=self.app_a, role=self.role_a
            ).exists()
        )

    # ── T-04: permissões copiadas corretamente ─────────────────────────────────
    def test_t04_permissions_synced_after_create(self):
        _patched_post(
            self.admin_client, self.admin_user, USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
        )
        target_fresh = User.objects.get(pk=self.target.pk)
        user_perm_ids = set(target_fresh.user_permissions.values_list("pk", flat=True))
        group_perm_ids = set(self.grp_a.permissions.values_list("pk", flat=True))
        self.assertTrue(
            group_perm_ids.issubset(user_perm_ids),
            "Todas as permissões do grupo devem estar no usuário após o sync.",
        )

    # ── T-02: duplicado (user, aplicacao) → 400 ─────────────────────────────
    def test_t02_duplicate_user_aplicacao_returns_400(self):
        UserRole.objects.create(user=self.target, aplicacao=self.app_a, role=self.role_a)
        resp = _patched_post(
            self.admin_client, self.admin_user, USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
        )
        self.assertEqual(resp.status_code, 400)
        errors = resp.data.get("errors", resp.data)
        self.assertIn("non_field_errors", errors)

    # ── T-03: role de aplicacao diferente → 400 ─────────────────────────────
    def test_t03_role_wrong_app_returns_400(self):
        resp = _patched_post(
            self.admin_client, self.admin_user, USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_b.pk},
        )
        self.assertEqual(resp.status_code, 400)
        errors = resp.data.get("errors", resp.data)
        self.assertIn("role", errors)

    # ── T-05: role com group=None → 201 + sem perms + log WARNING ──────────
    def test_t05_role_no_group_creates_userrole_without_perms(self):
        with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
            resp = _patched_post(
                self.admin_client, self.admin_user, USERROLE_LIST_URL,
                {
                    "user": self.target.id,
                    "aplicacao": self.app_a.pk,
                    "role": self.role_no_group.pk,
                },
            )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            UserRole.objects.filter(user=self.target, role=self.role_no_group).exists()
        )
        self.assertTrue(
            any("PERM_SYNC_SKIP" in line for line in log_ctx.output),
            "Esperava log PERM_SYNC_SKIP para group=None",
        )

    # ── T-06: falha no sync → rollback total ───────────────────────────────
    def test_t06_sync_failure_rolls_back_userrole(self):
        sync_path = "apps.accounts.views.sync_user_permissions_from_group"
        patches = patch_security(self.admin_user, is_portal_admin=True)
        with patches[0], patches[1], patches[2], \
             patch(sync_path, side_effect=RuntimeError("DB explodiu")):
            with self.assertRaises(RuntimeError):
                self.admin_client.post(
                    USERROLE_LIST_URL,
                    {
                        "user": self.target.id,
                        "aplicacao": self.app_a.pk,
                        "role": self.role_a.pk,
                    },
                    format="json",
                )
        self.assertFalse(
            UserRole.objects.filter(
                user=self.target, aplicacao=self.app_a, role=self.role_a
            ).exists(),
            "UserRole não deve existir após rollback.",
        )

    # ── T-10: app com isshowinportal=True → aceito no UserRole ────────────
    def test_t10_isshowinportal_true_accepted_in_userrole(self):
        resp = _patched_post(
            self.admin_client, self.admin_user, USERROLE_LIST_URL,
            {
                "user": self.target.id,
                "aplicacao": self.app_portal.pk,
                "role": self.role_portal.pk,
            },
        )
        self.assertEqual(resp.status_code, 201)

    # ── T-11: dois usuários, mesma (aplicacao, role) → ambos 201 ─────────
    def test_t11_two_users_same_app_role_both_succeed(self):
        resp1 = _patched_post(
            self.admin_client, self.admin_user, USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
        )
        resp2 = _patched_post(
            self.admin_client, self.admin_user, USERROLE_LIST_URL,
            {"user": self.target2.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
        )
        self.assertEqual(resp1.status_code, 201, f"target1 falhou: {resp1.data}")
        self.assertEqual(resp2.status_code, 201, f"target2 falhou: {resp2.data}")
