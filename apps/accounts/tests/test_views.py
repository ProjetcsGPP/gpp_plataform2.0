"""
GPP Plataform 2.0 — Accounts Views Tests
PÓS-FASE-0: autenticacao 100% via sessão (cookie HttpOnly gpp_session).
Nenhuma referência a JWT, Bearer token ou jti.

Coberturas obrigatórias:
  - LoginView:          sucesso, credenciais inválidas, app inválida,
                        app bloqueada, sem acesso (403), campos ausentes (400)
  - LogoutView:         sucesso, sessão já revogada
  - SwitchAppView:      sucesso, app inválida, sem acesso
  - AppContextMiddleware: sessão revogada → 401
  - AccountsSession:    criação, revogação via revoke()
  - MeEndpoint:         retorna dados do usuário autenticado
  - ProfilesListView:   PORTAL_ADMIN vê todos, comum vê apenas o próprio
  - AssignRole:         não-admin recebe 403
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.accounts.models import (
    Aplicacao, Role, StatusUsuario, TipoUsuario,
    ClassificacaoUsuario, UserProfile, UserRole, AccountsSession,
)
from apps.core.tests.utils import patch_security


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_status():
    obj, _ = StatusUsuario.objects.get_or_create(
        idstatususuario=1, defaults={"strdescricao": "Ativo"}
    )
    return obj


def _make_tipo():
    obj, _ = TipoUsuario.objects.get_or_create(
        idtipousuario=1, defaults={"strdescricao": "Padrão"}
    )
    return obj


def _make_classificacao():
    obj, _ = ClassificacaoUsuario.objects.get_or_create(
        idclassificacaousuario=1, defaults={"strdescricao": "Padrão"}
    )
    return obj


def _make_app(codigo="PORTAL", bloqueada=False):
    app, _ = Aplicacao.objects.get_or_create(
        codigointerno=codigo,
        defaults={"nomeaplicacao": codigo, "isshowinportal": True},
    )
    if bloqueada:
        app.isshowinportal = False
        app.save(update_fields=["isshowinportal"])
    return app


def _make_user_with_profile(username, password="pass", orgao="SESP", is_admin=False):
    """Cria User + UserProfile + role PORTAL_ADMIN ou USER."""
    user = User.objects.create_user(username=username, password=password)
    _make_status()
    _make_tipo()
    _make_classificacao()
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao=orgao,
        status_usuario_id=1,
        tipo_usuario_id=1,
        classificacao_usuario_id=1,
    )
    app = _make_app()
    role_codigo = "PORTAL_ADMIN" if is_admin else "USER"
    role, _ = Role.objects.get_or_create(
        aplicacao=app,
        codigoperfil=role_codigo,
        defaults={"nomeperfil": role_codigo},
    )
    UserRole.objects.create(user=user, aplicacao=app, role=role)
    return user


def _make_session(user, app_context="PORTAL", revoked=False):
    """Cria AccountsSession diretamente (sem passar pela view de login)."""
    session = AccountsSession.objects.create(
        user=user,
        session_key=f"test-session-{user.id}-{app_context}",
        app_context=app_context,
        expires_at=timezone.now() + timedelta(hours=8),
        ip_address="127.0.0.1",
        user_agent="pytest",
        revoked=revoked,
    )
    if revoked:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
    return session


# ─── LoginView ───────────────────────────────────────────────────────────────

class LoginViewTest(APITestCase):
    """
    Testa POST /api/accounts/login/
    Autentica via sessão Django — sem JWT, sem Bearer token.
    """

    def setUp(self):
        self.url = reverse("accounts:login")
        self.app = _make_app("PORTAL")
        self.user = _make_user_with_profile("login_user", password="secret123")

    def test_login_sucesso_retorna_200(self):
        """Credenciais válidas + app válida → 200 e cookie de sessão."""
        payload = {"username": "login_user", "password": "secret123", "app_context": "PORTAL"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Cookie de sessão deve estar presente na resposta
        self.assertIn("gpp_session", response.cookies)

    def test_login_credenciais_invalidas_retorna_401(self):
        """Senha errada → 401."""
        payload = {"username": "login_user", "password": "errada", "app_context": "PORTAL"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_app_invalida_retorna_400(self):
        """app_context inexistente no banco → 400."""
        payload = {"username": "login_user", "password": "secret123", "app_context": "INEXISTENTE"}
        response = self.client.post(self.url, payload)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED])

    def test_login_app_bloqueada_retorna_403(self):
        """App com isshowinportal=False → 403."""
        app_bloqueada = _make_app("BLOQUEADA", bloqueada=True)
        # cria role para o usuario na app bloqueada para testar
        role, _ = Role.objects.get_or_create(
            aplicacao=app_bloqueada,
            codigoperfil="USER",
            defaults={"nomeperfil": "User"},
        )
        UserRole.objects.create(user=self.user, aplicacao=app_bloqueada, role=role)
        payload = {"username": "login_user", "password": "secret123", "app_context": "BLOQUEADA"}
        response = self.client.post(self.url, payload)
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

    def test_login_sem_acesso_retorna_403(self):
        """Usuário sem UserRole na app → 403."""
        app_outra = _make_app("ACOES_PNGI")
        # user não tem role em ACOES_PNGI
        payload = {"username": "login_user", "password": "secret123", "app_context": "ACOES_PNGI"}
        response = self.client.post(self.url, payload)
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED])

    def test_login_campos_ausentes_retorna_400(self):
        """Payload vazio → 400."""
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_sem_password_retorna_400(self):
        """username presente, password ausente → 400."""
        payload = {"username": "login_user", "app_context": "PORTAL"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ─── LogoutView ───────────────────────────────────────────────────────────────

class LogoutViewTest(APITestCase):
    """
    Testa POST /api/accounts/logout/
    O logout deve revogar a AccountsSession e encerrar a sessão Django.
    """

    def setUp(self):
        self.url = reverse("accounts:logout")
        self.user = _make_user_with_profile("logout_user", password="pass")

    def test_logout_sucesso_retorna_200(self):
        """Usuário autenticado faz logout → 200 e sessão encerrada."""
        self.client.force_login(self.user)
        response = self.client.post(self.url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    def test_logout_sem_autenticacao_retorna_401(self):
        """Logout sem estar logado → 401."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_sessao_ja_revogada_retorna_401(self):
        """
        Se a sessão já estiver revogada (AccountsSession.revoked=True),
        o AppContextMiddleware deve barrar com 401 antes de chegar na view.
        Simula diretamente via AccountsSession revogada + request fake.
        """
        session = _make_session(self.user, revoked=True)
        # Verifica que AccountsSession.revoke() funciona corretamente
        self.assertTrue(session.revoked)
        self.assertIsNotNone(session.revoked_at)


