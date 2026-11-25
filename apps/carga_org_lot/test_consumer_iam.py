"""Piloto WebSocket de Carga: decisão antes de cada notificação entregue."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings

from apps.carga_org_lot.consumers import CargaOrgLotConsumer
from apps.carga_org_lot.routing import websocket_urlpatterns
from apps.carga_org_lot.services.cliente_iam import (
    IAMIndisponivel,
    PermissaoIAMNegada,
    SessaoIAMInvalida,
)
from apps.core.middleware.websocket import MiddlewareSessaoAplicacaoWebSocket


def _consumer(*, usuario_id=7, cookies="gpp_session_CARGA_ORG_LOT=sessao-opaca"):
    consumer = CargaOrgLotConsumer()
    consumer.scope = {
        "user": SimpleNamespace(is_authenticated=True, pk=usuario_id),
        "headers": [(b"cookie", cookies.encode("latin1"))],
        "url_route": {"kwargs": {}},
    }
    consumer.channel_layer = SimpleNamespace(group_add=AsyncMock(), group_discard=AsyncMock())
    consumer.channel_name = "teste-carga"
    consumer.accept = AsyncMock()
    consumer.close = AsyncMock()
    consumer.send_json = AsyncMock()
    return consumer


def _executar(consumer, evento=None):
    async def cenario():
        await consumer.connect()
        if evento is not None:
            await consumer.carga_event({"payload": evento})

    asyncio.run(cenario())


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=False)
def test_modo_atual_nao_consulta_iam_nem_revalida_evento():
    consumer = _consumer()
    with (
        patch.object(consumer, "_authorized", new=AsyncMock(return_value=True)),
        patch("apps.carga_org_lot.consumers.decidir_acesso_remoto") as remoto,
    ):
        _executar(consumer, {"evento": "teste"})
    consumer.accept.assert_awaited_once()
    consumer.send_json.assert_awaited_once_with({"evento": "teste"})
    assert consumer._monitor_iam is None  # pylint: disable=protected-access
    remoto.assert_not_called()


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_piloto_revalida_e_fecha_apos_revogacao_sem_enviar_payload():
    consumer = _consumer()
    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto",
        side_effect=[
            {"usuario_id": 7, "decisao_id": "decisao-1"},
            SessaoIAMInvalida(),
        ],
    ) as remoto:
        _executar(consumer, {"dado": "privado"})
    consumer.accept.assert_awaited_once()
    consumer.close.assert_awaited_once_with(code=4401)
    consumer.send_json.assert_not_awaited()
    assert remoto.call_count == 2
    assert remoto.call_args.kwargs["credenciais"] == {
        "gpp_session_CARGA_ORG_LOT": "sessao-opaca"
    }


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
@pytest.mark.parametrize(
    ("erro", "codigo"),
    [(PermissaoIAMNegada, 4403), (IAMIndisponivel, 1013)],
)
def test_piloto_falha_fechada_antes_do_evento(erro, codigo):
    consumer = _consumer()
    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto",
        side_effect=[{"usuario_id": 7, "decisao_id": "decisao-1"}, erro()],
    ):
        _executar(consumer, {"dado": "privado"})
    consumer.close.assert_awaited_once_with(code=codigo)
    consumer.send_json.assert_not_awaited()


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_piloto_identidade_divergente_nega_conexao():
    consumer = _consumer()
    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto",
        return_value={"usuario_id": 8, "decisao_id": "decisao-1"},
    ):
        _executar(consumer)
    consumer.close.assert_awaited_once_with(code=1013)
    consumer.accept.assert_not_awaited()


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_piloto_resposta_inesperada_nega_conexao():
    consumer = _consumer()
    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto", return_value=None
    ):
        _executar(consumer)
    consumer.close.assert_awaited_once_with(code=1013)
    consumer.accept.assert_not_awaited()


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_piloto_sem_usuario_local_exige_identidade_remota_valida():
    consumer = _consumer()
    consumer.scope["user"] = AnonymousUser()
    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto",
        return_value={"usuario_id": None, "decisao_id": "decisao-1"},
    ):
        _executar(consumer)
    consumer.close.assert_awaited_once_with(code=1013)
    consumer.accept.assert_not_awaited()


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_piloto_sem_cookie_nao_consulta_iam():
    consumer = _consumer(cookies="")
    with patch("apps.carga_org_lot.consumers.decidir_acesso_remoto") as remoto:
        _executar(consumer)
    consumer.close.assert_awaited_once_with(code=4401)
    remoto.assert_not_called()


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_piloto_cookie_de_outra_app_nao_consulta_iam():
    consumer = _consumer(cookies="gpp_session_PORTAL=sessao-portal")
    with patch("apps.carga_org_lot.consumers.decidir_acesso_remoto") as remoto:
        _executar(consumer)
    consumer.close.assert_awaited_once_with(code=4401)
    remoto.assert_not_called()


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_piloto_envia_apenas_cookie_de_carga():
    consumer = _consumer(cookies=(
        "gpp_session_PORTAL=sessao-portal; "
        "gpp_session_CARGA_ORG_LOT=sessao-opaca"
    ))
    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto",
        return_value={"usuario_id": 7, "decisao_id": "teste"},
    ) as remoto:
        _executar(consumer)
    assert remoto.call_args.kwargs["credenciais"] == {
        "gpp_session_CARGA_ORG_LOT": "sessao-opaca"
    }


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_asgi_nao_entrega_evento_apos_revogacao():
    """Exercita a rota e o channel layer, além do método do consumer."""

    async def aplicacao(escopo, receber, enviar):
        escopo = dict(escopo)
        escopo["user"] = SimpleNamespace(is_authenticated=True, pk=7)
        await URLRouter(websocket_urlpatterns)(escopo, receber, enviar)

    async def cenario():
        comunicador = WebsocketCommunicator(
            aplicacao,
            "/ws/carga-org-lot/dashboard/",
            headers=[(b"cookie", b"gpp_session_CARGA_ORG_LOT=sessao-opaca")],
        )
        conectado, _ = await comunicador.connect()
        assert conectado is True
        await get_channel_layer().group_send(
            "carga_org_lot.dashboard",
            {"type": "carga.event", "payload": {"dado": "privado"}},
        )
        saida = await comunicador.receive_output(timeout=1)
        assert saida == {"type": "websocket.close", "code": 4401}

    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto",
        side_effect=[
            {"usuario_id": 7, "decisao_id": "decisao-1"},
            SessaoIAMInvalida(),
        ],
    ):
        asyncio.run(cenario())


@override_settings(
    CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True,
    CARGA_IAM_WEBSOCKET_REVALIDACAO_SEGUNDOS=0.01,
)
@pytest.mark.parametrize(
    ("erro", "codigo"),
    [(SessaoIAMInvalida, 4401), (PermissaoIAMNegada, 4403), (IAMIndisponivel, 1013)],
)
def test_asgi_fecha_conexao_ociosa_apos_revalidacao(erro, codigo):
    """Revogação ou queda do IAM fecha o socket sem precisar de evento."""

    async def aplicacao(escopo, receber, enviar):
        escopo = dict(escopo)
        escopo["user"] = SimpleNamespace(is_authenticated=True, pk=7)
        await URLRouter(websocket_urlpatterns)(escopo, receber, enviar)

    async def cenario():
        comunicador = WebsocketCommunicator(
            aplicacao,
            "/ws/carga-org-lot/dashboard/",
            headers=[(b"cookie", b"gpp_session_CARGA_ORG_LOT=sessao-opaca")],
        )
        conectado, _ = await comunicador.connect()
        assert conectado is True
        saida = await comunicador.receive_output(timeout=1)
        assert saida == {"type": "websocket.close", "code": codigo}
        await comunicador.disconnect()

    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto",
        side_effect=[{"usuario_id": 7, "decisao_id": "decisao-1"}, erro()],
    ) as remoto:
        asyncio.run(cenario())
    assert remoto.call_count == 2


@override_settings(
    CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True,
    CARGA_IAM_WEBSOCKET_REVALIDACAO_SEGUNDOS=0.01,
)
def test_asgi_mantem_conexao_ociosa_autorizada_e_cancela_monitor_ao_sair():
    async def aplicacao(escopo, receber, enviar):
        escopo = dict(escopo)
        escopo["user"] = SimpleNamespace(is_authenticated=True, pk=7)
        await URLRouter(websocket_urlpatterns)(escopo, receber, enviar)

    async def cenario():
        comunicador = WebsocketCommunicator(
            aplicacao,
            "/ws/carga-org-lot/dashboard/",
            headers=[(b"cookie", b"gpp_session_CARGA_ORG_LOT=sessao-opaca")],
        )
        conectado, _ = await comunicador.connect()
        assert conectado is True
        await asyncio.sleep(0.04)
        assert remoto.call_count >= 2
        await get_channel_layer().group_send(
            "carga_org_lot.dashboard",
            {"type": "carga.event", "payload": {"evento": "permitido"}},
        )
        assert await comunicador.receive_json_from(timeout=1) == {
            "evento": "permitido"
        }
        await comunicador.disconnect()
        chamadas_apos_saida = remoto.call_count
        await asyncio.sleep(0.04)
        assert remoto.call_count == chamadas_apos_saida

    with patch(
        "apps.carga_org_lot.consumers.decidir_acesso_remoto",
        return_value={"usuario_id": 7, "decisao_id": "decisao-1"},
    ) as remoto:
        asyncio.run(cenario())


@override_settings(
    CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True,
    CARGA_IAM_WEBSOCKET_REVALIDACAO_SEGUNDOS=300,
)
def test_asgi_piloto_remoto_nao_resolve_sessao_local():
    middleware = MiddlewareSessaoAplicacaoWebSocket(
        URLRouter(websocket_urlpatterns),
        contextos_por_prefixo={"ws/carga-org-lot/": "CARGA_ORG_LOT"},
    )

    async def cenario():
        comunicador = WebsocketCommunicator(
            middleware,
            "/ws/carga-org-lot/dashboard/",
            headers=[(b"cookie", b"gpp_session_CARGA_ORG_LOT=sessao-opaca")],
        )
        conectado, _ = await comunicador.connect()
        assert conectado is True
        await get_channel_layer().group_send(
            "carga_org_lot.dashboard",
            {"type": "carga.event", "payload": {"evento": "permitido"}},
        )
        assert await comunicador.receive_json_from(timeout=1) == {
            "evento": "permitido"
        }
        await comunicador.disconnect()

    with (
        patch.object(middleware, "_resolver", side_effect=AssertionError("DB local")) as local,
        patch(
            "apps.carga_org_lot.consumers.decidir_acesso_remoto",
            return_value={"usuario_id": 7, "decisao_id": "decisao-1"},
        ) as remoto,
    ):
        asyncio.run(cenario())
    local.assert_not_called()
    assert remoto.call_count == 2
