"""Contrato M2M de decisão IAM: não usa o banco real nem credenciais reais."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client, override_settings

from apps.accounts.services.decisao_interna import decidir_acesso_carga

CAMINHO = "/interno/iam/v1/decisoes/"
CORPO = {
    "acao": "view_importacaoplanilha",
    "credenciais_usuario": [{
        "nome_cookie": "gpp_session_CARGA_ORG_LOT",
        "valor": "sessao-opaca-de-teste",
    }],
}
CONFIGURACAO_PILOTO = {
    "IAM_DECISOES_INTERNAS_ATIVAS": True,
    "IAM_TOKEN_SERVICO_CARGA": "credencial-m2m-de-teste-com-mais-de-32-caracteres",
}


def _postar(corpo=None, *, token="credencial-m2m-de-teste-com-mais-de-32-caracteres"):
    return Client().post(
        CAMINHO,
        data=CORPO if corpo is None else corpo,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


@override_settings(IAM_DECISOES_INTERNAS_ATIVAS=False)
def test_endpoint_desativado_por_padrao_nao_consulta_iam():
    with patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir:
        resposta = _postar()
    assert resposta.status_code == 404
    decidir.assert_not_called()


@override_settings(IAM_DECISOES_INTERNAS_ATIVAS=True, IAM_TOKEN_SERVICO_CARGA="fraca")
def test_endpoint_recusa_configuracao_com_credencial_curta():
    resposta = _postar(token="fraca")
    assert resposta.status_code == 404


@override_settings(IAM_DECISOES_INTERNAS_ATIVAS=True, IAM_TOKEN_SERVICO_CARGA="x" * 257)
def test_endpoint_recusa_configuracao_com_credencial_longa():
    with patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir:
        resposta = _postar(token="x" * 257)
    assert resposta.status_code == 404
    decidir.assert_not_called()


@override_settings(**CONFIGURACAO_PILOTO)
def test_credencial_de_servico_invalida_nao_consulta_sessao():
    with patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir:
        resposta = _postar(token="invalida")
    assert resposta.status_code == 401
    assert resposta["WWW-Authenticate"].startswith("Bearer")
    decidir.assert_not_called()


@override_settings(**CONFIGURACAO_PILOTO)
@pytest.mark.parametrize(
    "corpo",
    [
        {"acao": "view_importacaoplanilha", "credenciais_usuario": []},
        {"acao": "../admin", "credenciais_usuario": CORPO["credenciais_usuario"]},
        {"acao": "view_importacaoplanilha", "credenciais_usuario": CORPO["credenciais_usuario"] * 2},
        {"acao": "view_importacaoplanilha", "credenciais_usuario": CORPO["credenciais_usuario"] * 9},
        {"acao": "view_importacaoplanilha", "credenciais_usuario": [{"nome_cookie": "outro", "valor": "abc"}]},
        {"acao": "view_importacaoplanilha", "credenciais_usuario": [{"nome_cookie": "gpp_session_PORTAL", "valor": ""}]},
        {"acao": "view_importacaoplanilha", "credenciais_usuario": [{"nome_cookie": "gpp_session_PORTAL", "valor": "x", "extra": 1}]},
        {"acao": "View_importacaoplanilha", "credenciais_usuario": CORPO["credenciais_usuario"]},
        [CORPO],
    ],
)
def test_contrato_rejeita_entrada_invalida(corpo):
    with patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir:
        resposta = _postar(corpo)
    assert resposta.status_code == 400
    decidir.assert_not_called()


@override_settings(**CONFIGURACAO_PILOTO)
def test_autenticacao_m2m_precede_validacao_do_corpo():
    with patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir:
        resposta = _postar({"corpo": "invalido"}, token="incorreto")
    assert resposta.status_code == 401
    decidir.assert_not_called()


@override_settings(**CONFIGURACAO_PILOTO)
def test_corpo_acima_de_4k_e_rejeitado_sem_consulta():
    with patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir:
        resposta = Client().post(
            CAMINHO,
            data={"acao": "x" * 4100, "credenciais_usuario": CORPO["credenciais_usuario"]},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {CONFIGURACAO_PILOTO['IAM_TOKEN_SERVICO_CARGA']}",
        )
    assert resposta.status_code == 413
    decidir.assert_not_called()


@override_settings(**CONFIGURACAO_PILOTO)
def test_tipo_de_conteudo_invalido_e_rejeitado_sem_consulta():
    with patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir:
        resposta = Client().post(
            CAMINHO,
            data="acao=view_importacaoplanilha",
            content_type="application/x-www-form-urlencoded",
            HTTP_AUTHORIZATION=f"Bearer {CONFIGURACAO_PILOTO['IAM_TOKEN_SERVICO_CARGA']}",
        )
    assert resposta.status_code == 415
    decidir.assert_not_called()


@override_settings(**CONFIGURACAO_PILOTO)
def test_json_malformado_e_rejeitado_sem_consulta():
    with patch("apps.accounts.views_internas.decidir_acesso_carga") as decidir:
        resposta = Client().post(
            CAMINHO,
            data="{json-invalido",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {CONFIGURACAO_PILOTO['IAM_TOKEN_SERVICO_CARGA']}",
        )
    assert resposta.status_code == 400
    decidir.assert_not_called()


@override_settings(**CONFIGURACAO_PILOTO)
@pytest.mark.parametrize(
    "resultado",
    ["AUTORIZADO", "NEGADO", "SESSAO_INVALIDA"],
)
def test_resultado_explicito_nao_envia_sessao_ao_chamador(resultado):
    with patch(
        "apps.accounts.views_internas.decidir_acesso_carga",
        return_value={"resultado": resultado},
    ) as decidir:
        resposta = _postar()
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == resultado
    assert resposta.json()["versao"] == 1
    assert "sessao-opaca-de-teste" not in resposta.content.decode()
    assert resposta["Cache-Control"] == "no-store"
    decidir.assert_called_once_with(
        credenciais={"gpp_session_CARGA_ORG_LOT": "sessao-opaca-de-teste"},
        permissao="view_importacaoplanilha",
    )


@override_settings(**CONFIGURACAO_PILOTO)
def test_falha_do_iam_nao_se_torna_autorizacao(caplog):
    with patch(
        "apps.accounts.views_internas.decidir_acesso_carga",
        side_effect=RuntimeError("falha simulada"),
    ):
        resposta = _postar()
    assert resposta.status_code == 503
    assert resposta.json()["erro"] == "iam_indisponivel"
    assert "falha simulada" not in resposta.content.decode()
    assert "sessao-opaca-de-teste" not in caplog.text
    assert CONFIGURACAO_PILOTO["IAM_TOKEN_SERVICO_CARGA"] not in caplog.text


def test_sessao_nao_encontrada_nao_consulta_permissoes():
    with (
        patch("apps.accounts.services.decisao_interna.AccountsSession") as sessoes,
        patch("apps.accounts.services.decisao_interna.AuthorizationService") as autorizador,
    ):
        sessoes.objects.filter.return_value.select_related.return_value.first.return_value = None
        resultado = decidir_acesso_carga(
            credenciais={"gpp_session_CARGA_ORG_LOT": "sessao-invalida"},
            permissao="view_importacaoplanilha",
        )
    assert resultado == {"resultado": "SESSAO_INVALIDA"}
    autorizador.assert_not_called()
    _, filtros = sessoes.objects.filter.call_args
    assert filtros["revoked"] is False
    assert filtros["user__is_active"] is True
    assert filtros["app_context"] == "CARGA_ORG_LOT"


def test_cookie_de_outra_aplicacao_exige_portal_admin():
    usuario = SimpleNamespace(pk=7, is_superuser=False)
    sessao = SimpleNamespace(user=usuario)
    with (
        patch("apps.accounts.services.decisao_interna.AccountsSession") as sessoes,
        patch("apps.accounts.services.decisao_interna.UserRole") as roles,
        patch("apps.accounts.services.decisao_interna.AuthorizationService") as autorizador,
    ):
        sessoes.objects.filter.return_value.select_related.return_value.order_by.return_value.first.return_value = sessao
        roles.objects.filter.return_value.exists.return_value = False
        resultado = decidir_acesso_carga(
            credenciais={"gpp_session_PORTAL": "sessao-portal"},
            permissao="view_importacaoplanilha",
        )
    assert resultado == {"resultado": "SESSAO_INVALIDA"}
    autorizador.assert_not_called()


def test_portal_admin_ainda_passa_pela_decisao_final():
    usuario = SimpleNamespace(pk=7, is_superuser=False)
    sessao = SimpleNamespace(user=usuario, expires_at=SimpleNamespace(isoformat=lambda: "fim"))
    with (
        patch("apps.accounts.services.decisao_interna.AccountsSession") as sessoes,
        patch("apps.accounts.services.decisao_interna.UserRole") as roles,
        patch("apps.accounts.services.decisao_interna.ApplicationRegistry") as registro,
        patch("apps.accounts.services.decisao_interna.AuthorizationService") as autorizador,
    ):
        sessoes.objects.filter.return_value.select_related.return_value.order_by.return_value.first.return_value = sessao
        roles.objects.filter.return_value.exists.return_value = True
        autorizador.return_value.can.return_value = False
        resultado = decidir_acesso_carga(
            credenciais={"gpp_session_PORTAL": "sessao-portal"},
            permissao="view_importacaoplanilha",
        )
    assert resultado == {"resultado": "NEGADO", "usuario_id": 7}
    registro.return_value.get.assert_called_once_with("CARGA_ORG_LOT")
    autorizador.return_value.can.assert_called_once_with("view_importacaoplanilha")


def test_sessao_carga_autorizada_retorna_identidade_minima_e_versao():
    usuario = SimpleNamespace(
        pk=7, is_superuser=False,
        get_full_name=lambda: "Nome de Teste",
        get_username=lambda: "usuario_teste",
    )
    sessao = SimpleNamespace(user=usuario, expires_at=SimpleNamespace(isoformat=lambda: "fim"))
    with (
        patch("apps.accounts.services.decisao_interna.AccountsSession") as sessoes,
        patch("apps.accounts.services.decisao_interna.UserRole") as roles,
        patch("apps.accounts.services.decisao_interna.ApplicationRegistry") as registro,
        patch("apps.accounts.services.decisao_interna.AuthorizationService") as autorizador,
        patch("apps.accounts.services.decisao_interna.UserAuthzState") as versoes,
    ):
        sessoes.objects.filter.return_value.select_related.return_value.first.return_value = sessao
        autorizador.return_value.can.return_value = True
        versoes.objects.filter.return_value.values_list.return_value.first.return_value = 4
        resultado = decidir_acesso_carga(
            credenciais={"gpp_session_CARGA_ORG_LOT": "sessao-carga"},
            permissao="view_importacaoplanilha",
        )
    assert resultado == {
        "resultado": "AUTORIZADO",
        "usuario_id": 7,
        "usuario_nome": "Nome de Teste",
        "versao_autorizacao": 4,
        "expira_em": "fim",
    }
    roles.objects.filter.assert_not_called()
    registro.return_value.get.assert_called_once_with("CARGA_ORG_LOT")


@pytest.mark.parametrize("nome", ["", "Nome\nforjado", "N" * 201])
def test_nome_iam_invalido_nao_produz_decisao_autorizada(nome):
    usuario = SimpleNamespace(
        pk=7, is_superuser=False,
        get_full_name=lambda: nome,
        get_username=lambda: nome,
    )
    sessao = SimpleNamespace(user=usuario)
    with (
        patch("apps.accounts.services.decisao_interna.AccountsSession") as sessoes,
        patch("apps.accounts.services.decisao_interna.ApplicationRegistry"),
        patch("apps.accounts.services.decisao_interna.AuthorizationService") as autorizador,
    ):
        sessoes.objects.filter.return_value.select_related.return_value.first.return_value = sessao
        autorizador.return_value.can.return_value = True
        with pytest.raises(ValueError, match="Nome do usuário inválido"):
            decidir_acesso_carga(
                credenciais={"gpp_session_CARGA_ORG_LOT": "sessao-carga"},
                permissao="view_importacaoplanilha",
            )


def test_cookie_dedicado_invalido_nao_tenta_fallback():
    with patch("apps.accounts.services.decisao_interna.AccountsSession") as sessoes:
        sessoes.objects.filter.return_value.select_related.return_value.first.return_value = None
        resultado = decidir_acesso_carga(
            credenciais={
                "gpp_session_CARGA_ORG_LOT": "invalida",
                "gpp_session_PORTAL": "valida",
            },
            permissao="view_importacaoplanilha",
        )
    assert resultado == {"resultado": "SESSAO_INVALIDA"}
    sessoes.objects.filter.return_value.select_related.return_value.order_by.assert_not_called()


def test_fallback_usa_sessao_mais_recente_entre_cookies_validos():
    usuario = SimpleNamespace(
        pk=7, is_superuser=False,
        get_full_name=lambda: "",
        get_username=lambda: "usuario_teste",
    )
    sessao = SimpleNamespace(user=usuario, expires_at=SimpleNamespace(isoformat=lambda: "fim"))
    with (
        patch("apps.accounts.services.decisao_interna.AccountsSession") as sessoes,
        patch("apps.accounts.services.decisao_interna.UserRole") as roles,
        patch("apps.accounts.services.decisao_interna.ApplicationRegistry") as registro,
        patch("apps.accounts.services.decisao_interna.AuthorizationService") as autorizador,
        patch("apps.accounts.services.decisao_interna.UserAuthzState") as versoes,
    ):
        consulta = sessoes.objects.filter.return_value.select_related.return_value
        consulta.order_by.return_value.first.return_value = sessao
        roles.objects.filter.return_value.exists.return_value = True
        autorizador.return_value.can.return_value = True
        versoes.objects.filter.return_value.values_list.return_value.first.return_value = 4
        resultado = decidir_acesso_carga(
            credenciais={"gpp_session_PORTAL": "portal", "gpp_session_ACOES_PNGI": "acoes"},
            permissao="view_importacaoplanilha",
        )
    assert resultado["resultado"] == "AUTORIZADO"
    assert resultado["usuario_nome"] == "usuario_teste"
    consulta.order_by.assert_called_once_with("-created_at")
    registro.return_value.get.assert_called_once_with("CARGA_ORG_LOT")
