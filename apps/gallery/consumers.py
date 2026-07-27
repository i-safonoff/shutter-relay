"""One consumer, one group per album. A consumer never writes to the
database and never talks to S3 -- it only ever relays what
`views.confirm_upload` already decided happened.
"""

from __future__ import annotations

import json

from channels.generic.websocket import AsyncWebsocketConsumer


class AlbumConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        self.group_name = f"album_{self.scope['url_route']['kwargs']['slug']}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        # Channels drops a channel from every group it was ever added to
        # when the channel itself is torn down -- this call is belt and
        # suspenders for the ordinary case, and load-bearing for the case
        # where connect() joined the group but the process crashes before
        # an orderly disconnect, which group_discard handles as a no-op
        # rather than an error.
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Called by the channel layer, not by the browser -- the name matches
    # the "type" field views.py sends with group_send, translated from
    # dots to underscores by Channels' own dispatch convention.
    async def photo_added(self, event: dict) -> None:
        await self.send(text_data=json.dumps({"type": "photo_added", "photo": event["photo"]}))
