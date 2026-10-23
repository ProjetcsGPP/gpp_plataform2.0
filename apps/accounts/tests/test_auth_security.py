"""Regressão de segurança para login, CSRF, throttle e sessões multi-cookie."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AccountsSession

pytestmark = pytest.mark.django_db

CSRF_URL = "/api/accounts/auth/csrf/"
LOGIN_URL = "/api/accounts/login/"
ME_URL = "/api/accounts/me/"
RESOLVE_URL = "/api/accounts/auth/resolve-user/"
PASSWORD = "TestPass@2026"


def _payload(identifier, app_context="ACOES_PNGI", password=PASSWORD):
    return {
        "identifier": identifier,
        "password": password,
        "app_context": app_context,
    }


def _csrf_client():
    client = APIClient(enforce_csrf_checks=True)
    response = client.get(CSRF_URL)
    assert response.status_code == 200
    token = client.cookies["csrftoken"].value
    return client, token


class TestLoginIdentifierAndEnumeration:
    def test_login_por_username(self, gestor_pngi):
        response = APIClient().post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )
        assert response.status_code == 200

    def test_login_por_email_case_insensitive(self, gestor_pngi):
        gestor_pngi.email = "Gestor.Security@Teste.Gov.Br"
        gestor_pngi.save(update_fields=["email"])

        response = APIClient().post(
            LOGIN_URL,
            _payload("gestor.security@teste.gov.br"),
            format="json",
        )

        assert response.status_code == 200

    def test_alias_username_permanece_compativel(self, gestor_pngi):
        response = APIClient().post(
            LOGIN_URL,
            {
                "username": gestor_pngi.username,
                "password": PASSWORD,
                "app_context": "ACOES_PNGI",
            },
            format="json",
        )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "identifier,password",
        [
            ("usuario-inexistente", PASSWORD),
            ("inexistente@teste.gov.br", PASSWORD),
            ("gestor_test", "senha-incorreta"),
        ],
    )
    def test_falhas_nao_revelam_existencia(
        self, gestor_pngi, identifier, password
    ):
        response = APIClient().post(
            LOGIN_URL,
            _payload(identifier, password=password),
            format="json",
        )
        assert response.status_code == 401
        assert response.data == {
            "detail": "Credenciais inválidas.",
            "code": "invalid_credentials",
        }

    def test_usuario_inativo_recebe_mesma_falha_generica(self, gestor_pngi):
        gestor_pngi.is_active = False
        gestor_pngi.save(update_fields=["is_active"])

        response = APIClient().post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )

        assert response.status_code == 401
        assert response.data["code"] == "invalid_credentials"

    def test_email_duplicado_falha_sem_escolher_usuario(
        self, gestor_pngi, coordenador_pngi
    ):
        gestor_pngi.email = "duplicado@teste.gov.br"
        coordenador_pngi.email = "duplicado@teste.gov.br"
        gestor_pngi.save(update_fields=["email"])
        coordenador_pngi.save(update_fields=["email"])

        response = APIClient().post(
            LOGIN_URL, _payload("duplicado@teste.gov.br"), format="json"
        )

        assert response.status_code == 401
        assert response.data["code"] == "invalid_credentials"

    def test_endpoint_de_resolucao_foi_descontinuado(self):
        response = APIClient().post(
            RESOLVE_URL, {"identifier": "qualquer"}, format="json"
        )
        assert response.status_code == 404


class TestCsrfContract:
    def test_bootstrap_emite_cookie_legivel_pelo_frontend(self):
        response = APIClient().get(CSRF_URL)
        cookie = response.cookies["csrftoken"]

        assert response.status_code == 200
        assert cookie.value
        assert cookie["httponly"] == ""
        assert cookie["samesite"] == "Lax"

    def test_login_sem_cookie_csrf_e_rejeitado(self, gestor_pngi):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )
        assert response.status_code == 403

    def test_login_com_cookie_sem_header_csrf_e_rejeitado(self, gestor_pngi):
        client, _ = _csrf_client()
        response = client.post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )
        assert response.status_code == 403

    def test_login_com_bootstrap_e_header_csrf_funciona(self, gestor_pngi):
        client, token = _csrf_client()
        response = client.post(
            LOGIN_URL,
            _payload(gestor_pngi.username),
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert response.status_code == 200

    def test_mutacao_autenticada_sem_csrf_e_rejeitada(self, gestor_pngi):
        login_client = APIClient()
        login_response = login_client.post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )
        session_cookie = login_response.cookies["gpp_session_ACOES_PNGI"].value

        client = APIClient(enforce_csrf_checks=True)
        client.cookies["gpp_session_ACOES_PNGI"] = session_cookie
        response = client.post("/api/accounts/logout/", format="json")

        assert response.status_code == 403

    def test_mutacao_autenticada_com_csrf_funciona(self, gestor_pngi):
        client, token = _csrf_client()
        login_response = client.post(
            LOGIN_URL,
            _payload(gestor_pngi.username),
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert login_response.status_code == 200

        rotated_token = client.cookies["csrftoken"].value
        response = client.post(
            "/api/accounts/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=rotated_token,
        )
        assert response.status_code == 200

    def test_logout_seletivo_sem_csrf_e_rejeitado(self, gestor_pngi):
        client, token = _csrf_client()
        login_response = client.post(
            LOGIN_URL,
            _payload(gestor_pngi.username),
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert login_response.status_code == 200

        response = client.post("/api/accounts/logout/acoes-pngi/", format="json")
        assert response.status_code == 403

    def test_logout_seletivo_com_csrf_revoga_somente_a_sessao(
        self, gestor_pngi
    ):
        client, token = _csrf_client()
        login_response = client.post(
            LOGIN_URL,
            _payload(gestor_pngi.username),
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert login_response.status_code == 200
        session_key = client.cookies["gpp_session_ACOES_PNGI"].value

        rotated_token = client.cookies["csrftoken"].value
        response = client.post(
            "/api/accounts/logout/acoes-pngi/",
            format="json",
            HTTP_X_CSRFTOKEN=rotated_token,
        )

        assert response.status_code == 200
        assert AccountsSession.objects.get(session_key=session_key).revoked is True


class TestSessionAndCookieValidation:
    def test_cookie_de_sessao_usa_atributos_configurados(self, gestor_pngi):
        response = APIClient().post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )
        cookie = response.cookies["gpp_session_ACOES_PNGI"]

        assert cookie["httponly"] is True
        assert cookie["samesite"] == "Lax"
        assert cookie["path"] == "/"
        assert int(cookie["max-age"]) == 3600

    def test_cookies_respeitam_secure_quando_habilitado(
        self, gestor_pngi, settings
    ):
        settings.SESSION_COOKIE_SECURE = True
        settings.CSRF_COOKIE_SECURE = True
        client = APIClient()

        csrf_response = client.get(CSRF_URL)
        login_response = client.post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )

        assert csrf_response.cookies["csrftoken"]["secure"] is True
        assert login_response.cookies["gpp_session_ACOES_PNGI"]["secure"] is True

    @pytest.mark.parametrize("invalid_state", ["expired", "revoked", "inactive"])
    def test_sessao_invalida_nao_autentica(self, gestor_pngi, invalid_state):
        client = APIClient()
        login_response = client.post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )
        assert login_response.status_code == 200

        session = AccountsSession.objects.get(
            session_key=client.cookies["gpp_session_ACOES_PNGI"].value
        )
        if invalid_state == "expired":
            session.expires_at = timezone.now() - timedelta(seconds=1)
            session.save(update_fields=["expires_at"])
        elif invalid_state == "revoked":
            session.revoked = True
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked", "revoked_at"])
        else:
            gestor_pngi.is_active = False
            gestor_pngi.save(update_fields=["is_active"])

        response = client.get(ME_URL)
        assert response.status_code in (401, 403)

    def test_cookie_nao_autentica_contexto_divergente(self, gestor_pngi):
        client = APIClient()
        login_response = client.post(
            LOGIN_URL, _payload(gestor_pngi.username), format="json"
        )
        assert login_response.status_code == 200

        session = AccountsSession.objects.get(
            session_key=client.cookies["gpp_session_ACOES_PNGI"].value
        )
        session.app_context = "CARGA_ORG_LOT"
        session.save(update_fields=["app_context"])

        response = client.get(ME_URL)
        assert response.status_code in (401, 403)


class TestLoginThrottle:
    def test_throttle_especifico_limita_por_ip(self, settings):
        settings.LOGIN_THROTTLE_RATE = "2/min"
        cache.clear()
        client = APIClient()
        payload = _payload("inexistente", app_context="PORTAL")

        first = client.post(
            LOGIN_URL, payload, format="json", REMOTE_ADDR="198.51.100.10"
        )
        second = client.post(
            LOGIN_URL, payload, format="json", REMOTE_ADDR="198.51.100.10"
        )
        blocked = client.post(
            LOGIN_URL, payload, format="json", REMOTE_ADDR="198.51.100.10"
        )
        other_ip = client.post(
            LOGIN_URL, payload, format="json", REMOTE_ADDR="198.51.100.11"
        )

        assert first.status_code == 401
        assert second.status_code == 401
        assert blocked.status_code == 429
        assert other_ip.status_code == 401

    def test_x_forwarded_for_nao_contorna_limite_por_padrao(self, settings):
        settings.LOGIN_THROTTLE_RATE = "2/min"
        cache.clear()
        client = APIClient()
        payload = _payload("inexistente", app_context="PORTAL")

        responses = [
            client.post(
                LOGIN_URL,
                payload,
                format="json",
                REMOTE_ADDR="198.51.100.20",
                HTTP_X_FORWARDED_FOR=spoofed_ip,
            )
            for spoofed_ip in (
                "203.0.113.1",
                "203.0.113.2",
                "203.0.113.3",
            )
        ]

        assert [response.status_code for response in responses] == [401, 401, 429]
