"""A vivacidade não pode depender de sessão, IAM ou cadastro de aplicações."""

from unittest.mock import patch

from django.test import Client


def test_health_preserva_contrato_e_nao_consulta_cadastro_de_aplicacoes():
    with patch(
        "apps.core.middleware.application_context.ApplicationRegistry",
        side_effect=AssertionError("cadastro consultado"),
    ):
        response = Client().get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gpp_plataform2"}
    assert response["Cache-Control"] == "no-store"


def test_health_ignora_cookie_de_aplicacao_sem_validar_sessao():
    client = Client()
    client.cookies["gpp_session_CARGA_ORG_LOT"] = "sessao-invalida"

    with patch(
        "apps.accounts.middleware.AccountsSession.objects.filter",
        side_effect=AssertionError("sessao consultada"),
    ):
        response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
