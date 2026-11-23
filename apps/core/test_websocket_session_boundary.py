"""Regressão da seleção de sessão WebSocket sem banco real."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import override_settings

from apps.core.middleware.websocket import MiddlewareSessaoAplicacaoWebSocket


def _middleware():
    return MiddlewareSessaoAplicacaoWebSocket(
        lambda *_: None,
        contextos_por_prefixo={"ws/carga-org-lot": "CARGA_ORG_LOT"},
    )


def _escopo(cookies):
    return {
        "path": "/ws/carga-org-lot/dashboard/",
        "headers": [(b"cookie", cookies.encode("latin1"))],
    }


def test_cookie_dedicado_invalido_nao_faz_fallback_websocket():
    middleware = _middleware()
    escopo = _escopo(
        "gpp_session_CARGA_ORG_LOT=invalida; gpp_session_PORTAL=valida"
    )
    with patch("apps.core.middleware.websocket.AccountsSession") as sessoes:
        sessoes.objects.filter.return_value.select_related.return_value.first.return_value = None
        usuario, contexto = MiddlewareSessaoAplicacaoWebSocket.__dict__["_resolver"].func(
            middleware, escopo
        )
    assert isinstance(usuario, AnonymousUser)
    assert contexto == "CARGA_ORG_LOT"
    sessoes.objects.filter.return_value.select_related.return_value.order_by.assert_not_called()


def test_fallback_websocket_usa_sessao_mais_recente_e_contexto_do_cookie():
    middleware = _middleware()
    usuario_esperado = SimpleNamespace(is_superuser=True)
    sessao = SimpleNamespace(user=usuario_esperado)
    escopo = _escopo("gpp_session_PORTAL=portal; gpp_session_ACOES_PNGI=acoes")
    with patch("apps.core.middleware.websocket.AccountsSession") as sessoes:
        consulta = sessoes.objects.filter.return_value.select_related.return_value
        consulta.order_by.return_value.first.return_value = sessao
        usuario, contexto = MiddlewareSessaoAplicacaoWebSocket.__dict__["_resolver"].func(
            middleware, escopo
        )
    assert usuario is usuario_esperado
    assert contexto == "CARGA_ORG_LOT"
    consulta.order_by.assert_called_once_with("-created_at")
    _, filtros = sessoes.objects.filter.call_args
    assert filtros["user__is_active"] is True


def test_fallback_websocket_recusa_usuario_sem_perfil_administrativo():
    middleware = _middleware()
    sessao = SimpleNamespace(user=SimpleNamespace(is_superuser=False))
    with (
        patch("apps.core.middleware.websocket.AccountsSession") as sessoes,
        patch("apps.core.middleware.websocket.UserRole") as roles,
    ):
        sessoes.objects.filter.return_value.select_related.return_value.order_by.return_value.first.return_value = sessao
        roles.objects.filter.return_value.exists.return_value = False
        usuario, contexto = MiddlewareSessaoAplicacaoWebSocket.__dict__["_resolver"].func(
            middleware, _escopo("gpp_session_PORTAL=portal")
        )
    assert isinstance(usuario, AnonymousUser)
    assert contexto == "CARGA_ORG_LOT"


def test_cookie_dedicado_valido_websocket_nao_consulta_fallback():
    middleware = _middleware()
    usuario_esperado = SimpleNamespace(is_superuser=False)
    sessao = SimpleNamespace(user=usuario_esperado)
    with (
        patch("apps.core.middleware.websocket.AccountsSession") as sessoes,
        patch("apps.core.middleware.websocket.UserRole") as roles,
    ):
        consulta = sessoes.objects.filter.return_value.select_related.return_value
        consulta.first.return_value = sessao
        usuario, contexto = MiddlewareSessaoAplicacaoWebSocket.__dict__["_resolver"].func(
            middleware, _escopo("gpp_session_CARGA_ORG_LOT=valida; gpp_session_PORTAL=portal")
        )
    assert usuario is usuario_esperado
    assert contexto == "CARGA_ORG_LOT"
    consulta.order_by.assert_not_called()
    roles.objects.filter.assert_not_called()


def test_websocket_rota_desconhecida_ou_sem_cookie_nao_consulta_sessoes():
    middleware = _middleware()
    with patch("apps.core.middleware.websocket.AccountsSession") as sessoes:
        usuario_sem_contexto, contexto_ausente = MiddlewareSessaoAplicacaoWebSocket.__dict__["_resolver"].func(
            middleware, {"path": "/ws/outra-app/", "headers": []}
        )
        usuario_sem_cookie, contexto_carga = MiddlewareSessaoAplicacaoWebSocket.__dict__["_resolver"].func(
            middleware, {"path": "/ws/carga-org-lot/dashboard/", "headers": []}
        )
    assert isinstance(usuario_sem_contexto, AnonymousUser)
    assert contexto_ausente is None
    assert isinstance(usuario_sem_cookie, AnonymousUser)
    assert contexto_carga == "CARGA_ORG_LOT"
    sessoes.objects.filter.assert_not_called()


def test_fallback_websocket_sem_sessao_valida_recusa():
    middleware = _middleware()
    with patch("apps.core.middleware.websocket.AccountsSession") as sessoes:
        sessoes.objects.filter.return_value.select_related.return_value.order_by.return_value.first.return_value = None
        usuario, _ = MiddlewareSessaoAplicacaoWebSocket.__dict__["_resolver"].func(
            middleware, _escopo("gpp_session_PORTAL=invalida")
        )
    assert isinstance(usuario, AnonymousUser)


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=True)
def test_piloto_carga_nao_altera_resolucao_local_de_publicacoes():
    async def destino(escopo, _receber, _enviar):
        return escopo

    middleware = MiddlewareSessaoAplicacaoWebSocket(
        destino,
        contextos_por_prefixo={
            "ws/carga-org-lot/": "CARGA_ORG_LOT",
            "ws/pub-institucional/": "PUB_INSTITUCIONAL",
        },
    )
    usuario = SimpleNamespace(pk=42)
    resolver = AsyncMock(return_value=(usuario, "PUB_INSTITUCIONAL"))
    with patch.object(middleware, "_resolver", resolver):
        escopo = asyncio.run(
            middleware({"path": "/ws/pub-institucional/edocs/"}, None, None)
        )
    resolver.assert_awaited_once()
    assert escopo["user"] is usuario
    assert escopo["app_context"] == "PUB_INSTITUCIONAL"


@override_settings(CARGA_IAM_WEBSOCKET_REMOTO_ATIVO=False)
def test_modo_padrao_carga_continua_resolvendo_sessao_local():
    async def destino(escopo, _receber, _enviar):
        return escopo

    middleware = MiddlewareSessaoAplicacaoWebSocket(
        destino,
        contextos_por_prefixo={"ws/carga-org-lot/": "CARGA_ORG_LOT"},
    )
    usuario = SimpleNamespace(pk=7)
    resolver = AsyncMock(return_value=(usuario, "CARGA_ORG_LOT"))
    with patch.object(middleware, "_resolver", resolver):
        escopo = asyncio.run(
            middleware({"path": "/ws/carga-org-lot/dashboard/"}, None, None)
        )
    resolver.assert_awaited_once()
    assert escopo["user"] is usuario
