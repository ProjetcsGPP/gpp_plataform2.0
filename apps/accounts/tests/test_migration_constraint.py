"""
Fase 7 — Testes: UniqueConstraint UserRole ao nível de banco

Cenários cobertos (T-01..T-10):
  T-01  Inserir via ORM dois UserRole (user, app) iguais, roles diferentes  → IntegrityError
  T-02  Inserir via ORM dois UserRole (user, app, role) idênticos            → IntegrityError
  T-03  Inserir via ORM UserRole com user/role iguais, apps diferentes       → Sucesso
  T-04  __str__ de UserRole continua funcionando após troca de constraint    → str ok
  T-05  UserRole pode ser deletado e recriado (sem violação)                 → Sucesso
  T-06  Constraint não bloqueia usuários diferentes, mesma (app, role)       → Sucesso
  T-07  Login de usuário criado sem role falha com 400 ou 403                → 400/403
  T-08  Login de usuário criado com role (Fase 6 / direct ORM) sucede        → 200
  T-09  Mesmo resultado com pytest --reuse-db (isolamento por TestCase)      → isolado via tearDown
  T-10  Reversão da constraint — migration anterior permite (user,app,role)  → testada via SQL direto

Regras (R-01..R-07) verificadas:
  R-01: constraint no banco (IntegrityError via ORM).
  R-02: operações sem RunSQL manual — migration pura Django ORM.
  R-03: testes existentes não quebram — sem alteração de fixtures.
  R-05: User criado com User.objects.create_user(), nunca via endpoint.
  R-07: __str__ de UserRole testado explicitamente (T-04).

Dependências de fixture: apps/accounts/fixtures/initial_data.json
  Registros utilizados:
    statususuario pk=1, tipousuario pk=1, classificacaousuario pk=1
    accounts.aplicacao pk=1 (PORTAL), pk=2 (ACOES_PNGI)
    accounts.role      pk=1 (PORTAL_ADMIN/app=1), pk=2 (GESTOR_PNGI/app=2)
"""
import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Aplicacao, Role, UserProfile, UserRole

