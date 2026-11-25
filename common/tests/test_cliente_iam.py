"""Validação do transporte IAM compartilhado sem rede ou banco."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from common.services.cliente_iam import (
    IAMIndisponivel, PermissaoIAMNegada, SessaoIAMInvalida,
    decidir_acesso_remoto,
    decidir_atividade_remota,
)

CAMINHO = "/interno/iam/v1/decisoes-publicacoes/"
PARAMETROS = {
    "url": "http://127.0.0.1:8000" + CAMINHO,
    "caminho": CAMINHO,
    "token": "credencial-m2m-sintetica-de-integracao",
    "credenciais": {"gpp_session_PUB_INSTITUCIONAL": "sessao-opaca"},
    "nome_cookie": "gpp_session_PUB_INSTITUCIONAL",
    "permissao": "view_patriarcaedocs",
}
PARAMETROS_ATIVIDADE = {
    "url_decisao": PARAMETROS["url"],
    "caminho_decisao": CAMINHO,
    "caminho_atividade": "/interno/iam/v1/decisoes-atividade-publicacoes/",
    "token": PARAMETROS["token"],
    "usuario_id": 7,
    "permissao": "solicitar_coleta_mensal_edocs",
}


def test_atividade_remota_nao_envia_cookie_e_valida_resposta():
    dados = {"versao": 1, "decisao_id": "decisao-1", "resultado": "AUTORIZADO",
             "usuario_id": 7, "versao_autorizacao": 3}
    resposta = SimpleNamespace(status_code=200, json=lambda: dados)
    with patch("common.services.cliente_iam.requests.post", return_value=resposta) as postar:
        assert decidir_atividade_remota(**PARAMETROS_ATIVIDADE)["versao_autorizacao"] == 3
    assert postar.call_args.args[0].endswith("/decisoes-atividade-publicacoes/")
    assert postar.call_args.kwargs["json"] == {
        "usuario_id": 7, "acao": "solicitar_coleta_mensal_edocs",
    }
    assert "Cookie" not in postar.call_args.kwargs["headers"]


def test_atividade_remota_nega_revogacao_e_identidade_divergente():
    dados = {"versao": 1, "decisao_id": "decisao-1", "resultado": "NEGADO",
             "usuario_id": 7}
    resposta = SimpleNamespace(status_code=200, json=lambda: dados)
    with patch("common.services.cliente_iam.requests.post", return_value=resposta):
        with pytest.raises(PermissaoIAMNegada):
            decidir_atividade_remota(**PARAMETROS_ATIVIDADE)
    dados["resultado"] = "AUTORIZADO"
    dados["usuario_id"] = 8
    dados["versao_autorizacao"] = 2
    with patch("common.services.cliente_iam.requests.post", return_value=resposta):
        with pytest.raises(IAMIndisponivel):
            decidir_atividade_remota(**PARAMETROS_ATIVIDADE)


def _resposta(resultado="AUTORIZADO", **alteracoes):
    dados = {
        "versao": 1,
        "decisao_id": "decisao-sintetica",
        "resultado": resultado,
        "usuario_id": 1,
        "usuario_nome": "Gestor",
        "versao_autorizacao": 2,
        "expira_em": (timezone.now() + timedelta(minutes=5)).isoformat(),
    }
    dados.update(alteracoes)
    return SimpleNamespace(status_code=200, json=lambda: dados)


def test_decisao_valida_preserva_identidade_e_sem_redirecionamento():
    with patch("common.services.cliente_iam.requests.post", return_value=_resposta()) as postar:
        decisao = decidir_acesso_remoto(**PARAMETROS)
    assert decisao["usuario_nome"] == "Gestor"
    assert postar.call_args.kwargs["allow_redirects"] is False
    assert postar.call_args.kwargs["timeout"] == (1, 2)
    assert postar.call_args.kwargs["json"]["acao"] == "view_patriarcaedocs"


@pytest.mark.parametrize("url", [
    "http://iam.exemplo.org" + CAMINHO,
    "http://127.0.0.1:8000/interno/iam/v1/decisoes/",
    "https://usuario:senha@iam.exemplo.org" + CAMINHO,
    "https://iam.exemplo.org" + CAMINHO + "?destino=outro",
])
def test_url_insegura_ou_inesperada_falha_sem_rede(url):
    with patch("common.services.cliente_iam.requests.post") as postar:
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(**{**PARAMETROS, "url": url})
    postar.assert_not_called()


@pytest.mark.parametrize("credenciais", [
    {"gpp_session_PORTAL": "sessao-portal"},
    {
        "gpp_session_PUB_INSTITUCIONAL": "sessao-opaca",
        "gpp_session_PORTAL": "sessao-portal",
    },
])
def test_cookie_de_outra_app_falha_antes_da_rede(credenciais):
    with patch("common.services.cliente_iam.requests.post") as postar:
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(**{**PARAMETROS, "credenciais": credenciais})
    postar.assert_not_called()


@pytest.mark.parametrize("alteracoes", [
    {"versao": 2},
    {"versao": True},
    {"usuario_id": True},
    {"usuario_nome": ""},
    {"expira_em": "2020-01-01T00:00:00+00:00"},
])
def test_resposta_invalida_falha_fechada(alteracoes):
    with patch("common.services.cliente_iam.requests.post", return_value=_resposta(**alteracoes)):
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(**PARAMETROS)


@pytest.mark.parametrize("resultado,excecao", [
    ("SESSAO_INVALIDA", SessaoIAMInvalida),
    ("NEGADO", PermissaoIAMNegada),
])
def test_negativas_explicitas_nao_sao_confundidas_com_indisponibilidade(resultado, excecao):
    with patch("common.services.cliente_iam.requests.post", return_value=_resposta(resultado)):
        with pytest.raises(excecao):
            decidir_acesso_remoto(**PARAMETROS)
