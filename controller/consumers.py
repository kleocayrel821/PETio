from channels.generic.websocket import AsyncJsonWebsocketConsumer

class DeviceStatusConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("device_status", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("device_status", self.channel_name)

    async def device_status_event(self, event):
        # event = {"type": "device_status_event", "data": {...}}
        await self.send_json(event.get("data", {}))

    async def receive_json(self, content, **kwargs):
        # No-op for now; clients only receive pushes
        pass


class FeedingLogConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("feeding_logs", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("feeding_logs", self.channel_name)

    async def feeding_log_event(self, event):
        # event = {"type": "feeding_log_event", "data": {...}}
        await self.send_json(event.get("data", {}))

    async def receive_json(self, content, **kwargs):
        # No-op for now; clients only receive pushes
        pass