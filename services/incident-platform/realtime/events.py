from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class RealtimeEvent:
    event_id: UUID
    event_type: str
    incident_id: UUID
    sequence: int
    payload: dict[str, Any]
    occurred_at: datetime
    producer: str = "incident-platform"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "incident_id": str(self.incident_id),
            "sequence": self.sequence,
            "occurred_at": self.occurred_at.astimezone(
                timezone.utc
            ).isoformat(),
            "producer": self.producer,
            "payload": self.payload,
        }

    def to_ws_message(self) -> dict[str, Any]:
        return {
            "type": "EVENT",
            "message_id": str(self.event_id),
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "incident_id": str(self.incident_id),
            "sequence": self.sequence,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "payload": self.payload,
        }
