from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.db.models import Q
from asgiref.sync import sync_to_async
from .models import MessageThread, PurchaseRequest


class MessageThreadConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        kwargs = self.scope.get("url_route", {}).get("kwargs", {})
        thread_id = int(kwargs.get("thread_id", 0) or 0)
        if not user or not getattr(user, "is_authenticated", False) or thread_id <= 0:
            await self.close()
            return
        is_participant = await sync_to_async(
            lambda: MessageThread.objects.filter(pk=thread_id).filter(Q(buyer_id=user.id) | Q(seller_id=user.id)).exists()
        )()
        if not is_participant:
            await self.close()
            return
        self.thread_group = f"thread_{thread_id}"
        await self.channel_layer.group_add(self.thread_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        try:
            if hasattr(self, "thread_group"):
                await self.channel_layer.group_discard(self.thread_group, self.channel_name)
        except Exception:
            pass

    async def thread_message_event(self, event):
        await self.send_json(event.get("data", {}))

    async def request_status_event(self, event):
        await self.send_json(event.get("data", {}))


class RequestMessageConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        kwargs = self.scope.get("url_route", {}).get("kwargs", {})
        request_id = int(kwargs.get("request_id", 0) or 0)
        if not user or not getattr(user, "is_authenticated", False) or request_id <= 0:
            await self.close()
            return
        is_participant = await sync_to_async(
            lambda: PurchaseRequest.objects.filter(pk=request_id).filter(Q(buyer_id=user.id) | Q(seller_id=user.id)).exists()
        )()
        if not is_participant:
            await self.close()
            return
        self.request_group = f"request_{request_id}"
        await self.channel_layer.group_add(self.request_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        try:
            if hasattr(self, "request_group"):
                await self.channel_layer.group_discard(self.request_group, self.channel_name)
        except Exception:
            pass

    async def request_message_event(self, event):
        await self.send_json(event.get("data", {}))

    async def request_status_event(self, event):
        await self.send_json(event.get("data", {}))


class UserEventsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.close()
            return
        self.user_group = f"user_{user.id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        try:
            if hasattr(self, "user_group"):
                await self.channel_layer.group_discard(self.user_group, self.channel_name)
        except Exception:
            pass

    async def notification_event(self, event):
        await self.send_json(event.get("data", {}))

    async def counts_event(self, event):
        await self.send_json(event.get("data", {}))

    async def request_status_event(self, event):
        await self.send_json(event.get("data", {}))

    async def transaction_event(self, event):
        await self.send_json(event.get("data", {}))

