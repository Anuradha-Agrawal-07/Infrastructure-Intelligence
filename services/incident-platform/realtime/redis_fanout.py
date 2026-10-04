from __future__ import annotations

import json
from typing import Any

from redis import asyncio as redis


class RedisFanout:
    """
    Redis pub/sub adapter.

    Redis is fanout only.
    PostgreSQL/EventStore remains the durable source of truth.
    """

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self.url = url
        self.client: redis.Redis | None = None

    async def connect(self) -> None:
        if self.client is None:
            self.client = redis.from_url(
                self.url,
                decode_responses=True,
            )
            await self.client.ping()

    async def publish(
        self,
        incident_id: str,
        message: dict[str, Any],
    ) -> int:
        await self.connect()

        assert self.client is not None

        channel = f"incident:{incident_id}"

        return await self.client.publish(
            channel,
            json.dumps(message),
        )

    async def subscribe(self, incident_id: str):
        await self.connect()

        assert self.client is not None

        pubsub = self.client.pubsub()
        await pubsub.subscribe(f"incident:{incident_id}")

        return pubsub

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None
