"""Notificações WebSocket de Publicações; o estado canônico fica na API HTTP."""

import asyncio
import logging
from http.cookies import CookieError, SimpleCookie

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.pub_institucional.edocs_tempo_real import GRUPO_EDOCS
from common.services.cliente_iam import (
    IAMIndisponivel, PermissaoIAMNegada, SessaoIAMInvalida,
    decidir_acesso_remoto,
)

logger = logging.getLogger("gpp.security")
COOKIE_PUBLICACOES = "gpp_session_PUB_INSTITUCIONAL"
CAMINHO_IAM = "/interno/iam/v1/decisoes-publicacoes/"
PERMISSAO_EVENTOS = "visualizar_coletas_patriarcas"
CODIGOS_FECHAMENTO = {"SESSAO_INVALIDA": 4401, "NEGADO": 4403, "INDISPONIVEL": 1013}


class ConsumidorEdocs(AsyncJsonWebsocketConsumer):
    """Revalida a permissão antes dos eventos e durante a ociosidade."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._monitor_iam = None
        self._decisao_lock = asyncio.Lock()
        self._encerrado = False
        self._grupo_adicionado = False

    async def connect(self):
        resultado = await self._decidir()
        if resultado != "AUTORIZADO":
            self._encerrado = True
            await self.close(code=CODIGOS_FECHAMENTO[resultado])
            return
        await self.channel_layer.group_add(GRUPO_EDOCS, self.channel_name)
        self._grupo_adicionado = True
        await self.accept()
        if settings.PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO:
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
        if self._grupo_adicionado:
            await self.channel_layer.group_discard(GRUPO_EDOCS, self.channel_name)

    async def publicacoes_evento(self, evento):
        if settings.PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO:
            async with self._decisao_lock:
                if self._encerrado:
                    return
                resultado = await self._decidir()
                if resultado != "AUTORIZADO":
                    self._encerrado = True
                    await self.close(code=CODIGOS_FECHAMENTO[resultado])
                    return
                await self.send_json({"evento": evento["evento"], "dados": evento["dados"]})
            return
        await self.send_json({"evento": evento["evento"], "dados": evento["dados"]})

    async def _revalidar_enquanto_ocioso(self):
        try:
            while not self._encerrado:
                await asyncio.sleep(settings.PUBLICACOES_IAM_WEBSOCKET_REVALIDACAO_SEGUNDOS)
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
        except Exception:  # fronteira: qualquer falha inesperada fecha a conexão
            logger.exception("PUBLICACOES_WS_IAM_REVALIDACAO_INDISPONIVEL")
            self._encerrado = True
            await self.close(code=CODIGOS_FECHAMENTO["INDISPONIVEL"])

    async def _decidir(self):
        if settings.PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO:
            return await sync_to_async(self._decidir_remoto, thread_sensitive=False)()
        return "AUTORIZADO" if await self._esta_autorizado() else "NEGADO"

    def _decidir_remoto(self):  # pylint: disable=too-many-return-statements
        cabecalhos = dict(self.scope.get("headers", []))
        cookies = SimpleCookie()
        try:
            cookies.load(cabecalhos.get(b"cookie", b"").decode("latin1"))
        except (CookieError, TypeError, ValueError):
            return "SESSAO_INVALIDA"
        cookie = cookies.get(COOKIE_PUBLICACOES)
        if cookie is None or not cookie.value:
            return "SESSAO_INVALIDA"
        try:
            decisao = decidir_acesso_remoto(
                url=settings.IAM_URL_PUBLICACOES,
                caminho=CAMINHO_IAM,
                token=settings.IAM_TOKEN_SERVICO_PUBLICACOES,
                credenciais={COOKIE_PUBLICACOES: cookie.value},
                nome_cookie=COOKIE_PUBLICACOES,
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
        except Exception:
            logger.exception("PUBLICACOES_WS_IAM_ERRO_INESPERADO")
            return "INDISPONIVEL"
        usuario_id = decisao.get("usuario_id") if isinstance(decisao, dict) else None
        usuario_local = self.scope.get("user")
        identidade_invalida = (
            not isinstance(usuario_id, int)
            or isinstance(usuario_id, bool)
            or usuario_id < 1
        )
        identidade_divergente = (
            usuario_local is not None
            and getattr(usuario_local, "is_authenticated", False)
            and usuario_id != usuario_local.pk
        )
        if identidade_invalida or identidade_divergente:
            logger.error("PUBLICACOES_WS_IAM_IDENTIDADE_INVALIDA")
            return "INDISPONIVEL"
        return "AUTORIZADO"

    @database_sync_to_async
    def _esta_autorizado(self):
        usuario = self.scope.get("user")
        return bool(
            usuario
            and usuario.is_authenticated
            and (
                usuario.is_superuser
                or usuario.has_perm("pub_institucional.visualizar_coletas_patriarcas")
            )
        )
