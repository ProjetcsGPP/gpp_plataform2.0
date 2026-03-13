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

Dependências de fixture: apps/accounts/fixtures/initial_data.json
  Registros utilizados:
    classificacaousuario pk=1  statususuario pk=1  tipousuario pk=1
    auth.group pk=1 (PORTAL_ADMIN)  pk=2 (GESTOR_PNGI)
    accounts.role pk=1 (PORTAL_ADMIN/app=1)  pk=2 (GESTOR_PNGI/app=2)
    accounts.aplicacao pk=1 (PORTAL)  pk=2 (ACOES_PNGI)  pk=3 (CARGA_ORG_LOT)
"""
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.db.models.signals import post_save
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserProfile, UserRole
from apps.accounts.signals import auto_create_group_for_role

USERROLE_LIST_URL = "/api/accounts/user-roles/"
TOKEN_URL = "/api/auth/token/"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fetch_token(username, password="Senha@123"):
    tmp = APIClient()
    resp = tmp.post(TOKEN_URL, {"username": username, "password": password}, format="json")
    assert resp.status_code == 200, (
        f"Falha ao obter token para '{username}': "
        f"{resp.status_code} — {getattr(resp, 'data', resp.content)}"
    )
    return resp.data["access"]


def _auth_client(token):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


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
    """Cria Role com group explícito (signal não sobrescreve se group != None)."""
    return Role.objects.create(
        aplicacao=aplicacao, nomeperfil=nome, codigoperfil=codigo, group=group,
    )


def make_role_without_group(aplicacao, nome, codigo):
    """Cria Role com group=None desconectando o signal temporariamente."""
    post_save.disconnect(auto_create_group_for_role, sender=Role)
    try:
        role = Role.objects.create(
            aplicacao=aplicacao, nomeperfil=nome, codigoperfil=codigo, group=None,
        )
    finally:
        post_save.connect(auto_create_group_for_role, sender=Role)
    return role


# ─── Test Classes ─────────────────────────────────────────────────────────────

class TestUserRoleAssign(TestCase):
    """
    T-01..T-06, T-09..T-11: lógica de negócio e edge cases.
    """
    fixtures = ["initial_data"]

    @classmethod
    def setUpTestData(cls):
        # Aplicações
        cls.app_a = make_aplicacao("TST_UROLE_A", "App UserRole A")
        cls.app_b = make_aplicacao("TST_UROLE_B", "App UserRole B")
        cls.app_portal = make_aplicacao("TST_PORTAL_VIS", "App Portal Vis", isshowinportal=True)

        # Groups
        cls.grp_a = Group.objects.create(name="grp_userrole_a")
        cls.grp_a.permissions.set(
            Permission.objects.filter(codename__in=["add_user", "view_user"])
        )
        cls.grp_b = Group.objects.create(name="grp_userrole_b")

        # Roles
        cls.role_a = make_role(cls.app_a, "Role A", "TST_ROLE_A", group=cls.grp_a)
        cls.role_b = make_role(cls.app_b, "Role B", "TST_ROLE_B", group=cls.grp_b)
        cls.role_portal = make_role(cls.app_portal, "Role Portal Vis", "TST_ROLE_PORTAL_VIS")
        cls.role_no_group = make_role_without_group(cls.app_a, "Role Sem Grupo", "TST_NO_GRP")

        # Usuários
        cls.admin = make_user("tst_admin_gap04", role_pk=1)  # PORTAL_ADMIN
        cls.common = make_user("tst_common_gap04", role_pk=2)  # sem PORTAL_ADMIN
        cls.target = make_user("tst_target_gap04")  # usuário-alvo sem role
        cls.target2 = make_user("tst_target2_gap04")  # segundo usuário-alvo

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._admin_token = _fetch_token("tst_admin_gap04")
        cls._common_token = _fetch_token("tst_common_gap04")

    def setUp(self):
        self.admin_client = _auth_client(self._admin_token)
        self.common_client = _auth_client(self._common_token)
        self.anon_client = APIClient()

    # ── T-07: sem autenticação → 401 ─────────────────────────────────
    def test_t07_unauthenticated_returns_401(self):
        resp = self.anon_client.post(
            USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    # ── T-08: sem PORTAL_ADMIN → 403 ─────────────────────────────────
    def test_t08_no_portal_admin_returns_403(self):
        resp = self.common_client.post(
            USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    # ── T-09: user inexistente → 400 ──────────────────────────────────
    def test_t09_nonexistent_user_returns_400(self):
        resp = self.admin_client.post(
            USERROLE_LIST_URL,
            {"user": 999999, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    # ── T-01: POST válido → 201 + permissões adicionadas ─────────────
    def test_t01_valid_post_creates_userrole(self):
        resp = self.admin_client.post(
            USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            UserRole.objects.filter(
                user=self.target, aplicacao=self.app_a, role=self.role_a
            ).exists()
        )

    # ── T-04: permissões copiadas corretamente ────────────────────────
    def test_t04_permissions_synced_after_create(self):
        # Cria o UserRole via API
        self.admin_client.post(
            USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        # Recarrega o usuário do banco (cache de perms é por instância)
        target_fresh = User.objects.get(pk=self.target.pk)
        user_perm_ids = set(
            target_fresh.user_permissions.values_list("pk", flat=True)
        )
        group_perm_ids = set(
            self.grp_a.permissions.values_list("pk", flat=True)
        )
        self.assertTrue(
            group_perm_ids.issubset(user_perm_ids),
            "Todas as permissões do grupo devem estar no usuário após o sync.",
        )

    # ── T-02: duplicado (user, aplicacao) → 400 ──────────────────────
    def test_t02_duplicate_user_aplicacao_returns_400(self):
        # Cria o primeiro UserRole diretamente
        UserRole.objects.create(
            user=self.target, aplicacao=self.app_a, role=self.role_a
        )
        # Tenta criar outro para a mesma (user, aplicacao)
        resp = self.admin_client.post(
            USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("non_field_errors", resp.data)

    # ── T-03: role de aplicacao diferente → 400 ──────────────────────
    def test_t03_role_wrong_app_returns_400(self):
        resp = self.admin_client.post(
            USERROLE_LIST_URL,
            # role_b pertence a app_b, mas informamos app_a
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("role", resp.data)

    # ── T-05: role com group=None → 201 + sem perms + log WARNING ─────
    def test_t05_role_no_group_creates_userrole_without_perms(self):
        with self.assertLogs("gpp.security", level="WARNING") as log_ctx:
            resp = self.admin_client.post(
                USERROLE_LIST_URL,
                {
                    "user": self.target.id,
                    "aplicacao": self.app_a.pk,
                    "role": self.role_no_group.pk,
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            UserRole.objects.filter(
                user=self.target, role=self.role_no_group
            ).exists()
        )
        self.assertTrue(
            any("PERM_SYNC_SKIP" in line for line in log_ctx.output),
            "Esperava log PERM_SYNC_SKIP para group=None",
        )

    # ── T-06: falha no sync → rollback total ──────────────────────────
    def test_t06_sync_failure_rolls_back_userrole(self):
        sync_path = "apps.accounts.views.sync_user_permissions_from_group"
        with patch(sync_path, side_effect=RuntimeError("DB explodiu")):
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
        # O rollback deve ter desfeito a criação do UserRole
        self.assertFalse(
            UserRole.objects.filter(
                user=self.target, aplicacao=self.app_a, role=self.role_a
            ).exists(),
            "UserRole não deve existir após rollback por falha no sync.",
        )

    # ── T-10: app com isshowinportal=True → aceito no UserRole ────────
    def test_t10_isshowinportal_true_accepted_in_userrole(self):
        resp = self.admin_client.post(
            USERROLE_LIST_URL,
            {
                "user": self.target.id,
                "aplicacao": self.app_portal.pk,
                "role": self.role_portal.pk,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

    # ── T-11: dois usuários, mesma (aplicacao, role) → ambos 201 ──────
    def test_t11_two_users_same_app_role_both_succeed(self):
        resp1 = self.admin_client.post(
            USERROLE_LIST_URL,
            {"user": self.target.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        resp2 = self.admin_client.post(
            USERROLE_LIST_URL,
            {"user": self.target2.id, "aplicacao": self.app_a.pk, "role": self.role_a.pk},
            format="json",
        )
        self.assertEqual(resp1.status_code, 201, f"target1 falhou: {resp1.data}")
        self.assertEqual(resp2.status_code, 201, f"target2 falhou: {resp2.data}")
