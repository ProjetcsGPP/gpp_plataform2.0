"""
GAP-03 — Testes: RoleSerializer + RoleViewSet com filtro por aplicacao_id

Cenários cobertos (T-01..T-11):
  T-01  GET ?aplicacao_id=<id_válido>          → 200, só roles da app
  T-02  GET /roles/ sem query param            → 200, todas as roles
  T-03  GET ?aplicacao_id=abc                  → 200, lista vazia
  T-04  GET ?aplicacao_id=99999 (inexistente)  → 200, lista vazia
  T-05  GET ?aplicacao_id=<app_sem_roles>      → 200, lista vazia
  T-06  Isolamento entre apps (3 + 2)          → contagens corretas
  T-07  Role com group=None                    → group_id/group_name null sem erro
  T-08  Campos do serializer presentes         → todos os 8 campos na resposta
  T-09  GET sem autenticação                   → 401
  T-10  GET autenticado sem PORTAL_ADMIN       → 403
  T-11  POST /api/accounts/roles/              → 405
"""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserProfile, UserRole


# ─── Helpers ──────────────────────────────────────────────────────────────────────

def make_user(username, password="senha@123", is_admin=False):
    """Cria auth.User + UserProfile (status ativo) e opcionalmente Role PORTAL_ADMIN."""
    user = User.objects.create_user(username=username, password=password, email=f"{username}@test.com")
    # status_usuario FK=1 (Ativo) — ajuste se o fixture usar outro id
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao="TEST",
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario_id=1,
        idusuariocriacao=user,
    )
    if is_admin:
        # Garante role PORTAL_ADMIN para que IsPortalAdmin passe
        admin_role, _ = Role.objects.get_or_create(
            codigoperfil="PORTAL_ADMIN",
            defaults={"nomeperfil": "Portal Admin", "aplicacao": Aplicacao.objects.first()},
        )
        UserRole.objects.create(user=user, role=admin_role, aplicacao=admin_role.aplicacao)
    return user


def make_aplicacao(codigo, nome="App Teste"):
    return Aplicacao.objects.create(
        codigointerno=codigo,
        nomeaplicacao=nome,
        base_url=f"http://{codigo}.test",
        isshowinportal=False,
    )


def make_role(aplicacao, nome, codigo, group=None):
    return Role.objects.create(
        aplicacao=aplicacao,
        nomeperfil=nome,
        codigoperfil=codigo,
        group=group,
    )


ROLES_LIST_URL = "/api/accounts/roles/"


# ─── Tests ────────────────────────────────────────────────────────────────────────

