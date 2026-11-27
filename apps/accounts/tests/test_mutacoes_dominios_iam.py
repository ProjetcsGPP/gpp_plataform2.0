"""Matriz de falha fechada para todas as mutações HTTP roteadas."""

from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.carga_org_lot.services.cliente_iam import (
    IAMIndisponivel as IAMCargaIndisponivel,
    PermissaoIAMNegada as PermissaoCargaNegada,
    SessaoIAMInvalida as SessaoCargaInvalida,
)
from apps.carga_org_lot.urls import router as roteador_carga
from apps.pub_institucional.urls import roteador as roteador_publicacoes
from common.services.cliente_iam import (
    IAMIndisponivel as IAMPublicacoesIndisponivel,
    PermissaoIAMNegada as PermissaoPublicacoesNegada,
    SessaoIAMInvalida as SessaoPublicacoesInvalida,
)
from common.services.identidade_iam import IdentidadeIAM


def _acoes_mutaveis(roteador, namespace):
    acoes = []
    for rota in roteador.urls:
        mapeamento = getattr(rota.callback, "actions", {})
        for metodo, acao in mapeamento.items():
            if "format" in rota.pattern.regex.groupindex:
                continue  # Mesma ação DRF com sufixo de formato opcional.
            if metodo not in {"post", "put", "patch", "delete"}:
                continue
            if metodo not in rota.callback.cls.http_method_names:
                continue
            kwargs = {nome: "1" for nome in rota.pattern.regex.groupindex}
            caminho = reverse(f"{namespace}:{rota.name}", kwargs=kwargs)
            acoes.append((metodo, acao, caminho, rota.callback, kwargs))
    return acoes


@pytest.mark.parametrize(
    "metodo,acao,caminho,visao,kwargs",
    _acoes_mutaveis(roteador_carga, "carga_org_lot"),
)
@pytest.mark.parametrize("falha,status,codigo", [
    (SessaoCargaInvalida, 401, "session_invalid"),
    (PermissaoCargaNegada, 403, "permission_denied"),
    (IAMCargaIndisponivel, 503, "servico_iam_indisponivel"),
])
@override_settings(CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True)
def test_mutacao_carga_nao_entra_no_dominio_sem_iam(
    metodo, acao, caminho, visao, kwargs, falha, status, codigo
):
    requisicao = getattr(APIRequestFactory(), metodo)(caminho, data={}, format="json")
    requisicao.COOKIES["gpp_session_CARGA_ORG_LOT"] = "sessao-ensaio"
    force_authenticate(requisicao, user=IdentidadeIAM(7, "Gestor"))
    with (
        patch(
            "apps.carga_org_lot.permissoes_iam.decidir_acesso_remoto",
            side_effect=falha(),
        ),
        patch.object(visao.cls, acao, side_effect=AssertionError("dominio executado")) as dominio,
    ):
        resposta = visao(requisicao, **kwargs)
    assert resposta.status_code == status, (metodo, caminho, resposta.data)
    assert resposta.data["errors"]["code"] == codigo
    dominio.assert_not_called()


@pytest.mark.parametrize(
    "metodo,acao,caminho,visao,kwargs",
    _acoes_mutaveis(roteador_publicacoes, "pub_institucional"),
)
@pytest.mark.parametrize("falha,status,codigo", [
    (SessaoPublicacoesInvalida, 401, "session_invalid"),
    (PermissaoPublicacoesNegada, 403, "permission_denied"),
    (IAMPublicacoesIndisponivel, 503, "servico_iam_indisponivel"),
])
@override_settings(PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA=True)
def test_mutacao_publicacoes_nao_entra_no_dominio_sem_iam(
    metodo, acao, caminho, visao, kwargs, falha, status, codigo
):
    requisicao = getattr(APIRequestFactory(), metodo)(caminho, data={}, format="json")
    requisicao.COOKIES["gpp_session_PUB_INSTITUCIONAL"] = "sessao-ensaio"
    force_authenticate(requisicao, user=IdentidadeIAM(7, "Gestor"))
    with (
        patch(
            "apps.pub_institucional.permissoes_iam.decidir_acesso_remoto",
            side_effect=falha(),
        ),
        patch.object(visao.cls, acao, side_effect=AssertionError("dominio executado")) as dominio,
    ):
        resposta = visao(requisicao, **kwargs)
    assert resposta.status_code == status, (metodo, caminho, resposta.data)
    assert resposta.data["errors"]["code"] == codigo
    dominio.assert_not_called()
