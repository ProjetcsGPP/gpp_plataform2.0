from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts.services.application_registry import ApplicationRegistry
from apps.accounts.services.authorization_service import AuthorizationService


class CargaOrgLotConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not await self._authorized():
            await self.close(code=4403)
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

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def carga_event(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _authorized(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return False
        application = ApplicationRegistry().get("CARGA_ORG_LOT")
        return AuthorizationService(user, application).can(
            "view_importacaoplanilha"
        )
