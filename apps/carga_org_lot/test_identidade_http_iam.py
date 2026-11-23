"""Regressão da fronteira HTTP remota de Carga pelo pipeline Django/DRF."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient

from apps.carga_org_lot.services.cliente_iam import (
    IAMIndisponivel, PermissaoIAMNegada, SessaoIAMInvalida,
)
from apps.carga_org_lot.permissoes_iam import CanPermissionCarga
from apps.carga_org_lot.urls import router
from apps.carga_org_lot.views.dashboard import DashboardCargaOrgLotView
from apps.core.middleware.authorization import AuthorizationMiddleware
from config.iam_boundary import carga_http_iam_remoto

pytestmark = pytest.mark.django_db

CONFIGURACAO_REMOTA = {
    "CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA": True,
    "CARGA_IAM_DECISAO_REMOTA_ATIVA": False,
}
DECISAO = {
    "usuario_id": 7,
    "usuario_nome": "Gestora de Teste",
    "decisao_id": "decisao-teste",
}
CAMINHO = "/api/carga-org-lot/dashboard/"


def _cliente(*, csrf=False, cookie=True):
    cliente = APIClient(enforce_csrf_checks=csrf)
    if cookie:
        cliente.cookies["gpp_session_CARGA_ORG_LOT"] = "sessao-sintetica"
    return cliente


@override_settings(**CONFIGURACAO_REMOTA)
def test_decisao_remota_autentica_sem_consultar_iam_local():
    def responder(_view, request):
        return Response({
            "usuario_id": request.user.pk,
            "usuario_nome": request.user.get_full_name(),
        })

    with (
        patch("apps.accounts.middleware.AccountsSession.objects.filter") as sessoes,
        patch("apps.core.middleware.role_context.UserRole.objects.filter") as roles,
        patch("apps.core.middleware.application_context.ApplicationRegistry.get") as aplicacoes,
        patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto", return_value=DECISAO) as iam,
        patch.object(DashboardCargaOrgLotView, "get", responder),
    ):
        resposta = _cliente().get(CAMINHO, HTTP_X_APPLICATION_CODE="PORTAL")

    assert resposta.status_code == 200
    assert resposta.json() == {"usuario_id": 7, "usuario_nome": "Gestora de Teste"}
    sessoes.assert_not_called()
    roles.assert_not_called()
    aplicacoes.assert_not_called()
    iam.assert_called_once_with(
        credenciais={"gpp_session_CARGA_ORG_LOT": "sessao-sintetica"},
        permissao="view_importacaoplanilha",
        correlacao=None,
    )


@override_settings(**CONFIGURACAO_REMOTA)
@pytest.mark.parametrize(
    ("erro", "status", "codigo"),
    [
        (SessaoIAMInvalida, 401, "session_invalid"),
        (PermissaoIAMNegada, 403, "permission_denied"),
        (IAMIndisponivel, 503, "servico_iam_indisponivel"),
    ],
)
def test_falha_remota_nao_executa_dominio(erro, status, codigo):
    with (
        patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto", side_effect=erro()),
        patch.object(DashboardCargaOrgLotView, "get") as dominio,
    ):
        resposta = _cliente().get(CAMINHO)
    assert resposta.status_code == status
    assert resposta.json()["errors"]["code"] == codigo
    dominio.assert_not_called()


@override_settings(**CONFIGURACAO_REMOTA)
def test_sem_cookie_nao_chama_iam_nem_dominio():
    with (
        patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto") as iam,
        patch.object(DashboardCargaOrgLotView, "get") as dominio,
    ):
        resposta = _cliente(cookie=False).get(CAMINHO)
    assert resposta.status_code == 401
    iam.assert_not_called()
    dominio.assert_not_called()


@override_settings(**CONFIGURACAO_REMOTA)
@pytest.mark.parametrize("nome", [None, "", "Nome\nforjado", "N" * 201])
def test_identidade_incompleta_falha_fechada(nome):
    with (
        patch(
            "apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto",
            return_value={**DECISAO, "usuario_nome": nome},
        ),
        patch.object(DashboardCargaOrgLotView, "get") as dominio,
    ):
        resposta = _cliente().get(CAMINHO)
    assert resposta.status_code == 503
    assert resposta.json()["errors"]["code"] == "servico_iam_indisponivel"
    dominio.assert_not_called()


@override_settings(**CONFIGURACAO_REMOTA)
def test_carga_sem_guard_e_bloqueada_antes_da_view():
    requisicao = SimpleNamespace(path="/api/carga-org-lot/rota-nova/", method="GET")
    resposta = AuthorizationMiddleware.process_view(
        requisicao, lambda _request: None, (), {}
    )
    assert resposta.status_code == 503
    assert json.loads(resposta.content)["errors"]["code"] == "servico_iam_indisponivel"


@override_settings(**CONFIGURACAO_REMOTA)
@pytest.mark.parametrize(
    ("caminho", "esperado"),
    [
        ("/api/carga-org-lot/dashboard/", True),
        ("/api/carga-org-lot-malicioso/dashboard/", False),
        ("/api/portal/dashboard/", False),
        ("/api/pub-institucional/publicacoes/", False),
        ("/api/public/v1/publicacoes-institucionais/vigente/", False),
        ("/interno/iam/v1/decisoes/", False),
    ],
)
def test_flag_remota_so_alcanca_prefixo_de_carga(caminho, esperado):
    assert carga_http_iam_remoto(caminho) is esperado


@override_settings(**CONFIGURACAO_REMOTA)
def test_todas_as_views_de_carga_executam_apenas_o_guard_remoto():
    for _, classe, _ in router.registry:
        visao = classe()
        visao.request = SimpleNamespace(path=CAMINHO)
        visao.action = "list"
        permissoes = visao.get_permissions()
        assert len(permissoes) == 1, classe.__name__
        assert isinstance(permissoes[0], CanPermissionCarga), classe.__name__

    dashboard = DashboardCargaOrgLotView()
    dashboard.request = SimpleNamespace(path=CAMINHO)
    permissoes = dashboard.get_permissions()
    assert len(permissoes) == 1
    assert isinstance(permissoes[0], CanPermissionCarga)


@override_settings(**CONFIGURACAO_REMOTA)
def test_publicacoes_publicas_nao_dependem_do_iam_apesar_do_cookie():
    with (
        patch("apps.accounts.middleware.AccountsSession.objects.filter") as sessoes,
        patch("apps.core.middleware.role_context.UserRole.objects.filter") as roles,
        patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto") as iam,
    ):
        resposta = _cliente().get(
            "/api/public/v1/publicacoes-institucionais/vigente/"
        )
    assert resposta.status_code == 404
    assert resposta.json()["codigo"] == "PUBLICACAO_NAO_DISPONIVEL"
    sessoes.assert_not_called()
    roles.assert_not_called()
    iam.assert_not_called()


@override_settings(**CONFIGURACAO_REMOTA)
def test_csrf_de_escrita_permanece_obrigatorio():
    caminho = "/api/carga-org-lot/patriarcas/"
    with patch(
        "apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto",
        return_value={**DECISAO, "decisao_id": "escrita"},
    ) as iam:
        resposta = _cliente(csrf=True).post(caminho, data={}, format="json")
    assert resposta.status_code == 403
    assert "CSRF" in str(resposta.data)
    iam.assert_called_once()


@override_settings(**CONFIGURACAO_REMOTA)
def test_csrf_valido_permite_chegar_ao_dominio_com_ator_iam():
    from apps.carga_org_lot.views.catalogs import PatriarcaViewSet

    caminho = "/api/carga-org-lot/patriarcas/"
    cliente = _cliente(csrf=True)
    cliente.cookies["csrftoken"] = "A" * 32

    def responder(_view, request, *_args, **_kwargs):
        return Response({"usuario_id": request.user.pk, "nome": request.user.username})

    with (
        patch(
            "apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto",
            return_value=DECISAO,
        ) as iam,
        patch.object(PatriarcaViewSet, "create", responder),
    ):
        resposta = cliente.post(
            caminho, data={}, format="json", HTTP_X_CSRFTOKEN="A" * 32,
        )
    assert resposta.status_code == 200
    assert resposta.json() == {"usuario_id": 7, "nome": "Gestora de Teste"}
    assert iam.call_args.kwargs["permissao"] == "add_patriarca"
