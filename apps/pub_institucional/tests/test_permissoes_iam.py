"""Decisões auxiliares de Publicações não podem voltar ao IAM local."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.pub_institucional.permissoes_iam import (
    CanPermissionPublicacoes, ServicoIAMPublicacoesIndisponivel,
    SessaoPublicacoesInvalida,
    pode_acao_adicional,
)
from common.services.cliente_iam import PermissaoIAMNegada, SessaoIAMInvalida
from common.services.identidade_iam import IdentidadeIAM


def _requisicao():
    return SimpleNamespace(
        path="/api/pub-institucional/patriarcas/",
        COOKIES={"gpp_session_PUB_INSTITUCIONAL": "sessao-opaca"},
        headers={},
        user=IdentidadeIAM(7, "Gestor"),
    )


@override_settings(PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True)
def test_permissao_auxiliar_negada_gera_falso_sem_fallback_local():
    with (
        patch("apps.pub_institucional.permissoes_iam.decidir_acesso_remoto", side_effect=PermissaoIAMNegada()),
        patch("apps.pub_institucional.permissoes_iam.AuthorizationService", side_effect=AssertionError("IAM local")),
    ):
        assert pode_acao_adicional(_requisicao(), "revisar_patriarcas_edocs") is False


@override_settings(PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True)
def test_sessao_auxiliar_invalida_nao_vira_falso_silencioso():
    with patch("apps.pub_institucional.permissoes_iam.decidir_acesso_remoto", side_effect=SessaoIAMInvalida()):
        with pytest.raises(SessaoPublicacoesInvalida) as capturada:
            pode_acao_adicional(_requisicao(), "revisar_patriarcas_edocs")
    assert capturada.value.status_code == 401


@override_settings(PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True)
def test_identidade_auxiliar_divergente_falha_fechada():
    with patch("apps.pub_institucional.permissoes_iam.decidir_acesso_remoto", return_value={
        "usuario_id": 8, "decisao_id": "decisao-sintetica",
    }):
        with pytest.raises(ServicoIAMPublicacoesIndisponivel):
            pode_acao_adicional(_requisicao(), "revisar_patriarcas_edocs")


@override_settings(PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True)
def test_cookie_de_outra_app_nao_autoriza_nem_e_enviado_ao_iam():
    requisicao = _requisicao()
    requisicao.COOKIES = {"gpp_session_PORTAL": "sessao-portal"}
    visao = SimpleNamespace(required_permission="view_patriarcaedocs")
    with patch("apps.pub_institucional.permissoes_iam.decidir_acesso_remoto") as remoto:
        with pytest.raises(SessaoPublicacoesInvalida):
            CanPermissionPublicacoes().has_permission(requisicao, visao)
    remoto.assert_not_called()


@override_settings(PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True)
def test_cookie_da_app_e_o_unico_enviado_ao_iam():
    requisicao = _requisicao()
    requisicao.COOKIES["gpp_session_PORTAL"] = "sessao-portal"
    with patch(
        "apps.pub_institucional.permissoes_iam.decidir_acesso_remoto",
        return_value={"usuario_id": 7, "decisao_id": "teste"},
    ) as remoto:
        assert pode_acao_adicional(requisicao, "revisar_patriarcas_edocs") is True
    assert remoto.call_args.kwargs["credenciais"] == {
        "gpp_session_PUB_INSTITUCIONAL": "sessao-opaca"
    }


def test_todas_as_acoes_administrativas_roteadas_declaram_permissao():
    """Uma nova action não pode ficar exposta sem permissão técnica explícita."""
    from apps.pub_institucional.urls import roteador  # pylint: disable=import-outside-toplevel
    from apps.pub_institucional.visoes import (  # pylint: disable=import-outside-toplevel
        VisaoPreferenciaExibicaoEflow,
    )

    ausentes = []
    for rota in roteador.urls:
        if not hasattr(rota.callback, "actions"):
            continue  # API root do DefaultRouter, sem ação de domínio.
        visao = rota.callback.cls
        if visao is VisaoPreferenciaExibicaoEflow:
            # Mapeamento por método HTTP implementado em get_permissions().
            continue
        for metodo, acao in rota.callback.actions.items():
            if metodo not in visao.http_method_names:
                continue
            if not visao.mapa_permissoes.get(acao):
                ausentes.append(f"{visao.__name__}.{acao}")
    assert ausentes == []
