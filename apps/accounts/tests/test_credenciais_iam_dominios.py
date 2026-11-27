"""Paridade das credenciais internas de Carga, Publicações e Ações."""

import pytest
from django.test import Client, override_settings


TOKENS = {
    "CARGA": "credencial-carga-exclusiva-de-teste-2026",
    "PUBLICACOES": "credencial-publicacoes-exclusiva-de-teste-2026",
    "ACOES": "credencial-acoes-exclusiva-de-teste-2026",
}
CONFIGURACAO = {
    "IAM_DECISOES_INTERNAS_ATIVAS": True,
    "IAM_DECISOES_PUBLICACOES_ATIVAS": True,
    "IAM_DECISOES_ACOES_ATIVAS": True,
    "IAM_TOKEN_SERVICO_CARGA": TOKENS["CARGA"],
    "IAM_TOKEN_SERVICO_PUBLICACOES": TOKENS["PUBLICACOES"],
    "IAM_TOKEN_SERVICO_ACOES": TOKENS["ACOES"],
}
ROTAS = {
    "CARGA": "/interno/iam/v1/decisoes/",
    "PUBLICACOES": "/interno/iam/v1/decisoes-publicacoes/",
    "ACOES": "/interno/iam/v1/decisoes-acoes/",
}
NOMES_CONFIGURACAO = {
    "CARGA": "IAM_TOKEN_SERVICO_CARGA",
    "PUBLICACOES": "IAM_TOKEN_SERVICO_PUBLICACOES",
    "ACOES": "IAM_TOKEN_SERVICO_ACOES",
}
COOKIES = {
    "CARGA": "gpp_session_CARGA_ORG_LOT",
    "PUBLICACOES": "gpp_session_PUB_INSTITUCIONAL",
    "ACOES": "gpp_session_ACOES_PNGI",
}


def _pedir(destino, token, *, cookie):
    return Client().post(
        ROTAS[destino],
        data={
            "acao": "view_recurso",
            "credenciais_usuario": [
                {"nome_cookie": cookie, "valor": "sessao-sintetica"},
            ],
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


@pytest.mark.parametrize("destino", ROTAS)
def test_contrato_proprio_responde_sem_aceitar_cookie_alheio(destino):
    outro = next(nome for nome in ROTAS if nome != destino)
    with override_settings(**CONFIGURACAO):
        resposta = _pedir(destino, TOKENS[destino], cookie=COOKIES[outro])
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "SESSAO_INVALIDA"


@pytest.mark.parametrize("destino", ROTAS)
def test_tokens_alheios_nao_autenticam_outro_dominio(destino):
    with override_settings(**CONFIGURACAO):
        for outro in ROTAS.keys() - {destino}:
            resposta = _pedir(destino, TOKENS[outro], cookie=COOKIES[destino])
            assert resposta.status_code == 401


@pytest.mark.parametrize(
    ("destino", "outro"),
    [(destino, outro) for destino in ROTAS for outro in ROTAS if destino != outro],
)
def test_token_compartilhado_desliga_ambos_contratos(destino, outro):
    configuracao = {
        **CONFIGURACAO,
        NOMES_CONFIGURACAO[outro]: TOKENS[destino],
    }
    with override_settings(**configuracao):
        for nome in (destino, outro):
            resposta = _pedir(nome, TOKENS[destino], cookie=COOKIES[nome])
            assert resposta.status_code == 404


@pytest.mark.parametrize(
    ("destino", "caminho"),
    [
        ("CARGA", "/interno/iam/v1/decisoes-atividade/"),
        ("PUBLICACOES", "/interno/iam/v1/decisoes-atividade-publicacoes/"),
    ],
)
def test_token_compartilhado_tambem_desliga_decisao_de_atividade(destino, caminho):
    configuracao = {
        **CONFIGURACAO,
        "IAM_TOKEN_SERVICO_ACOES": TOKENS[destino],
    }
    with override_settings(**configuracao):
        resposta = Client().post(
            caminho,
            data={"usuario_id": 1, "acao": "view_recurso"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKENS[destino]}",
        )
    assert resposta.status_code == 404
