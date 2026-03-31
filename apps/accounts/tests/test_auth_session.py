# apps/accounts/tests/test_auth_session.py
"""
Testes de autenticação baseada em sessão (multi-cookie).
Cobre: AccountsSession.__str__ (models.py 383–386) via login real.
"""
import pytest
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import AccountsSession

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/accounts/login/"


# ─── Fixtures de suporte ─────────────────────────────────────────────────────

@pytest.fixture
def authenticated_session(gestor_pngi):
    """Retorna (client, session_key) após login bem-sucedido."""
    client = APIClient()
    resp = client.post(LOGIN_URL, {
        "username": gestor_pngi.username,
        "password": "TestPass@2026",
        "app_context": "ACOES_PNGI",
    }, format="json")
    assert resp.status_code == 200, (
        f"Login falhou ao montar fixture: {resp.status_code} {resp.data}"
    )
    session_key = client.cookies["gpp_session_ACOES_PNGI"].value
    return client, session_key


# ─── Testes de fluxo de sessão ────────────────────────────────────────────────

class TestLoginSessionCookie:

    def test_login_retorna_200(self, gestor_pngi):
        client = APIClient()
        resp = client.post(LOGIN_URL, {
            "username": gestor_pngi.username,
            "password": "TestPass@2026",
            "app_context": "ACOES_PNGI",
        }, format="json")
        assert resp.status_code == 200

    def test_login_gera_cookie_gpp_session(self, gestor_pngi):
        client = APIClient()
        resp = client.post(LOGIN_URL, {
            "username": gestor_pngi.username,
            "password": "TestPass@2026",
            "app_context": "ACOES_PNGI",
        }, format="json")
        assert "gpp_session_ACOES_PNGI" in resp.cookies

    def test_login_cria_accounts_session_no_banco(self, gestor_pngi):
        client = APIClient()
        client.post(LOGIN_URL, {
            "username": gestor_pngi.username,
            "password": "TestPass@2026",
            "app_context": "ACOES_PNGI",
        }, format="json")
        assert AccountsSession.objects.filter(
            user=gestor_pngi,
            app_context="ACOES_PNGI",
            revoked=False,
        ).exists()

    def test_login_invalido_retorna_401(self, gestor_pngi):
        client = APIClient()
        resp = client.post(LOGIN_URL, {
            "username": gestor_pngi.username,
            "password": "SenhaErrada!",
            "app_context": "ACOES_PNGI",
        }, format="json")
        assert resp.status_code == 401

    def test_acesso_autenticado_retorna_200_ou_403(
        self, authenticated_session
    ):
        client, _ = authenticated_session
        resp = client.get("/api/accounts/me/")
        assert resp.status_code in (200, 403)

    def test_acesso_sem_cookie_retorna_401_ou_403(self):
        client = APIClient()
        resp = client.get("/api/accounts/me/")
        assert resp.status_code in (401, 403)

    def test_logout_revoga_sessao(self, authenticated_session, gestor_pngi):
        client, session_key = authenticated_session
        client.post("/api/accounts/logout/ACOES_PNGI/")
        session = AccountsSession.objects.filter(
            user=gestor_pngi,
            session_key=session_key,
        ).first()
        if session:
            assert session.revoked is True


# ─── AccountsSession.__str__ (models.py 383–386) ─────────────────────────────

class TestAccountsSessionModel:

    def test_str_apos_login_retorna_string_sem_excecao(
        self, authenticated_session, gestor_pngi
    ):
        """
        models.py 383–386: Após login bem-sucedido, recuperar a
        AccountsSession do banco e chamar str() → deve retornar string
        sem exceção, contendo user_id + session_key + app_context.
        """
        _, session_key = authenticated_session
        session = AccountsSession.objects.get(
            user=gestor_pngi,
            session_key=session_key,
        )
        resultado = str(session)
        assert isinstance(resultado, str)
        assert len(resultado) > 0
        assert str(gestor_pngi.pk) in resultado
        assert session_key in resultado
        assert "ACOES_PNGI" in resultado

    def test_str_contém_app_context(
        self, gestor_pngi
    ):
        """
        Criação direta de AccountsSession e verificação do __str__.
        """
        session = AccountsSession.objects.create(
            user=gestor_pngi,
            session_key="direct_test_key_456",
            app_context="ACOES_PNGI",
            session_cookie_name="gpp_session_ACOES_PNGI",
            expires_at=timezone.now() + timedelta(hours=2),
            revoked=False,
        )
        resultado = str(session)
        assert "ACOES_PNGI" in resultado
        assert "direct_test_key_456" in resultado

    def test_str_portal_admin_session(
        self, portal_admin
    ):
        """
        Verifica que __str__ funciona para qualquer app_context (PORTAL).
        """
        session = AccountsSession.objects.create(
            user=portal_admin,
            session_key="portal_test_key_789",
            app_context="PORTAL",
            session_cookie_name="gpp_session_PORTAL",
            expires_at=timezone.now() + timedelta(hours=1),
            revoked=False,
        )
        resultado = str(session)
        assert "PORTAL" in resultado
        assert str(portal_admin.pk) in resultado
