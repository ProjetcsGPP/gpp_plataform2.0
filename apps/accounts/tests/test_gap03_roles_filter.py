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

Dependências de fixture:
  apps/accounts/fixtures/initial_data.json
  Registros utilizados:
    classificacaousuario pk=1 ("Usuário")
    statususuario        pk=1 ("Ativo")
    tipousuario          pk=1 ("Interno")
    auth.group           pk=1 ("PORTAL_ADMIN")
    accounts.role        pk=1 ("Administrador do Portal", app=1, group=1)
    accounts.aplicacao   pk=1 ("PORTAL"), pk=2 ("ACOES_PNGI"), pk=3 ("CARGA_ORG_LOT")
"""
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserProfile, UserRole

ROLES_LIST_URL = "/api/accounts/roles/"
TOKEN_URL = "/api/auth/token/"


# ─── Helpers ────────────────────────────────────────────────────────────────────

def get_jwt_token(username, password="Senha@123"):
    """
    Cria um APIClient autenticado com JWT real obtido via /api/auth/token/.
    Necessário porque o middleware gpp.security valida o token JWT no nível
    Django (antes do DRF), tornando force_authenticate insuficiente.
    """
    client = APIClient()
    resp = client.post(
        TOKEN_URL,
        data={"username": username, "password": password},
        format="json",
    )
    assert resp.status_code == 200, (
        f"Falha ao obter token JWT para '{username}': "
        f"{resp.status_code} — {getattr(resp, 'data', resp.content)}"
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def make_user(username, is_admin=False):
    """
    Cria auth.User + UserProfile usando os registros de lookup carregados
    pela fixture (status_usuario_id=1, tipo_usuario_id=1,
    classificacao_usuario_id=1).

    Se is_admin=True, cria UserRole apontando para Role pk=1
    (PORTAL_ADMIN / Aplicacao pk=1 PORTAL) — ambos presentes na fixture.
    Isso satisfaz a verificação de IsPortalAdmin:
        UserRole.filter(user=user, role__codigoperfil="PORTAL_ADMIN")
    """
    user = User.objects.create_user(
        username=username,
        password="Senha@123",
        email=f"{username}@test.com",
    )
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao="TEST",
        status_usuario_id=1,       # fixture: Ativo
        tipo_usuario_id=1,         # fixture: Interno
        classificacao_usuario_id=1,  # fixture: Usuário
        idusuariocriacao=user,
    )
    if is_admin:
        portal_admin_role = Role.objects.get(pk=1)   # fixture: PORTAL_ADMIN
        portal_app = Aplicacao.objects.get(pk=1)     # fixture: PORTAL
        UserRole.objects.create(
            user=user,
            role=portal_admin_role,
            aplicacao=portal_app,
        )
    return user


def make_aplicacao(codigo, nome):
    """Cria Aplicacao de teste (pk auto, nunca conflita com fixture)."""
    return Aplicacao.objects.create(
        codigointerno=codigo,
        nomeaplicacao=nome,
        base_url=f"http://{codigo.lower()}.test",
        isshowinportal=False,
    )


def make_role(aplicacao, nome, codigo, group=None):
    """Cria Role de teste (pk auto)."""
    return Role.objects.create(
        aplicacao=aplicacao,
        nomeperfil=nome,
        codigoperfil=codigo,
        group=group,
    )


# ─── TestRoleViewSetFilter (T-01..T-06, T-09..T-11) ───────────────────────────

class TestRoleViewSetFilter(TestCase):
    """
    Testa filtragem, isolamento, autorização e métodos HTTP do RoleViewSet.
    """
    fixtures = ["initial_data"]

    @classmethod
    def setUpTestData(cls):
        # Aplicações exclusivas destes testes (pk auto)
        cls.app_a = make_aplicacao("TST_APP_A", "App Teste A")
        cls.app_b = make_aplicacao("TST_APP_B", "App Teste B")
        cls.app_empty = make_aplicacao("TST_APP_EMPTY", "App Sem Roles")

        # 3 roles para app_a, 2 para app_b
        cls.role_a1 = make_role(cls.app_a, "Visualizador", "TST_VIS_A")
        cls.role_a2 = make_role(cls.app_a, "Editor",       "TST_EDIT_A")
        cls.role_a3 = make_role(cls.app_a, "Admin",        "TST_ADMIN_A")
        cls.role_b1 = make_role(cls.app_b, "Leitor",       "TST_READ_B")
        cls.role_b2 = make_role(cls.app_b, "Gravador",     "TST_WRITE_B")

        # Usuários (criados uma vez, reutilizados por todos os testes da classe)
        cls.admin_user  = make_user("tst_admin_gap03",  is_admin=True)
        cls.common_user = make_user("tst_common_gap03", is_admin=False)

    def setUp(self):
        """
        APIClient recriado e autenticado via JWT real a cada teste.
        O middleware gpp.security exige header Authorization: Bearer <token>
        — force_authenticate não é suficiente pois o middleware atua antes do DRF.

        self.admin_client  → JWT de PORTAL_ADMIN
        self.common_client → JWT de usuário sem PORTAL_ADMIN
        self.anon_client   → sem credenciais
        """
        self.admin_client  = get_jwt_token("tst_admin_gap03")
        self.common_client = get_jwt_token("tst_common_gap03")
        self.anon_client   = APIClient()

    # ── T-09: sem autenticação → 401 ──────────────────────────────
    def test_t09_unauthenticated_returns_401(self):
        response = self.anon_client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 401)

    # ── T-10: autenticado sem PORTAL_ADMIN → 403 ───────────────────
    def test_t10_no_portal_admin_returns_403(self):
        response = self.common_client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 403)

    # ── T-11: POST → 405 ─────────────────────────────────────────
    def test_t11_post_returns_405(self):
        response = self.admin_client.post(ROLES_LIST_URL, data={"nomeperfil": "X"}, format="json")
        self.assertEqual(response.status_code, 405)

    # ── T-01: filtro por aplicacao_id válido ───────────────────────
    def test_t01_filter_by_valid_aplicacao_id(self):
        response = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_a.idaplicacao})
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data]
        self.assertIn(self.role_a1.id, ids)
        self.assertIn(self.role_a2.id, ids)
        self.assertIn(self.role_a3.id, ids)
        self.assertNotIn(self.role_b1.id, ids)
        self.assertNotIn(self.role_b2.id, ids)

    # ── T-02: sem query param → todas as roles ────────────────────
    def test_t02_no_param_returns_all(self):
        response = self.admin_client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data]
        for role in [self.role_a1, self.role_a2, self.role_a3, self.role_b1, self.role_b2]:
            self.assertIn(role.id, ids)

    # ── T-03: aplicacao_id inválido (não inteiro) → [] ────────────
    def test_t03_invalid_aplicacao_id_returns_empty(self):
        response = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.data), [])

    # ── T-04: aplicacao_id inexistente → [] ───────────────────────
    def test_t04_nonexistent_aplicacao_id_returns_empty(self):
        response = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": 99999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.data), [])

    # ── T-05: app sem roles → [] ─────────────────────────────────
    def test_t05_app_without_roles_returns_empty(self):
        response = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_empty.idaplicacao})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.data), [])

    # ── T-06: isolamento entre apps ───────────────────────────────
    def test_t06_isolation_between_apps(self):
        resp_a = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_a.idaplicacao})
        resp_b = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_b.idaplicacao})

        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_b.status_code, 200)
        self.assertEqual(len(resp_a.data), 3)
        self.assertEqual(len(resp_b.data), 2)

        ids_a = {r["id"] for r in resp_a.data}
        ids_b = {r["id"] for r in resp_b.data}
        self.assertTrue(ids_a.isdisjoint(ids_b), "Roles das apps A e B não devem se misturar")


# ─── TestRoleSerializerFields (T-07, T-08) ─────────────────────────────────────

class TestRoleSerializerFields(TestCase):
    """
    Valida estrutura do RoleSerializer:
      T-07: role com group=None serializa group_id/group_name como null sem erro
      T-08: resposta contém exatamente os 8 campos esperados
      Extra: role com group real expõe group_id e group_name corretos
    """
    fixtures = ["initial_data"]

    EXPECTED_FIELDS = {
        "id", "nomeperfil", "codigoperfil",
        "aplicacao_id", "aplicacao_codigo", "aplicacao_nome",
        "group_id", "group_name",
    }

    @classmethod
    def setUpTestData(cls):
        cls.app = make_aplicacao("TST_APP_SER", "App Serializer Test")
        # group real para o teste de campos
        cls.group = Group.objects.create(name="tst_grp_ser")
        cls.role_with_group = make_role(cls.app, "Com Grupo", "TST_COM_GRP", group=cls.group)
        # group=None para T-07
        cls.role_no_group = make_role(cls.app, "Sem Grupo", "TST_SEM_GRP", group=None)
        cls.admin_user = make_user("tst_admin_ser_gap03", is_admin=True)

    def setUp(self):
        """
        Recria e autentica o APIClient via JWT real a cada teste.
        """
        self.client = get_jwt_token("tst_admin_ser_gap03")

    # ── T-08: todos os campos presentes na resposta ───────────────────
    def test_t08_all_fields_present(self):
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0, "Esperava ao menos uma role na resposta")
        first = response.data[0]
        self.assertEqual(set(first.keys()), self.EXPECTED_FIELDS)

    # ── T-07: role com group=None → null sem erro de serialização ───
    def test_t07_role_with_null_group_no_error(self):
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao})
        self.assertEqual(response.status_code, 200)

        no_group_items = [r for r in response.data if r["codigoperfil"] == "TST_SEM_GRP"]
        self.assertEqual(len(no_group_items), 1)
        item = no_group_items[0]
        self.assertIsNone(item["group_id"])
        self.assertIsNone(item["group_name"])

    # ── Extra: role com group real expõe dados corretos ─────────────
    def test_role_with_group_exposes_group_data(self):
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao})
        self.assertEqual(response.status_code, 200)

        with_group = [r for r in response.data if r["codigoperfil"] == "TST_COM_GRP"]
        self.assertEqual(len(with_group), 1)
        item = with_group[0]
        self.assertEqual(item["group_id"], cls.group.id)
        self.assertEqual(item["group_name"], cls.group.name)
        self.assertEqual(item["aplicacao_id"], cls.app.idaplicacao)
        self.assertEqual(item["aplicacao_codigo"], cls.app.codigointerno)
        self.assertEqual(item["aplicacao_nome"], cls.app.nomeaplicacao)
