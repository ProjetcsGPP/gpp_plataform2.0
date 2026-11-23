"""Rejeição explícita de caminhos WebSocket fora do perfil piloto."""

from channels.generic.websocket import AsyncWebsocketConsumer


class RejeitarRotaWebSocketDesconhecida(AsyncWebsocketConsumer):
    """Evita resposta HTTP 500 do URLRouter para rotas não montadas."""

    async def connect(self):
        await self.close(code=4404)
