# apps/accounts/tests/test_auth_session.py
"""
Testes de autenticacao baseada em sessao Django.

Endpoints cobertos:
  POST /api/accounts/login/
  POST /api/accounts/logout/
  GET  /api/accounts/me/

USA transaction=True porque:
  - AccountsSession.revoked precisa ser persistido e lido em queries separadas
    dentro do mesmo teste (sem savepoints intermediarios que escondam o estado).
  - O teardown usa TRUNCATE CASCADE via fixture local para evitar o bloqueio
    de tblusuarioresponsavel.

NOTA ARQUITETURAL — SwitchAppView removida:
  No modelo multi-cookie cada app possui sessao independente
  (gpp_session_{APP}). Nao ha contexto unico para "trocar" — o frontend
  simplesmente faz um segundo POST /login/ com o app_context desejado,
  recebendo um cookie distinto sem invalidar os demais.
"""
import pytest
from apps.accounts.models import AccountsSession

pytestmark = pytest.mark.django_db(transaction=True)

LOGIN_URL  = "/api/accounts/login/"
LOGOUT_URL = "/api/accounts/logout/"
ME_URL     = "/api/accounts/me/"


# --- Login -------------------------------------------------------------------

class TestLogin:

    def test_login_sucesso_acoes_pngi(self, client_anonimo, gestor_pngi):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "gestor_test", "password": "TestPass@2026",
             "app_context": "ACOES_PNGI"},
            format="json",
        )
        assert resp.status_code == 200

    def test_login_cria_accounts_session(self, client_anonimo, gestor_pngi):
        client_anonimo.post(
            LOGIN_URL,
            {"username": "gestor_test", "password": "TestPass@2026",
             "app_context": "ACOES_PNGI"},
            format="json",
        )
        assert AccountsSession.objects.filter(
            user=gestor_pngi,
            app_context="ACOES_PNGI",
            revoked=False,
        ).exists()

    def test_login_credenciais_invalidas(self, client_anonimo, gestor_pngi):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "gestor_test", "password": "senha_errada",
             "app_context": "ACOES_PNGI"},
            format="json",
        )
        assert resp.status_code == 401
        assert resp.data.get("code") == "invalid_credentials"

    def test_login_campos_ausentes_retorna_400(self, client_anonimo):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "gestor_test"},
            format="json",
        )
        assert resp.status_code == 400

    def test_login_app_context_inexistente(self, client_anonimo, gestor_pngi):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "gestor_test", "password": "TestPass@2026",
             "app_context": "APP_NAO_EXISTE"},
            format="json",
        )
        assert resp.status_code == 403
        assert resp.data.get("code") == "invalid_app"

    def test_login_usuario_sem_role_na_app(self, client_anonimo, usuario_sem_role):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "sem_role_test", "password": "TestPass@2026",
             "app_context": "ACOES_PNGI"},
            format="json",
        )
        assert resp.status_code == 403

    def test_login_portal_rejeita_usuario_comum(self, client_anonimo, gestor_pngi):
        """GESTOR_PNGI nao tem PORTAL_ADMIN -- nao deve acessar o PORTAL."""
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "gestor_test", "password": "TestPass@2026",
             "app_context": "PORTAL"},
            format="json",
        )
        assert resp.status_code == 403

    def test_login_portal_admin_acessa_portal(self, client_anonimo, portal_admin):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "portal_admin_test", "password": "TestPass@2026",
             "app_context": "PORTAL"},
            format="json",
        )
        assert resp.status_code == 200

    def test_login_superuser_acessa_portal(self, client_anonimo, superuser):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "superuser_test", "password": "TestPass@2026",
             "app_context": "PORTAL"},
            format="json",
        )
        assert resp.status_code == 200

    def test_login_coordenador_pngi(self, client_anonimo, coordenador_pngi):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "coordenador_test", "password": "TestPass@2026",
             "app_context": "ACOES_PNGI"},
            format="json",
        )
        assert resp.status_code == 200

    def test_login_operador_acao(self, client_anonimo, operador_acao):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "operador_test", "password": "TestPass@2026",
             "app_context": "ACOES_PNGI"},
            format="json",
        )
        assert resp.status_code == 200

    def test_login_gestor_carga(self, client_anonimo, gestor_carga):
        resp = client_anonimo.post(
            LOGIN_URL,
            {"username": "gestor_carga_test", "password": "TestPass@2026",
             "app_context": "CARGA_ORG_LOT"},
            format="json",
        )
        assert resp.status_code == 200


# --- Logout ------------------------------------------------------------------

class TestLogout:

    def test_logout_retorna_200(self, client_gestor):
        resp = client_gestor.post(LOGOUT_URL, format="json")
        assert resp.status_code == 200

    def test_logout_revoga_accounts_session(self, client_gestor, gestor_pngi):
        client_gestor.post(LOGOUT_URL, format="json")
        assert not AccountsSession.objects.filter(
            user=gestor_pngi,
            revoked=False,
        ).exists()

    def test_logout_sem_autenticacao_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.post(LOGOUT_URL, format="json")
        assert resp.status_code in (401, 403)


# --- MeView ------------------------------------------------------------------

class TestMeView:

    def test_me_retorna_200(self, client_gestor):
        resp = client_gestor.get(ME_URL)
        assert resp.status_code == 200

    def test_me_retorna_username_correto(self, client_gestor):
        resp = client_gestor.get(ME_URL)
        assert resp.data.get("username") == "gestor_test"

    def test_me_contem_campo_roles_ou_user_roles(self, client_gestor):
        resp = client_gestor.get(ME_URL)
        assert "roles" in resp.data or "user_roles" in resp.data

    def test_me_coordenador_retorna_dados_corretos(self, client_coordenador):
        resp = client_coordenador.get(ME_URL)
        assert resp.status_code == 200
        assert resp.data.get("username") == "coordenador_test"

    def test_me_nao_autenticado_retorna_401_ou_403(self, client_anonimo):
        resp = client_anonimo.get(ME_URL)
        assert resp.status_code in (401, 403)
