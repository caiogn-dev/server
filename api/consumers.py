import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class AdminUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not user.is_staff:
            logger.warning("Admin WS denied: user=%s", getattr(user, "email", "anonymous"))
            await self.close(code=4403)
            return

        await self.channel_layer.group_add("admin_updates", self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected"})

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("admin_updates", self.channel_name)

    async def admin_event(self, event):
        await self.send_json(
            {
                "event": event.get("event"),
                "payload": event.get("payload"),
            }
        )
