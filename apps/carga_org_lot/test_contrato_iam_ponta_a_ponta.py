"""Contrato cliente Carga ↔ endpoint IAM sem rede nem banco reais."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from apps.carga_org_lot.services.cliente_iam import (IAMIndisponivel,
                                                     PermissaoIAMNegada,
                                                     SessaoIAMInvalida,
                                                     decidir_acesso_remoto)

SEGREDO_TESTE = "credencial-sintetica-para-contrato-iam-123456"
CONFIGURACAO = {
    "IAM_DECISOES_INTERNAS_ATIVAS": True,
    "IAM_TOKEN_SERVICO_CARGA": SEGREDO_TESTE,
    "IAM_URL_CARGA": "http://127.0.0.1:8000/interno/iam/v1/decisoes/",
}
CREDENCIAIS = {
    "gpp_session_CARGA_ORG_LOT": "sessao-carga-sintetica",
}


def _postar_no_django(url, **opcoes):
    """Adapta requests.post ao Client sem expor a sessão ao transporte real."""
    assert url == CONFIGURACAO["IAM_URL_CARGA"]
    assert opcoes["timeout"] == (1, 2)
    assert opcoes["allow_redirects"] is False
    resposta = Client().post(
        "/interno/iam/v1/decisoes/",
        data=opcoes["json"],
        content_type="application/json",
        HTTP_AUTHORIZATION=opcoes["headers"]["Authorization"],
        HTTP_X_CORRELATION_ID=opcoes["headers"]["X-Correlation-ID"],
    )

    class Resposta:
        status_code = resposta.status_code

        @staticmethod
        def json():
            return resposta.json()

    return Resposta()


@override_settings(**CONFIGURACAO)
@pytest.mark.parametrize(
    ("resultado", "erro"),
    [
        ("AUTORIZADO", None),
        ("NEGADO", PermissaoIAMNegada),
        ("SESSAO_INVALIDA", SessaoIAMInvalida),
    ],
)
def test_cliente_e_endpoint_concordam_sobre_decisao(resultado, erro):
    dados = {"resultado": resultado}
    if resultado != "SESSAO_INVALIDA":
        dados["usuario_id"] = 7
    if resultado == "AUTORIZADO":
        dados.update(
            usuario_nome="Nome de Teste",
            versao_autorizacao=4,
            expira_em=(timezone.now() + timedelta(minutes=5)).isoformat(),
        )
    with (
        patch("apps.carga_org_lot.services.cliente_iam.requests.post", side_effect=_postar_no_django),
        patch("apps.accounts.views_internas.decidir_acesso_carga", return_value=dados) as decidir,
    ):
        if erro:
            with pytest.raises(erro):
                decidir_acesso_remoto(
                    credenciais=CREDENCIAIS, permissao="view_importacaoplanilha"
                )
        else:
            decisao = decidir_acesso_remoto(
                credenciais=CREDENCIAIS, permissao="view_importacaoplanilha"
            )
            assert decisao["usuario_id"] == 7
            assert decisao["usuario_nome"] == "Nome de Teste"
    decidir.assert_called_once_with(
        credenciais=CREDENCIAIS,
        permissao="view_importacaoplanilha",
    )


@override_settings(**{**CONFIGURACAO, "IAM_DECISOES_INTERNAS_ATIVAS": False})
def test_endpoint_desligado_e_falha_de_canal_nao_autorizam():
    with (
        patch("apps.carga_org_lot.services.cliente_iam.requests.post", side_effect=_postar_no_django),
        patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir,
    ):
        with pytest.raises(IAMIndisponivel):
            decidir_acesso_remoto(
                credenciais=CREDENCIAIS, permissao="view_importacaoplanilha"
            )
    decidir.assert_not_called()
