"""Testes isolados do cliente M2M, sem rede ou banco."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from django.test import override_settings
from django.utils import timezone

from apps.carga_org_lot.services.cliente_iam import (IAMIndisponivel,
                                                     PermissaoIAMNegada,
                                                     SessaoIAMInvalida,
                                                     decidir_acesso_remoto)

CONFIGURACAO = {
    "IAM_URL_CARGA": "http://127.0.0.1:8000/interno/iam/v1/decisoes/",
    "IAM_TOKEN_SERVICO_CARGA": "credencial-m2m-de-teste-com-mais-de-32-caracteres",
}
CREDENCIAIS = {"gpp_session_CARGA_ORG_LOT": "sessao-opaca-de-teste"}


def _resposta(resultado="AUTORIZADO", status=200, **alteracoes):
    dados = {
        "versao": 1,
        "decisao_id": "decisao-123",
        "resultado": resultado,
        "usuario_id": 7,
        "usuario_nome": "Nome de Teste",
        "versao_autorizacao": 4,
        "expira_em": (timezone.now() + timedelta(minutes=5)).isoformat(),
    }
    dados.update(alteracoes)
    return SimpleNamespace(
        status_code=status,
        json=lambda: dados,
    )


@override_settings(**CONFIGURACAO)
def test_decisao_autorizada_usa_timeout_sem_retry_e_sem_redirecionamento():
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", return_value=_resposta()) as postar:
        decisao = decidir_acesso_remoto(
            credenciais=CREDENCIAIS, permissao="view_importacaoplanilha"
        )
    assert decisao["usuario_id"] == 7
    assert decisao["usuario_nome"] == "Nome de Teste"
    assert postar.call_count == 1
    assert postar.call_args.kwargs["timeout"] == (1, 2)
    assert postar.call_args.kwargs["allow_redirects"] is False
    assert postar.call_args.kwargs["json"]["credenciais_usuario"] == [
        {"nome_cookie": "gpp_session_CARGA_ORG_LOT", "valor": "sessao-opaca-de-teste"}
    ]


@override_settings(**CONFIGURACAO)
@pytest.mark.parametrize(
    ("resultado", "erro"),
    [("NEGADO", PermissaoIAMNegada), ("SESSAO_INVALIDA", SessaoIAMInvalida)],
)
def test_negativas_explicitas_sao_diferenciadas(resultado, erro):
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", return_value=_resposta(resultado)):
        with pytest.raises(erro):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")


@override_settings(**CONFIGURACAO)
@pytest.mark.parametrize("status", [301, 401, 404, 500, 503])
def test_falha_de_canal_nao_autoriza(status):
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", return_value=_resposta(status=status)):
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")


@override_settings(**CONFIGURACAO)
def test_timeout_nao_autoriza():
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", side_effect=requests.Timeout("detalhe")):
        with pytest.raises(IAMIndisponivel, match="Decisão IAM indisponível"):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")


@override_settings(**CONFIGURACAO)
def test_resposta_malformada_nao_autoriza():
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", return_value=SimpleNamespace(status_code=200, json=lambda: {"versao": 1, "resultado": "AUTORIZADO"})):
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")


@override_settings(**CONFIGURACAO)
@pytest.mark.parametrize(
    "alteracoes",
    [
        {"versao": 2},
        {"versao": True},
        {"resultado": "DESCONHECIDO"},
        {"decisao_id": ""},
        {"usuario_id": True},
        {"usuario_id": 0},
        {"usuario_nome": ""},
        {"usuario_nome": None},
        {"usuario_nome": "Nome\nforjado"},
        {"usuario_nome": "N" * 201},
        {"usuario_nome": 7},
        {"versao_autorizacao": -1},
        {"expira_em": "2026-01-01T00:00:00+00:00"},
        {"expira_em": "sem-data"},
        {"expira_em": "2099-01-01T00:00:00"},
    ],
)
def test_respostas_inconsistentes_falham_fechadas(alteracoes):
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", return_value=_resposta(**alteracoes)):
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")


@override_settings(**CONFIGURACAO)
def test_iam_anterior_sem_nome_continua_aceito_no_piloto_local():
    resposta = _resposta()
    dados = resposta.json()
    del dados["usuario_nome"]
    with patch(
        "apps.carga_org_lot.services.cliente_iam.requests.post",
        return_value=SimpleNamespace(status_code=200, json=lambda: dados),
    ):
        decisao = decidir_acesso_remoto(
            credenciais=CREDENCIAIS, permissao="view_importacaoplanilha"
        )
    assert decisao["usuario_id"] == 7
    assert decisao["usuario_nome"] is None


@override_settings(**CONFIGURACAO)
def test_negativa_sem_usuario_conhecido_nao_e_tratada_como_403():
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", return_value=_resposta("NEGADO", usuario_id=None)):
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")


@override_settings(**CONFIGURACAO)
def test_erro_json_nao_autoriza():
    resposta = SimpleNamespace(status_code=200, json=lambda: (_ for _ in ()).throw(ValueError("json inválido")))
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", return_value=resposta):
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")


@override_settings(**CONFIGURACAO)
def test_correlacao_invalida_e_substituida_sem_propagacao():
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post", return_value=_resposta()) as postar:
        decidir_acesso_remoto(
            credenciais=CREDENCIAIS,
            permissao="view_importacaoplanilha",
            correlacao="valor\nAuthorization: segredo",
        )
    assert postar.call_args.kwargs["headers"]["X-Correlation-ID"] != "valor\nAuthorization: segredo"


@override_settings(**CONFIGURACAO)
@pytest.mark.parametrize("credenciais", [{}, {"outro": "x"}, {"gpp_session_PORTAL": ""}])
def test_credenciais_invalidas_nao_sao_enviadas(credenciais):
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post") as postar:
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=credenciais, permissao="view_importacaoplanilha")
    postar.assert_not_called()


@override_settings(IAM_URL_CARGA=CONFIGURACAO["IAM_URL_CARGA"], IAM_TOKEN_SERVICO_CARGA="")
def test_credencial_m2m_ausente_nao_envia_sessao():
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post") as postar:
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")
    postar.assert_not_called()


@override_settings(**CONFIGURACAO)
@pytest.mark.parametrize("permissao", ["", "../admin", "View_importacao", "área"])
def test_permissao_invalida_nao_e_enviada(permissao):
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post") as postar:
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao=permissao)
    postar.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://exemplo.org/interno/iam/v1/decisoes/",
        "https://usuario:senha@exemplo.org/interno/iam/v1/decisoes/",
        "https://exemplo.org/interno/iam/v1/decisoes/?redirect=1",
        "https://exemplo.org/outra/rota/",
        "http://127.0.0.1:porta/interno/iam/v1/decisoes/",
    ],
)
def test_destino_invalido_nao_recebe_sessao(url):
    with override_settings(IAM_URL_CARGA=url, IAM_TOKEN_SERVICO_CARGA=CONFIGURACAO["IAM_TOKEN_SERVICO_CARGA"]):
        with patch("apps.carga_org_lot.services.cliente_iam.requests.post") as postar:
            with pytest.raises(IAMIndisponivel):
                decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")
    postar.assert_not_called()


@override_settings(IAM_URL_CARGA="http://exemplo.org/interno/iam/v1/decisoes/", IAM_TOKEN_SERVICO_CARGA=CONFIGURACAO["IAM_TOKEN_SERVICO_CARGA"])
def test_url_http_externa_e_bloqueada_antes_de_enviar_sessao():
    with patch("apps.carga_org_lot.services.cliente_iam.requests.post") as postar:
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(credenciais=CREDENCIAIS, permissao="view_importacaoplanilha")
    postar.assert_not_called()
