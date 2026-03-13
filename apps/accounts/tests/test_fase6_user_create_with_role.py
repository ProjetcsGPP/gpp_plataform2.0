"""
FASE 6 — Testes: UserCreateWithRoleSerializer + UserCreateWithRoleView

Endpoint: POST /api/accounts/users/create-with-role/

Cenários cobertos (T-01..T-11):
  T-01  POST válido com todos os campos            → 201, User+Profile+UserRole criados, perms sincronizadas
  T-02  aplicacao_id com isshowinportal=True        → 400 aplicação inválida
  T-03  role_id de app diferente de aplicacao_id   → 400 "A role não pertence à aplicação informada."
  T-04  username já existente                       → 400 unicidade
  T-05  senha fraca                                 → 400 validação de senha
  T-06  falha simulada no sync (mock)               → rollback total — nenhum objeto criado
  T-07  falha simulada no UserRole.create (mock)    → rollback total — User e Profile não persistidos
  T-08  auth_user_user_permissions após T-01        → permissões do grupo da role presentes
  T-09  POST sem autenticação                       → 401
  T-10  POST autenticado sem PORTAL_ADMIN           → 403
  T-11  T-01 + POST /user-roles/ com outra role+app → 201 segundo UserRole criado (N roles em N apps)

Dependências de fixture: apps/accounts/fixtures/initial_data.json
  Registros utilizados:
    statususuario        pk=1 ("Ativo")
    tipousuario          pk=1 ("Interno")
    classificacaousuario pk=1 ("Usuário")
    auth.group           pk=1 ("PORTAL_ADMIN")  pk=2 ("GESTOR_PNGI")
    accounts.role        pk=1 (PORTAL_ADMIN / app=1)  pk=2 (GESTOR_PNGI / app=2)
    accounts.aplicacao   pk=1 (PORTAL isshowinportal=True)  pk=2 (ACOES_PNGI isshowinportal=False)
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserProfile, UserRole

CREATE_WITH_ROLE_URL = "/api/accounts/users/create-with-role/"
USER_ROLES_URL       = "/api/accounts/user-roles/"
TOKEN_URL            = "/api/auth/token/"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fetch_token(username, password="Senha@123"):
    tmp = APIClient()
    resp = tmp.post(TOKEN_URL, {"username": username, "password": password}, format="json")
    assert resp.status_code == 200, (
        f"Falha ao obter token para '{username}': "
        f"{resp.status_code} — {getattr(resp, 'data', resp.content)}"
    )
    return resp.data["access"]


def _make_client(token=None):
    client = APIClient()
    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _make_user(username, role_pk, password="Senha@123"):
    """Cria User + Profile + UserRole a partir de dados de fixture."""
    user = User.objects.create_user(
        username=username, password=password, email=f"{username}@test.com"
    )
    UserProfile.objects.create(
        user=user, name=username, orgao="TEST",
        status_usuario_id=1, tipo_usuario_id=1, classificacao_usuario_id=1,
        idusuariocriacao=user,
    )
    role = Role.objects.get(pk=role_pk)
    UserRole.objects.create(user=user, role=role, aplicacao=role.aplicacao)
    return user


def _valid_payload(aplicacao_id, role_id, suffix=""):
    """Gera um payload válido único para cada chamada."""
    return {
        "username":   f"joao.silva{suffix}",
        "email":      f"joao{suffix}@example.com",
        "password":   "SenhaForte@2026",
        "first_name": "João",
        "last_name":  "Silva",
        "name":       "João Silva",
        "orgao":      "SEDU",
        "aplicacao_id": aplicacao_id,
        "role_id":      role_id,
    }


# ─── TestUserCreateWithRoleView ───────────────────────────────────────────────

class TestUserCreateWithRoleView(TestCase):
    """
    Testa o endpoint POST /api/accounts/users/create-with-role/
    para todos os cenários T-01..T-11.
    """
    fixtures = ["fase6_initial_data"]

    @classmethod
    def setUpTestData(cls):
        # Usuário administrador: role pk=1 (PORTAL_ADMIN, app pk=1 PORTAL)
        cls.admin_user  = _make_user("fase6_admin",  role_pk=1)
        # Usuário comum: role pk=2 (GESTOR_PNGI, app pk=2), sem PORTAL_ADMIN
        cls.common_user = _make_user("fase6_common", role_pk=2)

        # app pk=2 (ACOES_PNGI, isshowinportal=False) → válida para associação
        cls.app_valida   = Aplicacao.objects.get(pk=2)
        # role pk=2 pertence à app pk=2
        cls.role_valida  = Role.objects.get(pk=2)

        # app pk=1 (PORTAL, isshowinportal=True) → inválida para associação (T-02)
        cls.app_portal   = Aplicacao.objects.get(pk=1)
        # role pk=1 pertence à app pk=1 (PORTAL) → "wrong app" para T-03
        cls.role_portal  = Role.objects.get(pk=1)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._admin_token  = _fetch_token("fase6_admin")
        cls._common_token = _fetch_token("fase6_common")

    def setUp(self):
        self.admin_client  = _make_client(self._admin_token)
        self.common_client = _make_client(self._common_token)
        self.anon_client   = _make_client()

    # ── T-09: sem autenticação → 401 ─────────────────────────────────
    def test_t09_unauthenticated_returns_401(self):
        resp = self.anon_client.post(
            CREATE_WITH_ROLE_URL,
            _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t09"),
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    # ── T-10: sem PORTAL_ADMIN → 403 ─────────────────────────────────
    def test_t10_no_portal_admin_returns_403(self):
        resp = self.common_client.post(
            CREATE_WITH_ROLE_URL,
            _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t10"),
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    # ── T-01: POST válido → 201 com payload correto ───────────────────
    def test_t01_valid_post_returns_201(self):
        payload = _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t01")
        resp = self.admin_client.post(CREATE_WITH_ROLE_URL, payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)

        # Campos obrigatórios na resposta
        for field in ["user_id", "username", "email", "name", "orgao",
                       "aplicacao", "role", "permissions_added", "datacriacao"]:
            self.assertIn(field, resp.data, f"Campo '{field}' ausente na resposta")

        self.assertEqual(resp.data["username"], payload["username"])
        self.assertEqual(resp.data["aplicacao"], self.app_valida.codigointerno)
        self.assertEqual(resp.data["role"],      self.role_valida.codigoperfil)

        # Objetos persistidos
        self.assertTrue(User.objects.filter(username=payload["username"]).exists())
        user = User.objects.get(username=payload["username"])
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertTrue(UserRole.objects.filter(user=user, aplicacao=self.app_valida).exists())

    # ── T-02: aplicacao_id com isshowinportal=True → 400 ─────────────
    def test_t02_portal_app_returns_400(self):
        payload = _valid_payload(self.app_portal.idaplicacao, self.role_portal.id, "_t02")
        resp = self.admin_client.post(CREATE_WITH_ROLE_URL, payload, format="json")
        self.assertEqual(resp.status_code, 400)

    # ── T-03: role de app diferente → 400 ────────────────────────────
    def test_t03_role_wrong_app_returns_400(self):
        # role_portal (pk=1) pertence à app PORTAL (pk=1, isshowinportal=True)
        # Mas estamos enviando aplicacao_id=app_valida (pk=2)
        # → app_valida passa no queryset (isshowinportal=False)
        # → mas role_portal.aplicacao != app_valida → validate() deve rejeitar
        payload = _valid_payload(
            self.app_valida.idaplicacao,
            self.role_portal.id,  # role pertence à app PORTAL, não à ACOES_PNGI
            "_t03"
        )
        resp = self.admin_client.post(CREATE_WITH_ROLE_URL, payload, format="json")
        self.assertEqual(resp.status_code, 400)
        # Verificar mensagem específica
        error_str = str(resp.data)
        self.assertIn("não pertence", error_str)

    # ── T-04: username duplicado → 400 ───────────────────────────────
    def test_t04_duplicate_username_returns_400(self):
        # Criar usuário com o mesmo username antes
        User.objects.create_user(username="joao.dup", password="x", email="dup@dup.com")
        payload = _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t04")
        payload["username"] = "joao.dup"
        resp = self.admin_client.post(CREATE_WITH_ROLE_URL, payload, format="json")
        self.assertEqual(resp.status_code, 400)
        
        self.assertIn("username", resp.data.get("errors", {}))

    # ── T-05: senha fraca → 400 ───────────────────────────────────────
    def test_t05_weak_password_returns_400(self):
        payload = _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t05")
        payload["password"] = "123"
        resp = self.admin_client.post(CREATE_WITH_ROLE_URL, payload, format="json")
        self.assertEqual(resp.status_code, 400)
        
        self.assertIn("password", resp.data.get("errors", {}))

    # ── T-06: falha no sync → rollback total ──────────────────────────
    def test_t06_sync_failure_triggers_rollback(self):
        payload = _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t06")
        sync_path = "apps.accounts.serializers.sync_user_permissions_from_group"
        with patch(sync_path, side_effect=Exception("sync falhou")):
            resp = self.admin_client.post(CREATE_WITH_ROLE_URL, payload, format="json")
        # A view captura a exceção e converte para 500
        self.assertEqual(resp.status_code, 500)
        # Rollback: nenhum objeto deve ter sido persistido
        self.assertFalse(User.objects.filter(username=payload["username"]).exists())
        self.assertFalse(
            UserRole.objects.filter(aplicacao=self.app_valida).filter(
                user__username=payload["username"]
            ).exists()
        )

    # ── T-07: falha no UserRole.create → rollback total ──────────────
    def test_t07_userrole_failure_triggers_rollback(self):
        payload = _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t07")
        role_path = "apps.accounts.models.UserRole.objects.create"
        with patch(role_path, side_effect=Exception("userrole criação falhou")):
            resp = self.admin_client.post(CREATE_WITH_ROLE_URL, payload, format="json")
        self.assertEqual(resp.status_code, 500)
        # Rollback: User e Profile não devem existir
        self.assertFalse(User.objects.filter(username=payload["username"]).exists())

    # ── T-08: permissões presentes após T-01 ──────────────────────────
    def test_t08_permissions_added_after_creation(self):
        payload = _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t08")
        resp = self.admin_client.post(CREATE_WITH_ROLE_URL, payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)

        user = User.objects.get(username=payload["username"])
        permissions_added = resp.data["permissions_added"]

        # permissions_added deve ser consistente com user_user_permissions
        direct_perms_count = user.user_permissions.count()
        self.assertEqual(
            direct_perms_count, permissions_added,
            f"Esperava {permissions_added} perms em auth_user_user_permissions, "
            f"mas encontrou {direct_perms_count}"
        )

    # ── T-11: T-01 + segunda role em app diferente → 201 ─────────────
    def test_t11_second_role_in_different_app_returns_201(self):
        # Passo 1: criar usuário via create-with-role na app_valida
        payload_1 = _valid_payload(self.app_valida.idaplicacao, self.role_valida.id, "_t11")
        resp1 = self.admin_client.post(CREATE_WITH_ROLE_URL, payload_1, format="json")
        self.assertEqual(resp1.status_code, 201, resp1.data)

        new_user = User.objects.get(username=payload_1["username"])

        # Passo 2: criar app extra (diferente de app_valida) e role extra
        from apps.accounts.models import Aplicacao, Role
        app_extra = Aplicacao.objects.create(
            codigointerno="EXTRA_APP",
            nomeaplicacao="App Extra T11",
            base_url="http://extra.test",
            isshowinportal=False,
        )
        role_extra = Role.objects.create(
            aplicacao=app_extra,
            nomeperfil="Técnico Extra",
            codigoperfil="TECNICO_EXTRA",
        )

        # Passo 3: atribuir segunda role via POST /user-roles/
        resp2 = self.admin_client.post(
            USER_ROLES_URL,
            {
                "user":      new_user.id,
                "aplicacao": app_extra.idaplicacao,
                "role":      role_extra.id,
            },
            format="json",
        )
        self.assertEqual(resp2.status_code, 201, resp2.data)

        # Deve ter 2 UserRoles: uma da app_valida, outra da app_extra
        total_roles = UserRole.objects.filter(user=new_user).count()
        self.assertEqual(total_roles, 2, "Usuário deve ter exatamente 2 roles em 2 apps diferentes")
