from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any

from realtime.events import RealtimeEvent


class RealtimeService:
    """
    Durable-first incident event service.

    Required ordering:
        PostgreSQL commit
            ->
        Redis publish
            ->
        WebSocket broadcast
    """

    def __init__(
        self,
        event_store,
        redis_fanout=None,
        connection_manager=None,
    ):
        self.event_store = event_store
        self.redis_fanout = redis_fanout
        self.connection_manager = connection_manager

    def create_event(
        self,
        incident_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        producer: str = "incident-platform",
    ) -> RealtimeEvent:
        latest = self.event_store.latest(incident_id)

        next_sequence = (
            latest.sequence + 1
            if latest is not None
            else 1
        )

        return RealtimeEvent(
            event_id=uuid4(),
            event_type=event_type,
            incident_id=incident_id,
            sequence=next_sequence,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
            producer=producer,
        )

    async def persist_and_publish(
        self,
        event: RealtimeEvent,
    ) -> RealtimeEvent:
        # STEP 1: durable PostgreSQL persistence.
        persisted = self.event_store.append(event)

        # STEP 2: Redis fan-out.
        if self.redis_fanout is not None:
            await self.redis_fanout.publish(persisted)

        # STEP 3: local WebSocket broadcast.
        if self.connection_manager is not None:
            await self.connection_manager.broadcast(
                persisted.incident_id,
                persisted.to_ws_message(),
            )

        return persisted

    def catch_up(
        self,
        incident_id: UUID,
        after_sequence: int = 0,
    ) -> list[RealtimeEvent]:
        return self.event_store.list_since(
            incident_id,
            after_sequence,
        )
