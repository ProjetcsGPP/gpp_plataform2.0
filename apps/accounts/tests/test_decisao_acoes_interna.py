"""Contrato produtor IAM de Ações PNGI, opt-in e isolado por credencial."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import Resolver404, resolve
from django.utils import timezone

from apps.accounts.models import AccountsSession
from apps.accounts.services.decisao_interna import decidir_acesso_acoes


CAMINHO = "/interno/iam/v1/decisoes-acoes/"
TOKEN_ACOES = "credencial-sintetica-acoes-pngi-isolamento"
TOKEN_CARGA = "credencial-sintetica-carga-isolamento"
TOKEN_PUBLICACOES = "credencial-sintetica-publicacoes-isolamento"
CONFIGURACAO = {
    "IAM_DECISOES_ACOES_ATIVAS": True,
    "IAM_TOKEN_SERVICO_ACOES": TOKEN_ACOES,
    "IAM_TOKEN_SERVICO_CARGA": TOKEN_CARGA,
    "IAM_TOKEN_SERVICO_PUBLICACOES": TOKEN_PUBLICACOES,
}


def _postar(*, token=TOKEN_ACOES, cookie="gpp_session_ACOES_PNGI"):
    return Client().post(
        CAMINHO,
        data={
            "acao": "view_acoes",
            "credenciais_usuario": [
                {"nome_cookie": cookie, "valor": "sessao-sintetica-acoes"},
            ],
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def test_rota_existe_so_no_iam():
    for urlconf in (
        "config.urls", "config.urls_plataforma_piloto",
        "config.urls_plataforma_separada_piloto",
    ):
        resolve(CAMINHO, urlconf=urlconf)
    for urlconf in ("config.urls_carga_piloto", "config.urls_publicacoes_piloto"):
        with pytest.raises(Resolver404):
            resolve(CAMINHO, urlconf=urlconf)


@override_settings(**{**CONFIGURACAO, "IAM_DECISOES_ACOES_ATIVAS": False})
def test_desligado_por_padrao_nao_decide():
    with patch("apps.accounts.views_internas.decidir_acesso_acoes") as decidir:
        resposta = _postar()
    assert resposta.status_code == 404
    decidir.assert_not_called()


@override_settings(**CONFIGURACAO)
def test_credencial_de_outro_servico_nao_decide():
    for token in (TOKEN_CARGA, TOKEN_PUBLICACOES):
        assert _postar(token=token).status_code == 401


@pytest.mark.parametrize("outro", [TOKEN_CARGA, TOKEN_PUBLICACOES])
def test_credencial_compartilhada_desabilita_contrato(outro):
    with override_settings(**{**CONFIGURACAO, "IAM_TOKEN_SERVICO_ACOES": outro}):
        assert _postar(token=outro).status_code == 404


@override_settings(**CONFIGURACAO)
def test_produtor_fixa_dominio_e_nao_consulta_outro_servico():
    resultado = {
        "resultado": "AUTORIZADO", "usuario_id": 42,
        "usuario_nome": "Gestor de Ações", "versao_autorizacao": 1,
        "expira_em": (timezone.now() + timedelta(hours=1)).isoformat(),
    }
    with patch(
        "apps.accounts.views_internas.decidir_acesso_acoes", return_value=resultado
    ) as decidir:
        resposta = _postar()
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "AUTORIZADO"
    assert resposta.json()["versao"] == 1
    assert resposta["Cache-Control"] == "no-store"
    decidir.assert_called_once_with(
        credenciais={"gpp_session_ACOES_PNGI": "sessao-sintetica-acoes"},
        permissao="view_acoes",
    )


@pytest.mark.django_db
def test_decisao_rejeita_cookie_de_outra_aplicacao():
    usuario = User.objects.create_user(username="acoes_isolamento")
    AccountsSession.objects.create(
        user=usuario,
        session_key="sessao-sintetica-acoes",
        session_cookie_name="gpp_session_PORTAL",
        app_context="PORTAL",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    resultado = decidir_acesso_acoes(
        credenciais={"gpp_session_PORTAL": "sessao-sintetica-acoes"},
        permissao="view_acoes",
    )
    assert resultado == {"resultado": "SESSAO_INVALIDA"}


@pytest.mark.django_db
@override_settings(**CONFIGURACAO)
def test_sessao_propria_autoriza_e_revogacao_impede_nova_decisao():
    usuario = User.objects.create_user(
        username="gestor_acoes_iam", first_name="Gestor", last_name="PNGI"
    )
    sessao = AccountsSession.objects.create(
        user=usuario,
        session_key="sessao-sintetica-acoes",
        session_cookie_name="gpp_session_ACOES_PNGI",
        app_context="ACOES_PNGI",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    with patch(
        "apps.accounts.services.decisao_interna.ApplicationRegistry.get",
        return_value=object(),
    ) as aplicacao, patch(
        "apps.accounts.services.decisao_interna.AuthorizationService"
    ) as autorizacao:
        autorizacao.return_value.can.return_value = True
        assert _postar().json()["resultado"] == "AUTORIZADO"
        aplicacao.assert_called_with("ACOES_PNGI")
        autorizacao.return_value.can.assert_called_with("view_acoes")

        sessao.revoked = True
        sessao.save(update_fields=["revoked"])
        assert _postar().json()["resultado"] == "SESSAO_INVALIDA"