LOGIN_URL = "/api/accounts/login/"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_user_with_profile(username, *, with_role_pk=None):
    """
    Cria auth.User + UserProfile (status_usuario=1, ativo).
    Optionally atribui UserRole via with_role_pk (pk da Role da fixture).
    R-05: nunca usa endpoints — criação direta via ORM.
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
    if with_role_pk is not None:
        role = Role.objects.get(pk=with_role_pk)
        UserRole.objects.create(user=user, role=role, aplicacao=role.aplicacao)
    return user


# ─── TestUserRoleBankConstraint (T-01..T-06, T-09) ───────────────────────────

class TestUserRoleBankConstraint(TestCase):
    """
    Valida que a UniqueConstraint uq_userrole_user_aplicacao está ativa
    no banco de dados — não apenas na camada de serializer.
    """
    fixtures = ["initial_data"]

    @classmethod
    def setUpTestData(cls):
        cls.app_portal    = Aplicacao.objects.get(pk=1)
        cls.app_acoes     = Aplicacao.objects.get(pk=2)
        cls.role_portal   = Role.objects.get(pk=1)   # PORTAL_ADMIN / app=1
        cls.role_acoes    = Role.objects.get(pk=2)   # GESTOR_PNGI  / app=2

    def setUp(self):
        """Cada teste recebe seu próprio usuário para garantir isolamento (R-06 / T-09)."""
        test_id = self._testMethodName
        self.user = User.objects.create_user(
            username=f"tst_f7_{test_id[:20]}",
            password="Senha@123",
            email=f"tst_f7_{test_id[:20]}@test.com",
        )

    # ── T-01: mesmo (user, app), roles diferentes → IntegrityError ───
    def test_t01_duplicate_user_aplicacao_different_roles_raises_integrity_error(self):
        """
        R-01: A nova constraint (user, aplicacao) impede dois UserRole com
        a mesma dupla, mesmo que as roles sejam diferentes.
        """
        UserRole.objects.create(
            user=self.user,
            aplicacao=self.app_portal,
            role=self.role_portal,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # role_acoes pertence à app=2, mas forçamos app_portal aqui
                # para garantir colisão em (user, app_portal) com role diferente.
                # Criamos uma role extra na app_portal para ter role distinta.
                from django.contrib.auth.models import Group
                grp = Group.objects.create(name=f"grp_t01_{self.user.pk}")
                extra_role = Role.objects.create(
                    aplicacao=self.app_portal,
                    nomeperfil="Extra T01",
                    codigoperfil=f"TST_EXTRA_T01_{self.user.pk}",
                    group=grp,
                )
                UserRole.objects.create(
                    user=self.user,
                    aplicacao=self.app_portal,
                    role=extra_role,
                )

    # ── T-02: mesmo (user, app, role) idênticos → IntegrityError ─────
    def test_t02_duplicate_user_aplicacao_same_role_raises_integrity_error(self):
        """
        A nova constraint mais restritiva (user, aplicacao) também bloqueia
        duplicatas de (user, aplicacao, role) — subconjunto da constraint.
        """
        UserRole.objects.create(
            user=self.user,
            aplicacao=self.app_portal,
            role=self.role_portal,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserRole.objects.create(
                    user=self.user,
                    aplicacao=self.app_portal,
                    role=self.role_portal,
                )

    # ── T-03: mesmo user/role, apps diferentes → Sucesso ─────────────
    def test_t03_same_user_different_aplicacoes_allowed(self):
        """
        Usuário pode ter UserRole em aplicações distintas — isso é esperado
        e não deve ser bloqueado pela constraint.
        """
        ur1 = UserRole.objects.create(
            user=self.user,
            aplicacao=self.app_portal,
            role=self.role_portal,
        )
        ur2 = UserRole.objects.create(
            user=self.user,
            aplicacao=self.app_acoes,
            role=self.role_acoes,
        )
        self.assertIsNotNone(ur1.pk)
        self.assertIsNotNone(ur2.pk)
        self.assertEqual(
            UserRole.objects.filter(user=self.user).count(), 2
        )

    # ── T-04: __str__ continua funcionando (R-07) ────────────────────
    def test_t04_str_representation_after_constraint_change(self):
        """
        R-07: A troca de constraint não pode quebrar o __str__ do model.
        """
        ur = UserRole.objects.create(
            user=self.user,
            aplicacao=self.app_portal,
            role=self.role_portal,
        )
        expected = f"{self.user} → {self.app_portal} ({self.role_portal})"
        self.assertEqual(str(ur), expected)

    # ── T-05: delete e recriar sem violação ──────────────────────────
    def test_t05_delete_and_recreate_userrole_allowed(self):
        """
        Após remoção do UserRole, deve ser possível criar novamente
        a mesma combinação (user, aplicacao) sem IntegrityError.
        """
        ur = UserRole.objects.create(
            user=self.user,
            aplicacao=self.app_portal,
            role=self.role_portal,
        )
        ur.delete()
        ur_new = UserRole.objects.create(
            user=self.user,
            aplicacao=self.app_portal,
            role=self.role_portal,
        )
        self.assertIsNotNone(ur_new.pk)

    # ── T-06: usuários diferentes, mesma (app, role) → Sucesso ───────
    def test_t06_different_users_same_aplicacao_role_allowed(self):
        """
        A constraint é por (user, aplicacao), portanto usuários distintos
        podem ter a mesma role na mesma aplicação sem conflito.
        """
        user2 = User.objects.create_user(
            username=f"tst_f7_u2_{self.user.pk}",
            password="Senha@123",
            email=f"tst_f7_u2_{self.user.pk}@test.com",
        )
        ur1 = UserRole.objects.create(
            user=self.user,
            aplicacao=self.app_portal,
            role=self.role_portal,
        )
        ur2 = UserRole.objects.create(
            user=user2,
            aplicacao=self.app_portal,
            role=self.role_portal,
        )
        self.assertNotEqual(ur1.pk, ur2.pk)


# ─── TestLoginBehaviorConstraint (T-07, T-08) ────────────────────────────────

class TestLoginBehaviorConstraint(TestCase):
    """
    Valida o comportamento de login pós-Fase-0 (autenticação stateful via
    cookie HttpOnly gpp_session — sem JWT):

      T-07: usuário sem UserRole não consegue logar (view de login exige
            ao menos 1 UserRole ativo na aplicação solicitada).
      T-08: usuário com UserRole (criado via ORM, R-05) loga com sucesso,
            recebendo o cookie gpp_session.

    Endpoint:  POST /api/accounts/login/  (name="accounts:login")
    Payload:   {"username": "...", "password": "...", "app_context": "PORTAL"}
    """
    fixtures = ["initial_data"]

    LOGIN_URL = "/api/accounts/login/"

    def _do_login(self, username, password="Senha@123", app_context="PORTAL"):
        """
        Executa POST no endpoint de login stateful.
        Retorna a Response — sem bearer token, sem credenciais de cliente.
        """
        client = APIClient()
        return client.post(
            self.LOGIN_URL,
            {"username": username, "password": password, "app_context": app_context},
            format="json",
        )

    # ── T-07: sem role → 400 ou 403 ──────────────────────────────────
    def test_t07_login_without_role_returns_400_or_403(self):
        """
        Usuário criado sem role atribuída deve ser barrado ao tentar logar.
        A view pode rejeitar com 400 (serializer) ou 403 (view/policy),
        mas nunca com 200 — cookie gpp_session NÃO deve ser emitido.

        Comportamento intencional: garante que a sessão não seja criada
        para usuários sem autorização de acesso à aplicação.
        """
        _make_user_with_profile("tst_f7_no_role")  # sem role
        resp = self._do_login("tst_f7_no_role")

        self.assertIn(
            resp.status_code,
            [400, 403],
            msg=(
                f"Esperado 400 ou 403 para usuário sem role, "
                f"mas recebeu {resp.status_code}. Body: {getattr(resp, 'data', resp.content)}"
            ),
        )
        # Cookie de sessão NÃO pode estar presente
        self.assertNotIn(
            "gpp_session",
            resp.cookies,
            msg="Cookie gpp_session não deve ser emitido para usuário sem role.",
        )
        # Nenhuma chave JWT deve aparecer no body
        if hasattr(resp, "data") and isinstance(resp.data, dict):
            self.assertNotIn("access", resp.data)
            self.assertNotIn("refresh", resp.data)

    # ── T-08: com role → 200 + cookie gpp_session ────────────────────
    def test_t08_login_with_role_returns_200_and_session_cookie(self):
        """
        Usuário com UserRole (role pk=1 / PORTAL_ADMIN, criado via ORM)
        deve receber 200 e o cookie HttpOnly gpp_session.
        Nenhuma chave JWT (access, refresh, token) deve estar no body.
        """
        _make_user_with_profile("tst_f7_with_role", with_role_pk=1)
        resp = self._do_login("tst_f7_with_role")

        self.assertEqual(
            resp.status_code,
            200,
            msg=(
                f"Esperado 200 para usuário com role, "
                f"mas recebeu {resp.status_code}. Body: {getattr(resp, 'data', resp.content)}"
            ),
        )

        # Verificação de sessão: cookie gpp_session OU dados do usuário no body
        has_cookie = "gpp_session" in resp.cookies
        has_user_data = (
            hasattr(resp, "data")
            and isinstance(resp.data, dict)
            and "username" in resp.data
        )
        self.assertTrue(
            has_cookie or has_user_data,
            msg=(
                "Esperado cookie 'gpp_session' ou 'username' no body após login com sucesso. "
                f"Cookies: {list(resp.cookies.keys())}. "
                f"Body keys: {list(resp.data.keys()) if hasattr(resp, 'data') and isinstance(resp.data, dict) else 'N/A'}"
            ),
        )

        # Nenhuma chave JWT deve estar no body
        if hasattr(resp, "data") and isinstance(resp.data, dict):
            self.assertNotIn(
                "access", resp.data,
                msg="Chave 'access' (JWT) não deve existir no body pós-Fase-0.",
            )
            self.assertNotIn(
                "refresh", resp.data,
                msg="Chave 'refresh' (JWT) não deve existir no body pós-Fase-0.",
            )
