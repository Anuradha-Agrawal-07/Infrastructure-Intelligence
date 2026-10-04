from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from redis import asyncio as redis


def _json_default(value: Any):
    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    raise TypeError(
        f"Object of type {type(value).__name__} "
        "is not JSON serializable"
    )


class RedisFanout:

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
    ):
        self.url = url
        self.client = None

    async def connect(self):
        if self.client is None:
            self.client = redis.from_url(
                self.url,
                decode_responses=True,
            )
            await self.client.ping()

    async def publish(
        self,
        event_or_incident_id,
        message=None,
    ):
        await self.connect()

        if message is None:
            event = event_or_incident_id
            incident_id = str(event.incident_id)
            message = event.to_ws_message()
        else:
            incident_id = str(event_or_incident_id)

        return await self.client.publish(
            f"incident:{incident_id}",
            json.dumps(
                message,
                default=_json_default,
            ),
        )

    async def subscribe(self, incident_id):
        await self.connect()

        pubsub = self.client.pubsub()

        await pubsub.subscribe(
            f"incident:{incident_id}"
        )

        return pubsub

    async def close(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None
