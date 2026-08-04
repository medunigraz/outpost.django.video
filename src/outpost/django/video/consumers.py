import logging

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import JsonWebsocketConsumer

from . import models

logger = logging.getLogger(__name__)


class PlayerConsumer(JsonWebsocketConsumer):

    # Set to True if you want it, else leave it out
    strict_ordering = False
    channel_session_user = True

    def connect(self, **kwargs):
        """
        Perform things on connection start
        """
        slug = self.scope.get("url_route").get("kwargs").get("slug")
        try:
            self.event = models.PushLiveEvent.objects.get(slug=slug)
        except models.PushLiveEvent.DoesNotExist:
            logger.warn(f"Unknown event {slug}")
            return
        self.accept()
        async_to_sync(self.channel_layer.group_add)(self.event.group, self.channel_name)
        if self.event.is_live():
            self.send(
                {"type": "event.start", "player": self.event.player}
            )
        logger.debug(f"Connected player for event {self.event}")

    def disconnect(self, message, **kwargs):
        """
        Perform things on connection close
        """
        async_to_sync(self.channel_layer.group_discard)(self.event.group, self.channel_name)
        logger.debug(f"Disconnected player for event {self.event}")

    def receive_json(self, content, **kwargs):
        """
        Called when a message is received with decoded JSON content
        """
        # Simple echo
        if content.get("type") == "chat.publish":
            if not self.event.chat:
                logger.warning(f"Received published but event {self.event} chat disabled")
                return
            async_to_sync(self.channel_layer.group_send)(
                self.event.group,
                {
                    'type': 'chat.message',
                    'message': content.get("message")
                }
            )
