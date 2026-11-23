"""Contrato de regressão da fronteira IAM local antes da extração de serviços."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from rest_framework.test import APIRequestFactory

from apps.carga_org_lot.consumers import CargaOrgLotConsumer
from apps.core.permissions import CanPermission
from apps.core.services.autorizacao_iam_local import autorizar, obter_aplicacao


def _decisao_websocket(consumer):
    """Executa só a regra síncrona, sem abrir canal ou conexão de banco."""
    return CargaOrgLotConsumer.__dict__["_authorized"].func(consumer)


def test_adaptador_preserva_aplicacao_permissao_e_contexto():
    usuario = SimpleNamespace(is_authenticated=True)
    aplicacao = object()
    contexto = {"patriarca": "123"}
    with patch(
        "apps.core.services.autorizacao_iam_local.AuthorizationService"
    ) as servico:
        servico.return_value.can.return_value = True
        assert autorizar(
            usuario,
            "view_importacaoplanilha",
            aplicacao=aplicacao,
            contexto=contexto,
        ) is True
    servico.assert_called_once_with(usuario, aplicacao)
    servico.return_value.can.assert_called_once_with(
        "view_importacaoplanilha", context=contexto
    )


def test_adaptador_resolve_aplicacao_no_cadastro_existente():
    with patch(
        "apps.core.services.autorizacao_iam_local.ApplicationRegistry"
    ) as registro:
        assert obter_aplicacao("CARGA_ORG_LOT") is registro.return_value.get.return_value
    registro.return_value.get.assert_called_once_with("CARGA_ORG_LOT")


def test_falha_do_iam_local_nao_concede_acesso():
    with patch(
        "apps.core.services.autorizacao_iam_local.AuthorizationService"
    ) as servico:
        servico.return_value.can.side_effect = RuntimeError("IAM indisponível")
        with pytest.raises(RuntimeError, match="IAM indisponível"):
            autorizar(object(), "view_importacaoplanilha")


@pytest.mark.parametrize("decisao", [True, False])
def test_permissao_http_usa_a_mesma_decisao(decisao):
    usuario = SimpleNamespace(is_authenticated=True, id=7)
    aplicacao = object()
    requisicao = APIRequestFactory().get("/api/carga-org-lot/exemplo/")
    requisicao.user = usuario
    requisicao.application = aplicacao
    visao = SimpleNamespace(
        required_permission="view_importacaoplanilha",
        permission_context={"patriarca": "123"},
    )
    with patch("apps.core.permissions.autorizar", return_value=decisao) as decidir:
        assert CanPermission().has_permission(requisicao, visao) is decisao
    decidir.assert_called_once_with(
        usuario,
        "view_importacaoplanilha",
        aplicacao=aplicacao,
        contexto={"patriarca": "123"},
    )


@pytest.mark.parametrize("decisao", [True, False])
def test_websocket_carga_usa_a_mesma_decisao(decisao):
    usuario = SimpleNamespace(is_authenticated=True)
    aplicacao = object()
    consumer = CargaOrgLotConsumer()
    consumer.scope = {"user": usuario}
    with (
        patch("apps.carga_org_lot.consumers.obter_aplicacao", return_value=aplicacao),
        patch("apps.carga_org_lot.consumers.autorizar", return_value=decisao) as decidir,
    ):
        assert _decisao_websocket(consumer) is decisao
    decidir.assert_called_once_with(
        usuario,
        "view_importacaoplanilha",
        aplicacao=aplicacao,
    )


def test_websocket_sem_usuario_nao_consulta_iam():
    consumer = CargaOrgLotConsumer()
    consumer.scope = {"user": SimpleNamespace(is_authenticated=False)}
    with patch("apps.carga_org_lot.consumers.autorizar", new_callable=Mock) as decidir:
        assert _decisao_websocket(consumer) is False
    decidir.assert_not_called()