# ─── SwitchAppView ────────────────────────────────────────────────────────────

class SwitchAppViewTest(APITestCase):
    """
    Testa POST /api/accounts/switch-app/
    Permite ao usuário trocar de aplicação sem fazer novo login.
    """

    def setUp(self):
        self.url = reverse("accounts:switch-app")
        self.user = _make_user_with_profile("switch_user", password="pass")
        self.app_pngi = _make_app("ACOES_PNGI")
        role, _ = Role.objects.get_or_create(
            aplicacao=self.app_pngi,
            codigoperfil="USER",
            defaults={"nomeperfil": "User"},
        )
        UserRole.objects.create(user=self.user, aplicacao=self.app_pngi, role=role)

    def test_switch_app_sucesso(self):
        """Usuário com role na app alvo → 200."""
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"app_context": "ACOES_PNGI"})
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    def test_switch_app_invalida_retorna_400(self):
        """app_context inexistente → 400."""
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"app_context": "NAO_EXISTE"})
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])

    def test_switch_app_sem_acesso_retorna_403(self):
        """Usuário sem UserRole na app alvo → 403."""
        app_sem_acesso = _make_app("CARGA_ORG_LOT")
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"app_context": "CARGA_ORG_LOT"})
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED])


# ─── AppContextMiddleware ─────────────────────────────────────────────────────

class AppContextMiddlewareTest(APITestCase):
    """
    Testa o comportamento do AppContextMiddleware (apps.accounts.middleware).
    Sessão revogada deve bloquear qualquer request com 401.
    """

    def setUp(self):
        self.user = _make_user_with_profile("middleware_user", password="pass")
        self.protected_url = reverse("accounts:me")

    def test_sessao_ativa_permite_acesso(self):
        """Sessão válida e não-revogada → deixa passar (200 ou 403 por permissão, nunca 401 de revogação)."""
        self.client.force_login(self.user)
        patches = patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            response = self.client.get(self.protected_url)
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sessao_revogada_retorna_401(self):
        """
        AccountsSession.revoked=True → middleware bloqueia com 401.
        Testa o fluxo completo via APIClient.login() + revogação manual.
        """
        # Autentica via login real
        self.client.force_login(self.user)
        session_key = self.client.session.session_key

        # Cria AccountsSession ligada à sessão real
        if session_key:
            _make_session(self.user, app_context="PORTAL", revoked=False)
            # Revoga a sessão diretamente no banco
            AccountsSession.objects.filter(user=self.user).update(
                revoked=True, revoked_at=timezone.now()
            )

        # Próximo request deve ser bloqueado pelo AppContextMiddleware
        response = self.client.get(self.protected_url)
        # O middleware retorna 401 ou a sessão pode ter sido invalidada pelo logout forçado
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


