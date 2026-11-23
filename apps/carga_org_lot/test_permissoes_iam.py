"""Contrato do piloto HTTP sem rede nem banco."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.carga_org_lot.permissoes_iam import (CanPermissionCarga,
                                               PermissaoCargaNegada,
                                               ServicoIAMIndisponivel,
                                               SessaoCargaInvalida)
from apps.carga_org_lot.services.cliente_iam import (IAMIndisponivel,
                                                     PermissaoIAMNegada,
                                                     SessaoIAMInvalida)
from apps.carga_org_lot.urls import router
from apps.carga_org_lot.views.dashboard import DashboardCargaOrgLotView


def _requisicao(*, usuario_id=7, com_cookie=True):
    requisicao = APIRequestFactory().get(
        "/api/carga-org-lot/dashboard/", HTTP_X_CORRELATION_ID="piloto-123"
    )
    requisicao.user = SimpleNamespace(
        is_authenticated=True, id=usuario_id, pk=usuario_id
    )
    if com_cookie:
        requisicao.COOKIES["gpp_session_CARGA_ORG_LOT"] = "sessao-opaca"
    return requisicao


VISAO = SimpleNamespace(required_permission="view_importacaoplanilha")


def test_todas_as_views_http_de_carga_usam_guard_comum():
    for _, classe, _ in router.registry:
        assert CanPermissionCarga in classe.permission_classes, classe.__name__
    assert CanPermissionCarga in DashboardCargaOrgLotView.permission_classes


@override_settings(CARGA_IAM_DECISAO_REMOTA_ATIVA=False)
def test_padrao_permanece_autorizacao_local():
    with (
        patch("apps.carga_org_lot.permissoes_iam.CanPermission.has_permission", return_value=True) as local,
        patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto") as remoto,
    ):
        assert CanPermissionCarga().has_permission(_requisicao(), VISAO) is True
    local.assert_called_once()
    remoto.assert_not_called()


@override_settings(CARGA_IAM_DECISAO_REMOTA_ATIVA=True)
def test_piloto_decide_remotamente_e_exige_mesma_identidade():
    with patch(
        "apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto",
        return_value={"usuario_id": 7, "decisao_id": "decisao-1"},
    ) as remoto:
        assert CanPermissionCarga().has_permission(_requisicao(), VISAO) is True
    remoto.assert_called_once_with(
        credenciais={"gpp_session_CARGA_ORG_LOT": "sessao-opaca"},
        permissao="view_importacaoplanilha",
        correlacao="piloto-123",
    )


@override_settings(CARGA_IAM_DECISAO_REMOTA_ATIVA=True)
def test_identidade_divergente_falha_fechada():
    with patch(
        "apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto",
        return_value={"usuario_id": 8, "decisao_id": "decisao-1"},
    ):
        with pytest.raises(ServicoIAMIndisponivel) as erro:
            CanPermissionCarga().has_permission(_requisicao(), VISAO)
    assert erro.value.status_code == 503


@override_settings(CARGA_IAM_DECISAO_REMOTA_ATIVA=True)
@pytest.mark.parametrize(
    ("falha", "resposta", "status"),
    [
        (SessaoIAMInvalida, SessaoCargaInvalida, 401),
        (PermissaoIAMNegada, PermissaoCargaNegada, 403),
        (IAMIndisponivel, ServicoIAMIndisponivel, 503),
    ],
)
def test_resultados_do_iam_tem_respostas_distintas(falha, resposta, status):
    with patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto", side_effect=falha()):
        with pytest.raises(resposta) as erro:
            CanPermissionCarga().has_permission(_requisicao(), VISAO)
    assert erro.value.status_code == status


@override_settings(CARGA_IAM_DECISAO_REMOTA_ATIVA=True)
def test_sem_cookie_nao_consulta_iam():
    with patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto") as remoto:
        with pytest.raises(SessaoCargaInvalida):
            CanPermissionCarga().has_permission(_requisicao(com_cookie=False), VISAO)
    remoto.assert_not_called()


@override_settings(CARGA_IAM_DECISAO_REMOTA_ATIVA=True)
def test_contexto_abac_nao_suportado_bloqueia_piloto():
    visao = SimpleNamespace(
        required_permission="view_importacaoplanilha",
        permission_context={"patriarca": "123"},
    )
    with patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto") as remoto:
        with pytest.raises(ServicoIAMIndisponivel):
            CanPermissionCarga().has_permission(_requisicao(), visao)
    remoto.assert_not_called()


@override_settings(CARGA_IAM_DECISAO_REMOTA_ATIVA=True)
@pytest.mark.parametrize(
    ("falha", "status", "codigo"),
    [
        (SessaoIAMInvalida, 401, "session_invalid"),
        (PermissaoIAMNegada, 403, "permission_denied"),
        (IAMIndisponivel, 503, "servico_iam_indisponivel"),
    ],
)
def test_view_http_devolve_json_estavel_sem_executar_dominio(falha, status, codigo):
    requisicao = APIRequestFactory().get("/api/carga-org-lot/dashboard/")
    requisicao.COOKIES["gpp_session_CARGA_ORG_LOT"] = "sessao-opaca"
    force_authenticate(
        requisicao,
        user=SimpleNamespace(is_authenticated=True, id=7, pk=7),
    )
    with (
        patch("apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto", side_effect=falha()),
        patch("apps.carga_org_lot.views.dashboard.Patriarca.objects.count") as consultar_dominio,
    ):
        resposta = DashboardCargaOrgLotView.as_view()(requisicao)
    assert resposta.status_code == status
    assert resposta.data["errors"]["code"] == codigo
    consultar_dominio.assert_not_called()
