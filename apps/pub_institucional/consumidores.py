"""Consumidores WebSocket de PUBLICAÇÕES."""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.pub_institucional.edocs_tempo_real import GRUPO_EDOCS


class ConsumidorEdocs(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not await self._esta_autorizado():
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(GRUPO_EDOCS, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GRUPO_EDOCS, self.channel_name)

    async def publicacoes_evento(self, evento):
        await self.send_json(
            {"evento": evento["evento"], "dados": evento["dados"]}
        )

    @database_sync_to_async
    def _esta_autorizado(self):
        usuario = self.scope.get("user")
        return bool(
            usuario
            and usuario.is_authenticated
            and (
                usuario.is_superuser
                or usuario.has_perm(
                    "pub_institucional.visualizar_coletas_patriarcas"
                )
            )
        )
