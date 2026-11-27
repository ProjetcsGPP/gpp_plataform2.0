"""Ações PNGI falha fechada quando o IAM remoto é o guard de HTTP."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.acoes_pngi.models import VigenciaPNGI
from common.services.cliente_iam import (
    IAMIndisponivel, PermissaoIAMNegada, SessaoIAMInvalida,
)
from config.iam_boundary import acoes_http_iam_remoto, dominio_http_iam_remoto


pytestmark = pytest.mark.django_db
CONFIGURACAO = {
    "ACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA": True,
    "IAM_URL_ACOES": "http://127.0.0.1:8000/interno/iam/v1/decisoes-acoes/",
    "IAM_TOKEN_SERVICO_ACOES": "credencial-sintetica-acoes-pngi-isolamento",
}
DECISAO = {"usuario_id": 17, "usuario_nome": "Gestora PNGI", "decisao_id": "teste"}
COOKIE = "gpp_session_ACOES_PNGI"


def _cliente(*, cookie=True, csrf=False):
    cliente = Client(enforce_csrf_checks=csrf)
    if cookie:
        cliente.cookies[COOKIE] = "sessao-sintetica-acoes"
    return cliente


@pytest.mark.parametrize(
    ("caminho", "esperado"),
    [
        ("/api/acoes-pngi/eixos/", True),
        ("/api/acoes-pngi/acoes/", True),
        ("/api/carga-org-lot/acoes/", False),
        ("/api/pub-institucional/acoes/", False),
        ("/api/public/v1/publicacoes-institucionais/vigente/", False),
    ],
)
@override_settings(**CONFIGURACAO)
def test_fronteira_remota_so_para_acoes(caminho, esperado):
    assert acoes_http_iam_remoto(caminho) is esperado
    assert (dominio_http_iam_remoto(caminho) == "ACOES_PNGI") is esperado


@override_settings(**CONFIGURACAO)
def test_somente_cookie_proprio_autoriza_decisao():
    cliente = _cliente(cookie=False)
    cliente.cookies["gpp_session_PORTAL"] = "sessao-de-outra-aplicacao"
    with patch("apps.acoes_pngi.permissoes_iam.decidir_acesso_remoto") as remoto:
        resposta = cliente.get("/api/acoes-pngi/eixos/")
    assert resposta.status_code == 401
    assert resposta.json()["errors"]["code"] == "session_invalid"
    remoto.assert_not_called()


@pytest.mark.parametrize(
    ("erro", "status", "codigo"),
    [
        (SessaoIAMInvalida, 401, "session_invalid"),
        (PermissaoIAMNegada, 403, "permission_denied"),
        (IAMIndisponivel, 503, "servico_iam_indisponivel"),
    ],
)
@override_settings(**CONFIGURACAO)
def test_decisao_iam_falha_fechada(erro, status, codigo):
    with patch(
        "apps.acoes_pngi.permissoes_iam.decidir_acesso_remoto",
        side_effect=erro(),
    ):
        resposta = _cliente().get("/api/acoes-pngi/eixos/")
    assert resposta.status_code == status
    assert resposta.json()["errors"]["code"] == codigo


@override_settings(**CONFIGURACAO)
def test_iam_indisponivel_nao_cria_vigencia():
    quantidade = VigenciaPNGI.objects.count()
    with patch(
        "apps.acoes_pngi.permissoes_iam.decidir_acesso_remoto",
        side_effect=IAMIndisponivel(),
    ):
        resposta = _cliente().post(
            "/api/acoes-pngi/vigencias/", data={}, content_type="application/json"
        )
    assert resposta.status_code == 503
    assert VigenciaPNGI.objects.count() == quantidade


@override_settings(**CONFIGURACAO)
def test_decisao_valida_nao_consulta_sessao_local():
    with patch(
        "apps.acoes_pngi.permissoes_iam.decidir_acesso_remoto", return_value=DECISAO
    ) as remoto, patch(
        "apps.accounts.middleware.AccountsSession.objects.filter",
        side_effect=AssertionError("sessão local consultada"),
    ):
        resposta = _cliente().get("/api/acoes-pngi/eixos/")
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), dict)
    assert remoto.call_args.kwargs["nome_cookie"] == COOKIE
    assert remoto.call_args.kwargs["permissao"] == "view_eixo"


@override_settings(**CONFIGURACAO)
def test_mutacao_autorizada_ainda_exige_csrf():
    quantidade = VigenciaPNGI.objects.count()
    with patch(
        "apps.acoes_pngi.permissoes_iam.decidir_acesso_remoto", return_value=DECISAO
    ):
        resposta = _cliente(csrf=True).post(
            "/api/acoes-pngi/vigencias/", data={}, content_type="application/json"
        )
    assert resposta.status_code == PermissionDenied.status_code
    assert VigenciaPNGI.objects.count() == quantidade


def _postar_no_iam(url, **opcoes):
    assert url == CONFIGURACAO["IAM_URL_ACOES"]
    assert opcoes["timeout"] == (1, 2)
    assert opcoes["allow_redirects"] is False
    resposta = Client().post(
        "/interno/iam/v1/decisoes-acoes/",
        data=opcoes["json"],
        content_type="application/json",
        HTTP_AUTHORIZATION=opcoes["headers"]["Authorization"],
        HTTP_X_CORRELATION_ID=opcoes["headers"]["X-Correlation-ID"],
    )
    return SimpleNamespace(status_code=resposta.status_code, json=resposta.json)


@override_settings(**{**CONFIGURACAO, "IAM_DECISOES_ACOES_ATIVAS": True})
def test_cliente_e_produtor_iam_concordam_sobre_autorizacao_e_revogacao():
    autorizado = {
        "resultado": "AUTORIZADO", "usuario_id": 17,
        "usuario_nome": "Gestora PNGI", "versao_autorizacao": 4,
        "expira_em": (timezone.now() + timedelta(minutes=5)).isoformat(),
    }
    with patch(
        "common.services.cliente_iam.requests.post", side_effect=_postar_no_iam
    ), patch(
        "apps.accounts.views_internas.decidir_acesso_acoes",
        return_value=autorizado,
    ) as decidir:
        assert _cliente().get("/api/acoes-pngi/eixos/").status_code == 200
        decidir.return_value = {"resultado": "NEGADO", "usuario_id": 17}
        assert _cliente().get("/api/acoes-pngi/eixos/").status_code == 403
    assert decidir.call_count == 2


@override_settings(**{**CONFIGURACAO, "IAM_DECISOES_ACOES_ATIVAS": False})
def test_produtor_desligado_falha_fechado_no_consumidor():
    with patch(
        "common.services.cliente_iam.requests.post", side_effect=_postar_no_iam
    ):
        resposta = _cliente().get("/api/acoes-pngi/eixos/")
    assert resposta.status_code == 503
    assert resposta.json()["errors"]["code"] == "servico_iam_indisponivel"