class TestRoleViewSetFilter(TestCase):
    """
    Cobre T-01..T-06 e T-09..T-11.
    """

    @classmethod
    def setUpTestData(cls):
        cls.app_a = make_aplicacao("APP_A", "Aplicação A")
        cls.app_b = make_aplicacao("APP_B", "Aplicação B")
        cls.app_empty = make_aplicacao("APP_EMPTY", "App Sem Roles")

        # 3 roles para app_a, 2 para app_b
        cls.role_a1 = make_role(cls.app_a, "Visualizador", "VIS_A")
        cls.role_a2 = make_role(cls.app_a, "Editor", "EDIT_A")
        cls.role_a3 = make_role(cls.app_a, "Admin", "ADMIN_A")
        cls.role_b1 = make_role(cls.app_b, "Leitor", "READ_B")
        cls.role_b2 = make_role(cls.app_b, "Gravador", "WRITE_B")

        cls.admin_user = make_user("admin_gap03", is_admin=True)
        cls.common_user = make_user("common_gap03", is_admin=False)

    def setUp(self):
        self.client = APIClient()

    # ── T-09: sem autenticação → 401 ─────────────────────────────
    def test_t09_unauthenticated_returns_401(self):
        response = self.client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 401)

    # ── T-10: autenticado sem PORTAL_ADMIN → 403 ─────────────────
    def test_t10_no_portal_admin_returns_403(self):
        self.client.force_authenticate(user=self.common_user)
        response = self.client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 403)

    # ── T-11: POST → 405 ─────────────────────────────────────────
    def test_t11_post_returns_405(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(ROLES_LIST_URL, data={"nomeperfil": "X"}, format="json")
        self.assertEqual(response.status_code, 405)

    # ── T-01: filtro por aplicacao_id válido ──────────────────────
    def test_t01_filter_by_valid_aplicacao_id(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_a.idaplicacao})
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data]
        self.assertIn(self.role_a1.id, ids)
        self.assertIn(self.role_a2.id, ids)
        self.assertIn(self.role_a3.id, ids)
        self.assertNotIn(self.role_b1.id, ids)
        self.assertNotIn(self.role_b2.id, ids)

    # ── T-02: sem query param → todas as roles ───────────────────
    def test_t02_no_param_returns_all(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data]
        for role in [self.role_a1, self.role_a2, self.role_a3, self.role_b1, self.role_b2]:
            self.assertIn(role.id, ids)

    # ── T-03: aplicacao_id inválido (não inteiro) → [] ───────────
    def test_t03_invalid_aplicacao_id_returns_empty(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    # ── T-04: aplicacao_id inexistente → [] ──────────────────────
    def test_t04_nonexistent_aplicacao_id_returns_empty(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": 99999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    # ── T-05: app sem roles → [] ─────────────────────────────────
    def test_t05_app_without_roles_returns_empty(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_empty.idaplicacao})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    # ── T-06: isolamento entre apps ──────────────────────────────
    def test_t06_isolation_between_apps(self):
        self.client.force_authenticate(user=self.admin_user)

        resp_a = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_a.idaplicacao})
        resp_b = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_b.idaplicacao})

        self.assertEqual(len(resp_a.data), 3)
        self.assertEqual(len(resp_b.data), 2)

        ids_a = {r["id"] for r in resp_a.data}
        ids_b = {r["id"] for r in resp_b.data}
        self.assertTrue(ids_a.isdisjoint(ids_b), "Roles das apps A e B não devem se misturar")


class TestRoleSerializerFields(TestCase):
    """
    Cobre T-07 (group=None) e T-08 (campos presentes).
    """

    EXPECTED_FIELDS = {
        "id", "nomeperfil", "codigoperfil",
        "aplicacao_id", "aplicacao_codigo", "aplicacao_nome",
        "group_id", "group_name",
    }

    @classmethod
    def setUpTestData(cls):
        cls.app = make_aplicacao("APP_SER", "App Serializer Test")
        cls.group = Group.objects.create(name="grp_ser_test")
        cls.role_with_group = make_role(cls.app, "Com Grupo", "COM_GRP", group=cls.group)
        cls.role_no_group = make_role(cls.app, "Sem Grupo", "SEM_GRP", group=None)
        cls.admin_user = make_user("admin_ser_gap03", is_admin=True)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)

    # ── T-08: todos os campos presentes ──────────────────────────
    def test_t08_all_fields_present(self):
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        first = response.data[0]
        self.assertEqual(set(first.keys()), self.EXPECTED_FIELDS)

    # ── T-07: role com group=None → null sem erro ─────────────────
    def test_t07_role_with_null_group_no_error(self):
        response = self.client.get(
            ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao}
        )
        self.assertEqual(response.status_code, 200)

        no_group_items = [r for r in response.data if r["codigoperfil"] == "SEM_GRP"]
        self.assertEqual(len(no_group_items), 1)
        item = no_group_items[0]
        self.assertIsNone(item["group_id"])
        self.assertIsNone(item["group_name"])

    # ── Verificação extra: role com group expõe dados corretos ────
    def test_role_with_group_exposes_group_data(self):
        response = self.client.get(
            ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao}
        )
        with_group = [r for r in response.data if r["codigoperfil"] == "COM_GRP"]
        self.assertEqual(len(with_group), 1)
        item = with_group[0]
        self.assertEqual(item["group_id"], self.group.id)
        self.assertEqual(item["group_name"], self.group.name)
