"""Testes do cliente E-Docs sem chamadas externas."""

import pytest
import requests
from django.test import override_settings

from apps.pub_institucional.services.cliente_edocs import (ClienteEdocs,
                                                           ErroRequisicaoEdocs)
from apps.pub_institucional.services.credenciais_edocs import \
    obter_credenciais_edocs


class RespostaSimulada:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class SessaoSimulada:
    def __init__(self, *, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)


@override_settings(
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_obtem_credenciais_edocs_do_ambiente():
    credenciais = obter_credenciais_edocs()

    assert credenciais.id_cliente == "synthetic-client"
    assert credenciais.segredo_cliente == "synthetic-secret"


@override_settings(
    GPP_EDOCS_ENVIRONMENT="HML",
    GPP_EDOCS_HML_API_BASE_URL="https://edocs.example",
    GPP_EDOCS_HML_TOKEN_URL="https://auth.example/token",
    GPP_EDOCS_HML_SCOPE="api-sigades-consultar",
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_cliente_usa_credenciais_e_cabecalho_de_autorizacao():
    session = SessaoSimulada(
        post_responses=[RespostaSimulada(200, {"access_token": "short-token"})],
        get_responses=[RespostaSimulada(200, [{"id": "patriarch"}])],
    )
    client = ClienteEdocs(sessao=session)

    assert client.listar_patriarcas() == [{"id": "patriarch"}]
    assert session.post_calls[0][1]["data"] == {
        "grant_type": "client_credentials",
        "client_id": "synthetic-client",
        "client_secret": "synthetic-secret",
        "scope": "api-sigades-consultar",
    }
    assert session.get_calls[0][1]["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer short-token",
    }
    assert session.get_calls[0][0] == (
        "https://edocs.example/v2/agente/patriarcas"
    )


@override_settings(
    GPP_EDOCS_ENVIRONMENT="PRD",
    GPP_EDOCS_PRD_API_BASE_URL="https://edocs.example",
    GPP_EDOCS_PRD_TOKEN_URL="https://auth.example/token",
    GPP_EDOCS_PRD_SCOPE="api-sigades-consultar",
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_cliente_renova_token_uma_vez_apos_nao_autorizado():
    session = SessaoSimulada(
        post_responses=[
            RespostaSimulada(200, {"access_token": "old-token"}),
            RespostaSimulada(200, {"access_token": "new-token"}),
        ],
        get_responses=[
            RespostaSimulada(401, {}),
            RespostaSimulada(200, []),
        ],
    )
    client = ClienteEdocs(sessao=session)

    assert client.relatorio_documentos("10", 2025) == []
    assert len(session.post_calls) == 2
    assert session.get_calls[1][1]["headers"]["Authorization"] == (
        "Bearer new-token"
    )


@override_settings(
    GPP_EDOCS_ENVIRONMENT="HML",
    GPP_EDOCS_HML_API_BASE_URL="https://edocs.example",
    GPP_EDOCS_HML_TOKEN_URL="https://auth.example/token",
    GPP_EDOCS_HML_SCOPE="api-sigades-consultar",
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_cliente_oculta_detalhes_do_erro_remoto():
    session = SessaoSimulada(
        post_responses=[RespostaSimulada(403, {"client_secret": "must-not-leak"})]
    )
    client = ClienteEdocs(sessao=session)

    with pytest.raises(ErroRequisicaoEdocs) as erro:
        client.listar_patriarcas()

    mensagem = str(erro.value)
    assert "must-not-leak" not in mensagem
    assert "synthetic-secret" not in mensagem


@override_settings(
    GPP_EDOCS_ENVIRONMENT="HML",
    GPP_EDOCS_HML_API_BASE_URL="https://edocs.example",
    GPP_EDOCS_HML_TOKEN_URL="https://auth.example/token",
    GPP_EDOCS_HML_SCOPE="api-sigades-consultar",
    GPP_EDOCS_CREDENTIALS_PROVIDER="environment",
    GPP_EDOCS_CLIENT_ID="synthetic-client",
    GPP_EDOCS_CLIENT_SECRET="synthetic-secret",
)
def test_cliente_oculta_detalhes_da_falha_de_transporte():
    class SessaoComFalha(SessaoSimulada):
        def post(self, url, **kwargs):
            raise requests.ConnectionError("secret in provider response")

    client = ClienteEdocs(sessao=SessaoComFalha())

    with pytest.raises(ErroRequisicaoEdocs) as erro:
        client.listar_patriarcas()

    assert "secret in provider response" not in str(erro.value)
