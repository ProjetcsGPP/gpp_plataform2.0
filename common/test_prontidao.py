"""A prontidão local não substitui a autorização nem a vivacidade."""

from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.test import Client, override_settings
from django.urls import resolve


PERFIS = (
    ("config.urls", "gpp_plataform2"),
    ("config.urls_carga_piloto", "carga_org_lot"),
    ("config.urls_publicacoes_piloto", "pub_institucional"),
    ("config.urls_plataforma_piloto", "plataforma"),
    ("config.urls_plataforma_separada_piloto", "plataforma"),
    ("config.urls_acoes_piloto", "acoes_pngi"),
    ("config.urls_plataforma_quatro_piloto", "plataforma"),
)


@pytest.mark.parametrize("urlconf,servico", PERFIS)
def test_prontidao_por_perfil_sem_iam(urlconf, servico):
    with override_settings(ROOT_URLCONF=urlconf):
        with patch("common.health.connection.cursor") as cursor:
            with patch(
                "apps.core.middleware.application_context.ApplicationRegistry",
                side_effect=AssertionError("cadastro IAM consultado"),
            ):
                resposta = Client().get("/api/ready/")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "pronto", "service": servico}
    assert resposta["Cache-Control"] == "no-store"
    cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
        "SELECT 1"
    )
    assert resolve("/api/ready/", urlconf=urlconf).url_name


@pytest.mark.parametrize("urlconf,servico", PERFIS)
def test_falha_do_banco_nao_revela_excecao(urlconf, servico, caplog):
    with override_settings(ROOT_URLCONF=urlconf):
        with patch(
            "common.health.connection.cursor",
            side_effect=DatabaseError("segredo-sintetico-na-excecao"),
        ):
            resposta = Client().get("/api/ready/")

    assert resposta.status_code == 503
    assert resposta.json() == {"status": "indisponivel", "service": servico}
    assert resposta["Cache-Control"] == "no-store"
    assert "segredo-sintetico-na-excecao" not in caplog.text
    assert "READINESS_FAIL" in caplog.text


def test_prontidao_nao_aceita_mutacao():
    with patch("common.health.connection.cursor") as cursor:
        resposta = Client().post("/api/ready/")

    assert resposta.status_code == 405
    cursor.assert_not_called()


def test_prontidao_ignora_cookie_invalido_sem_consultar_sessao():
    cliente = Client()
    cliente.cookies["gpp_session_PUB_INSTITUCIONAL"] = "sessao-invalida"

    with patch("common.health.connection.cursor"):
        with patch(
            "apps.accounts.middleware.AccountsSession.objects.filter",
            side_effect=AssertionError("sessao IAM consultada"),
        ):
            resposta = cliente.get("/api/ready/")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "pronto"


def test_prontidao_aceita_head_sem_corpo():
    with patch("common.health.connection.cursor"):
        resposta = Client().head("/api/ready/")

    assert resposta.status_code == 200
    assert not resposta.content