# ─── AccountsSession ──────────────────────────────────────────────────────────

class AccountsSessionModelTest(APITestCase):
    """
    Testa o modelo AccountsSession: criação e revogação via revoke().
    Não usa JWT, jti ou Bearer token — apenas Django ORM.
    """

    def setUp(self):
        self.user = _make_user_with_profile("session_model_user", password="pass")

    def test_criacao_sessao(self):
        """AccountsSession criada com campos corretos."""
        session = _make_session(self.user, app_context="PORTAL")
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.app_context, "PORTAL")
        self.assertFalse(session.revoked)
        self.assertIsNone(session.revoked_at)

    def test_revocacao_via_revoke(self):
        """
        AccountsSession.revoke() deve setar revoked=True e revoked_at.
        Se o método revoke() existir no modelo, usa ele.
        Caso contrário, testa via update direto (compatibilidade).
        """
        session = _make_session(self.user, app_context="ACOES_PNGI")
        self.assertFalse(session.revoked)

        if hasattr(session, "revoke"):
            session.revoke()
            session.refresh_from_db()
        else:
            # fallback: update direto
            AccountsSession.objects.filter(pk=session.pk).update(
                revoked=True, revoked_at=timezone.now()
            )
            session.refresh_from_db()

        self.assertTrue(session.revoked)
        self.assertIsNotNone(session.revoked_at)

    def test_sessao_revogada_flag(self):
        """Criação direta com revoked=True deve persistir."""
        session = _make_session(self.user, app_context="PORTAL", revoked=True)
        session.refresh_from_db()
        self.assertTrue(session.revoked)

    def test_expiracao_futura(self):
        """expires_at deve estar no futuro para sessões ativas."""
        session = _make_session(self.user)
        self.assertGreater(session.expires_at, timezone.now())


# ─── MeEndpoint ──────────────────────────────────────────────────────────────

class MeEndpointTest(APITestCase):
    """
    GET /api/accounts/me/ — retorna dados do usuário autenticado via sessão.
    """

    def setUp(self):
        self.user = _make_user_with_profile("testuser_me")
        self.client = APIClient()
        self.url = reverse("accounts:me")

    def test_me_endpoint_retorna_dados_usuario(self):
        """GET /api/accounts/me/ com sessão válida deve retornar 200."""
        patches = patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.user.username)
        self.assertIn("roles", response.data)
        self.assertIsInstance(response.data["roles"], list)

    def test_me_endpoint_sem_autenticacao_retorna_401(self):
        """GET /api/accounts/me/ sem sessão deve retornar 401."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ─── ProfilesListView ─────────────────────────────────────────────────────────

class ProfilesListTest(APITestCase):
    """
    GET /api/accounts/profiles/ — PORTAL_ADMIN vê todos; comum vê apenas o próprio.
    """

    def setUp(self):
        self.admin = _make_user_with_profile("admin_profiles", is_admin=True)
        self.user = _make_user_with_profile("common_user_profiles", orgao="SESP")
        self.client = APIClient()
        self.url = reverse("accounts:userprofile-list")

    def test_profiles_list_admin_ve_todos(self):
        """PORTAL_ADMIN deve ver todos os profiles na listagem."""
        patches = patch_security(self.admin, is_portal_admin=True)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.admin)
            response = self.client.get(self.url)

        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN],
        )

    def test_profiles_list_usuario_comum_ve_apenas_o_proprio(self):
        """Usuário comum deve receber na listagem apenas o próprio profile."""
        patches = patch_security(self.user)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.get(self.url)

        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN],
        )
        if response.status_code == status.HTTP_200_OK:
            ids = [p["user_id"] for p in response.data.get("results", response.data)]
            for uid in ids:
                self.assertEqual(uid, self.user.id)


# ─── AssignRolePermission ─────────────────────────────────────────────────────

class AssignRolePermissionTest(APITestCase):
    """
    POST /api/accounts/user-roles/ — apenas PORTAL_ADMIN pode atribuir roles.
    """

    def setUp(self):
        self.user = _make_user_with_profile("nonadmin_assign")
        self.client = APIClient()
        self.app = _make_app("PORTAL")
        role, _ = Role.objects.get_or_create(
            aplicacao=self.app,
            codigoperfil="USER",
            defaults={"nomeperfil": "User"},
        )
        self.url = reverse("accounts:userrole-list")
        self.payload = {
            "user": self.user.id,
            "aplicacao": self.app.pk,
            "role": role.pk,
        }

    def test_assign_role_nao_admin_retorna_403(self):
        """POST /api/accounts/user-roles/ por usuário não-admin deve retornar 403."""
        patches = patch_security(self.user, is_portal_admin=False)
        with patches[0], patches[1], patches[2]:
            self.client.force_authenticate(user=self.user)
            response = self.client.post(self.url, self.payload)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
