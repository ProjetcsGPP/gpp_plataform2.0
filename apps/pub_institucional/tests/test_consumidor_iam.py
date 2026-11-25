"""Contrato WebSocket opt-in de Publicações com decisão IAM por evento."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings

from apps.pub_institucional.consumidores import ConsumidorEdocs
from common.services.cliente_iam import (
    IAMIndisponivel, PermissaoIAMNegada, SessaoIAMInvalida,
)


def _consumidor(cookies="gpp_session_PUB_INSTITUCIONAL=sessao-opaca"):
    consumidor = ConsumidorEdocs()
    consumidor.scope = {
        "user": AnonymousUser(),
        "headers": [(b"cookie", cookies.encode("latin1"))],
    }
    consumidor.channel_layer = SimpleNamespace(
        group_add=AsyncMock(), group_discard=AsyncMock(),
    )
    consumidor.channel_name = "teste-publicacoes"
    consumidor.accept = AsyncMock()
    consumidor.close = AsyncMock()
    consumidor.send_json = AsyncMock()
    return consumidor


def _executar(consumidor, evento=None):
    async def cenario():
        await consumidor.connect()
        if evento is not None:
            await consumidor.publicacoes_evento(evento)
        await consumidor.disconnect(1000)

    asyncio.run(cenario())


@override_settings(PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO=False)
def test_modo_local_preservado():
    consumidor = _consumidor()
    with (
        patch.object(consumidor, "_esta_autorizado", new=AsyncMock(return_value=True)),
        patch("apps.pub_institucional.consumidores.decidir_acesso_remoto") as remoto,
    ):
        _executar(consumidor, {"evento": "teste", "dados": {}})
    consumidor.accept.assert_awaited_once()
    consumidor.send_json.assert_awaited_once_with({"evento": "teste", "dados": {}})
    remoto.assert_not_called()


@override_settings(PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_remoto_revalida_e_nao_entrega_apos_revogacao():
    consumidor = _consumidor()
    with patch.object(
        consumidor, "_decidir", new=AsyncMock(side_effect=["AUTORIZADO", "SESSAO_INVALIDA"]),
    ):
        _executar(consumidor, {"evento": "privado", "dados": {"id": 1}})
    consumidor.accept.assert_awaited_once()
    consumidor.close.assert_awaited_once_with(code=4401)
    consumidor.send_json.assert_not_awaited()


@override_settings(PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO=True)
@pytest.mark.parametrize(
    ("erro", "codigo"),
    [(PermissaoIAMNegada, 4403), (IAMIndisponivel, 1013)],
)
def test_remoto_falha_fechada_antes_do_evento(erro, codigo):
    consumidor = _consumidor()
    with patch.object(
        consumidor, "_decidir", new=AsyncMock(side_effect=[
            "AUTORIZADO", "NEGADO" if erro is PermissaoIAMNegada else "INDISPONIVEL",
        ]),
    ):
        _executar(consumidor, {"evento": "privado", "dados": {}})
    consumidor.close.assert_awaited_once_with(code=codigo)
    consumidor.send_json.assert_not_awaited()


@override_settings(PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO=True)
@pytest.mark.parametrize("cookies", ["", "gpp_session_PORTAL=sessao-portal"])
def test_remoto_exige_cookie_proprio(cookies):
    consumidor = _consumidor(cookies)
    with patch("apps.pub_institucional.consumidores.decidir_acesso_remoto") as remoto:
        assert consumidor._decidir_remoto() == "SESSAO_INVALIDA"  # pylint: disable=protected-access
    remoto.assert_not_called()


@override_settings(
    PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO=True,
    IAM_URL_PUBLICACOES="http://127.0.0.1:8000",
    IAM_TOKEN_SERVICO_PUBLICACOES="token-exclusivo",
)
def test_remoto_envia_somente_cookie_proprio_e_permissao():
    consumidor = _consumidor(
        "gpp_session_PORTAL=sessao-portal; "
        "gpp_session_PUB_INSTITUCIONAL=sessao-opaca"
    )
    with patch(
        "apps.pub_institucional.consumidores.decidir_acesso_remoto",
        return_value={"usuario_id": 7},
    ) as remoto:
        assert consumidor._decidir_remoto() == "AUTORIZADO"  # pylint: disable=protected-access
    assert remoto.call_args.kwargs["credenciais"] == {
        "gpp_session_PUB_INSTITUCIONAL": "sessao-opaca",
    }
    assert remoto.call_args.kwargs["permissao"] == "visualizar_coletas_patriarcas"


@override_settings(PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO=True)
@pytest.mark.parametrize(
    ("erro", "resultado"),
    [
        (SessaoIAMInvalida, "SESSAO_INVALIDA"),
        (PermissaoIAMNegada, "NEGADO"),
        (IAMIndisponivel, "INDISPONIVEL"),
    ],
)
def test_remoto_traduz_erro_iam_sem_fallback(erro, resultado):
    consumidor = _consumidor()
    with patch(
        "apps.pub_institucional.consumidores.decidir_acesso_remoto",
        side_effect=erro(),
    ):
        assert consumidor._decidir_remoto() == resultado  # pylint: disable=protected-access


@override_settings(PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO=True)
@pytest.mark.parametrize("identidade", [None, True, 0])
def test_remoto_identidade_invalida_nao_conecta(identidade):
    consumidor = _consumidor()
    with patch(
        "apps.pub_institucional.consumidores.decidir_acesso_remoto",
        return_value={"usuario_id": identidade},
    ):
        assert consumidor._decidir_remoto() == "INDISPONIVEL"  # pylint: disable=protected-access


@override_settings(
    PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO=True,
    PUBLICACOES_IAM_WEBSOCKET_REVALIDACAO_SEGUNDOS=0.01,
)
def test_remoto_fecha_conexao_ociosa_revogada():
    consumidor = _consumidor()

    async def cenario():
        await consumidor.connect()
        await asyncio.wait_for(consumidor._monitor_iam, timeout=1)  # pylint: disable=protected-access
        await consumidor.disconnect(1000)

    with patch.object(
        consumidor, "_decidir", new=AsyncMock(side_effect=["AUTORIZADO", "SESSAO_INVALIDA"]),
    ):
        asyncio.run(cenario())
    consumidor.close.assert_awaited_once_with(code=4401)
