"""Notificações de Carga; o estado canônico permanece na API HTTP."""

import asyncio
import logging
from http.cookies import CookieError, SimpleCookie

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.carga_org_lot.services.cliente_iam import (
    IAMIndisponivel,
    PermissaoIAMNegada,
    SessaoIAMInvalida,
    decidir_acesso_remoto,
)
from apps.core.services.autorizacao_iam_local import autorizar, obter_aplicacao

logger = logging.getLogger("gpp.security")
PERMISSAO_EVENTOS = "view_importacaoplanilha"
COOKIE_CARGA = "gpp_session_CARGA_ORG_LOT"
CODIGOS_FECHAMENTO = {
    "SESSAO_INVALIDA": 4401,
    "NEGADO": 4403,
    "INDISPONIVEL": 1013,
}


class CargaOrgLotConsumer(AsyncJsonWebsocketConsumer):
    group_name: str | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._monitor_iam = None
        self._decisao_lock = asyncio.Lock()
        self._encerrado = False

    async def connect(self):
        resultado = await self._decidir()
        if resultado != "AUTORIZADO":
            self._encerrado = True
            await self.close(code=CODIGOS_FECHAMENTO[resultado])
            return
        kwargs = self.scope["url_route"]["kwargs"]
        if "envio_id" in kwargs:
            self.group_name = f"carga_org_lot.envio.{kwargs['envio_id']}"
        elif "patriarca_id" in kwargs:
            self.group_name = f"carga_org_lot.patriarca.{kwargs['patriarca_id']}"
        else:
            self.group_name = "carga_org_lot.dashboard"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        if settings.CARGA_IAM_WEBSOCKET_REMOTO_ATIVO:
            self._monitor_iam = asyncio.create_task(self._revalidar_enquanto_ocioso())

    async def disconnect(self, code):
        del code
        self._encerrado = True
        if self._monitor_iam is not None:
            self._monitor_iam.cancel()
            try:
                await self._monitor_iam
            except asyncio.CancelledError:
                pass
        if self.group_name is not None:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def carga_event(self, event):
        if settings.CARGA_IAM_WEBSOCKET_REMOTO_ATIVO:
            async with self._decisao_lock:
                if self._encerrado:
                    return
                resultado = await self._decidir()
                if resultado != "AUTORIZADO":
                    self._encerrado = True
                    await self.close(code=CODIGOS_FECHAMENTO[resultado])
                    return
                await self.send_json(event["payload"])
            return
        await self.send_json(event["payload"])

    async def _revalidar_enquanto_ocioso(self):
        """Fecha sessão revogada mesmo sem eventos; falha IAM nunca libera."""
        try:
            while not self._encerrado:
                await asyncio.sleep(settings.CARGA_IAM_WEBSOCKET_REVALIDACAO_SEGUNDOS)
                async with self._decisao_lock:
                    if self._encerrado:
                        return
                    resultado = await self._decidir()
                    if resultado != "AUTORIZADO":
                        self._encerrado = True
                        await self.close(code=CODIGOS_FECHAMENTO[resultado])
                        return
        except asyncio.CancelledError:
            raise
        except Exception:  # fronteira: erro inesperado encerra a conexão
            logger.exception("CARGA_WS_IAM_REVALIDACAO_INDISPONIVEL")
            self._encerrado = True
            await self.close(code=CODIGOS_FECHAMENTO["INDISPONIVEL"])

    async def _decidir(self):
        if settings.CARGA_IAM_WEBSOCKET_REMOTO_ATIVO:
            return await sync_to_async(self._decidir_remoto, thread_sensitive=False)()
        return "AUTORIZADO" if await self._authorized() else "NEGADO"

    def _decidir_remoto(self):  # pylint: disable=too-many-return-statements
        usuario = self.scope.get("user")

        cabecalhos = dict(self.scope.get("headers", []))
        cookies = SimpleCookie()
        try:
            cookies.load(cabecalhos.get(b"cookie", b"").decode("latin1"))
        except (CookieError, TypeError, ValueError):
            return "SESSAO_INVALIDA"
        cookie_carga = cookies.get(COOKIE_CARGA)
        if cookie_carga is None or not cookie_carga.value:
            return "SESSAO_INVALIDA"

        try:
            decisao = decidir_acesso_remoto(
                credenciais={COOKIE_CARGA: cookie_carga.value},
                permissao=PERMISSAO_EVENTOS,
                correlacao=cabecalhos.get(b"x-correlation-id", b"").decode(
                    "ascii", errors="ignore"
                ),
            )
        except SessaoIAMInvalida:
            return "SESSAO_INVALIDA"
        except PermissaoIAMNegada:
            return "NEGADO"
        except IAMIndisponivel:
            return "INDISPONIVEL"
        except Exception:  # fronteira: erro inesperado nunca libera evento
            logger.exception("CARGA_WS_IAM_ERRO_INESPERADO")
            return "INDISPONIVEL"

        usuario_remoto = decisao.get("usuario_id") if isinstance(decisao, dict) else None
        identidade_invalida = (
            not isinstance(usuario_remoto, int)
            or isinstance(usuario_remoto, bool)
            or usuario_remoto < 1
        )
        identidade_divergente = (
            usuario is not None
            and getattr(usuario, "is_authenticated", False)
            and usuario_remoto != usuario.pk
        )
        if identidade_invalida or identidade_divergente:
            logger.error(
                "CARGA_WS_IAM_IDENTIDADE_DIVERGENTE decisao_id=%s",
                decisao.get("decisao_id", "indisponivel")
                if isinstance(decisao, dict) else "indisponivel",
            )
            return "INDISPONIVEL"
        return "AUTORIZADO"

    @database_sync_to_async
    def _authorized(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return False
        application = obter_aplicacao("CARGA_ORG_LOT")
        return autorizar(
            user,
            PERMISSAO_EVENTOS,
            aplicacao=application,
        )
