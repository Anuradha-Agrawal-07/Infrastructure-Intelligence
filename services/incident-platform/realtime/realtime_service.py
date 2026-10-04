from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from realtime.events import RealtimeEvent


def _datetime(value):
    if value is None:
        return datetime.now(timezone.utc)

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    value = str(value).replace("Z", "+00:00")
    result = datetime.fromisoformat(value)

    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)

    return result


class RealtimeService:

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
        event_id: UUID | None = None,
        occurred_at=None,
    ) -> RealtimeEvent:

        latest = self.event_store.latest(incident_id)

        sequence = (
            int(latest.sequence) + 1
            if latest is not None
            else 1
        )

        return RealtimeEvent(
            event_id=event_id or uuid4(),
            event_type=event_type,
            incident_id=incident_id,
            sequence=sequence,
            occurred_at=_datetime(occurred_at),
            payload=payload,
            producer=producer,
        )

    async def persist_and_publish(self, event):
        persisted = self.event_store.append(event)

        if self.redis_fanout is not None:
            await self.redis_fanout.publish(persisted)

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
    ):
        return self.event_store.list_since(
            incident_id,
            after_sequence,
        )
