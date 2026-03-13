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

Dependências de fixture: apps/accounts/fixtures/initial_data.json
  Registros utilizados:
    classificacaousuario pk=1 ("Usuário")
    statususuario        pk=1 ("Ativo")
    tipousuario          pk=1 ("Interno")
    auth.group           pk=1 ("PORTAL_ADMIN")  pk=2 ("GESTOR_PNGI")
    accounts.role        pk=1 (PORTAL_ADMIN / app=1)  pk=2 (GESTOR_PNGI / app=2)
    accounts.aplicacao   pk=1 (PORTAL)  pk=2 (ACOES_PNGI)  pk=3 (CARGA_ORG_LOT)

Correções aplicadas v4:
  1. common_user recebe UserRole com Role pk=2 (GESTOR_PNGI / ACOES_PNGI) para que
     GPPTokenObtainPairView emita token. Não tem PORTAL_ADMIN → /roles/ retorna 403.
  2. Token JWT obtido uma única vez por classe em setUpClass. Evita throttling (429).
  3. _get_results() trata response.data paginado {count, results} ou lista direta.
  4. make_role_without_group() desconecta o signal auto_create_group_for_role antes
     de salvar a role e reconecta logo em seguida, garantindo group=None persistido.
"""
from django.contrib.auth.models import Group, User
from django.db.models.signals import post_save
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserProfile, UserRole
from apps.accounts.signals import auto_create_group_for_role

ROLES_LIST_URL = "/api/accounts/roles/"
TOKEN_URL      = "/api/auth/token/"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_results(response):
    """
    Extrai a lista de itens da resposta, independentemente de paginação.
    - Com paginação DRF padrão: response.data == {"count": N, "results": [...]}
    - Sem paginação:            response.data == [...]
    """
    data = response.data
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def _fetch_token(username, password="Senha@123"):
    """
    Obtém access token JWT via /api/auth/token/ usando um client temporário.
    Retorna apenas a string do token.
    """
    tmp = APIClient()
    resp = tmp.post(TOKEN_URL, {"username": username, "password": password}, format="json")
    assert resp.status_code == 200, (
        f"Falha ao obter token JWT para '{username}': "
        f"{resp.status_code} — {getattr(resp, 'data', resp.content)}"
    )
    return resp.data["access"]


def _make_authenticated_client(token):
    """Cria APIClient já configurado com o token JWT fornecido."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def make_user(username, role_pk=None):
    """
    Cria auth.User + UserProfile.
    role_pk: pk da Role da fixture a atribuir via UserRole.
      - pk=1 → PORTAL_ADMIN (app PORTAL)    → satisfaz IsPortalAdmin
      - pk=2 → GESTOR_PNGI (app ACOES_PNGI) → passa no token mas não em IsPortalAdmin
      - None → nenhuma role
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
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario_id=1,
        idusuariocriacao=user,
    )
    if role_pk is not None:
        role = Role.objects.get(pk=role_pk)
        UserRole.objects.create(user=user, role=role, aplicacao=role.aplicacao)
    return user


def make_aplicacao(codigo, nome):
    return Aplicacao.objects.create(
        codigointerno=codigo,
        nomeaplicacao=nome,
        base_url=f"http://{codigo.lower()}.test",
        isshowinportal=False,
    )


def make_role(aplicacao, nome, codigo, group=None):
    """
    Cria uma Role com group já definido (signal não interfere pois
    auto_create_group_for_role só age quando created=True E group is None).
    """
    return Role.objects.create(
        aplicacao=aplicacao,
        nomeperfil=nome,
        codigoperfil=codigo,
        group=group,
    )


def make_role_without_group(aplicacao, nome, codigo):
    """
    Cria uma Role com group=None desconectando temporariamente o signal
    auto_create_group_for_role, que normalmente auto-preencheria o campo.
    O signal é reconectado imediatamente após o save.
    Usado para testar o cenário T-07 (R-06): dados legados onde group é None.
    """
    post_save.disconnect(auto_create_group_for_role, sender=Role)
    try:
        role = Role.objects.create(
            aplicacao=aplicacao,
            nomeperfil=nome,
            codigoperfil=codigo,
            group=None,
        )
    finally:
        post_save.connect(auto_create_group_for_role, sender=Role)
    return role


# ─── TestRoleViewSetFilter (T-01..T-06, T-09..T-11) ──────────────────────────

class TestRoleViewSetFilter(TestCase):
    """
    Testa filtragem, isolamento, autorização e métodos HTTP do RoleViewSet.
    """
    fixtures = ["initial_data"]

    @classmethod
    def setUpTestData(cls):
        cls.app_a     = make_aplicacao("TST_APP_A",     "App Teste A")
        cls.app_b     = make_aplicacao("TST_APP_B",     "App Teste B")
        cls.app_empty = make_aplicacao("TST_APP_EMPTY", "App Sem Roles")

        cls.role_a1 = make_role(cls.app_a, "Visualizador", "TST_VIS_A")
        cls.role_a2 = make_role(cls.app_a, "Editor",       "TST_EDIT_A")
        cls.role_a3 = make_role(cls.app_a, "Admin",        "TST_ADMIN_A")
        cls.role_b1 = make_role(cls.app_b, "Leitor",       "TST_READ_B")
        cls.role_b2 = make_role(cls.app_b, "Gravador",     "TST_WRITE_B")

        cls.admin_user  = make_user("tst_admin_gap03",  role_pk=1)
        cls.common_user = make_user("tst_common_gap03", role_pk=2)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()  # dispara setUpTestData
        cls._admin_token  = _fetch_token("tst_admin_gap03")
        cls._common_token = _fetch_token("tst_common_gap03")

    def setUp(self):
        self.admin_client  = _make_authenticated_client(self._admin_token)
        self.common_client = _make_authenticated_client(self._common_token)
        self.anon_client   = APIClient()

    # ── T-09: sem autenticação → 401 ─────────────────────────────────
    def test_t09_unauthenticated_returns_401(self):
        response = self.anon_client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 401)

    # ── T-10: autenticado sem PORTAL_ADMIN → 403 ─────────────────────
    def test_t10_no_portal_admin_returns_403(self):
        response = self.common_client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 403)

    # ── T-11: POST → 405 ─────────────────────────────────────────────
    def test_t11_post_returns_405(self):
        response = self.admin_client.post(ROLES_LIST_URL, data={"nomeperfil": "X"}, format="json")
        self.assertEqual(response.status_code, 405)

    # ── T-01: filtro por aplicacao_id válido ─────────────────────────
    def test_t01_filter_by_valid_aplicacao_id(self):
        response = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_a.idaplicacao})
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in _get_results(response)]
        self.assertIn(self.role_a1.id, ids)
        self.assertIn(self.role_a2.id, ids)
        self.assertIn(self.role_a3.id, ids)
        self.assertNotIn(self.role_b1.id, ids)
        self.assertNotIn(self.role_b2.id, ids)

    # ── T-02: sem query param → todas as roles ───────────────────────
    def test_t02_no_param_returns_all(self):
        response = self.admin_client.get(ROLES_LIST_URL)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in _get_results(response)]
        for role in [self.role_a1, self.role_a2, self.role_a3, self.role_b1, self.role_b2]:
            self.assertIn(role.id, ids)

    # ── T-03: aplicacao_id inválido (não inteiro) → [] ───────────────
    def test_t03_invalid_aplicacao_id_returns_empty(self):
        response = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(_get_results(response)), [])

    # ── T-04: aplicacao_id inexistente → [] ──────────────────────────
    def test_t04_nonexistent_aplicacao_id_returns_empty(self):
        response = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": 99999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(_get_results(response)), [])

    # ── T-05: app sem roles → [] ─────────────────────────────────────
    def test_t05_app_without_roles_returns_empty(self):
        response = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_empty.idaplicacao})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(_get_results(response)), [])

    # ── T-06: isolamento entre apps ──────────────────────────────────
    def test_t06_isolation_between_apps(self):
        resp_a = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_a.idaplicacao})
        resp_b = self.admin_client.get(ROLES_LIST_URL, {"aplicacao_id": self.app_b.idaplicacao})
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_b.status_code, 200)
        results_a = _get_results(resp_a)
        results_b = _get_results(resp_b)
        self.assertEqual(len(results_a), 3)
        self.assertEqual(len(results_b), 2)
        ids_a = {r["id"] for r in results_a}
        ids_b = {r["id"] for r in results_b}
        self.assertTrue(ids_a.isdisjoint(ids_b), "Roles das apps A e B não devem se misturar")


# ─── TestRoleSerializerFields (T-07, T-08, Extra) ────────────────────────────

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
        cls.app   = make_aplicacao("TST_APP_SER", "App Serializer Test")
        cls.group = Group.objects.create(name="tst_grp_ser")
        # role com group real (signal não interfere pois group != None)
        cls.role_with_group = make_role(cls.app, "Com Grupo", "TST_COM_GRP", group=cls.group)
        # role com group=None: signal desconectado durante o save
        cls.role_no_group = make_role_without_group(cls.app, "Sem Grupo", "TST_SEM_GRP")
        cls.admin_user = make_user("tst_admin_ser_gap03", role_pk=1)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()  # dispara setUpTestData
        cls._admin_token = _fetch_token("tst_admin_ser_gap03")

    def setUp(self):
        self.client = _make_authenticated_client(self._admin_token)

    # ── T-08: todos os campos presentes ──────────────────────────────
    def test_t08_all_fields_present(self):
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao})
        self.assertEqual(response.status_code, 200)
        results = _get_results(response)
        self.assertGreater(len(results), 0, "Esperava ao menos uma role na resposta")
        self.assertEqual(set(results[0].keys()), self.EXPECTED_FIELDS)

    # ── T-07: role com group=None → null sem erro ─────────────────────
    def test_t07_role_with_null_group_no_error(self):
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao})
        self.assertEqual(response.status_code, 200)
        results = _get_results(response)
        no_group_items = [r for r in results if r["codigoperfil"] == "TST_SEM_GRP"]
        self.assertEqual(len(no_group_items), 1)
        item = no_group_items[0]
        self.assertIsNone(item["group_id"])
        self.assertIsNone(item["group_name"])

    # ── Extra: role com group real expõe dados corretos ───────────────
    def test_role_with_group_exposes_group_data(self):
        response = self.client.get(ROLES_LIST_URL, {"aplicacao_id": self.app.idaplicacao})
        self.assertEqual(response.status_code, 200)
        results = _get_results(response)
        with_group = [r for r in results if r["codigoperfil"] == "TST_COM_GRP"]
        self.assertEqual(len(with_group), 1)
        item = with_group[0]
        self.assertEqual(item["group_id"],         self.group.id)
        self.assertEqual(item["group_name"],       self.group.name)
        self.assertEqual(item["aplicacao_id"],     self.app.idaplicacao)
        self.assertEqual(item["aplicacao_codigo"], self.app.codigointerno)
        self.assertEqual(item["aplicacao_nome"],   self.app.nomeaplicacao)
