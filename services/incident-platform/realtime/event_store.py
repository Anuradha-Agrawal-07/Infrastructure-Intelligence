from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EventStoreError(Exception):
    pass


class DuplicateEventError(EventStoreError):
    pass


class NonMonotonicSequenceError(ValueError):
    pass


@dataclass
class StoredEvent:
    event_id: str
    event_type: str
    incident_id: str
    sequence: int
    payload: dict[str, Any]
    occurred_at: str
    producer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "incident_id": str(self.incident_id),
            "sequence": self.sequence,
            "payload": self.payload,
            "occurred_at": self.occurred_at,
            "producer": self.producer,
        }


class EventStore:
    def __init__(self) -> None:
        self._events: dict[str, list[StoredEvent]] = {}
        self._by_id: dict[str, StoredEvent] = {}

    def append(self, event: StoredEvent) -> StoredEvent:
        event_id = str(event.event_id)
        incident_id = str(event.incident_id)

        if event_id in self._by_id:
            existing = self._by_id[event_id]

            if existing.to_dict() != event.to_dict():
                raise DuplicateEventError(
                    f"event_id already exists with different payload: {event_id}"
                )

            return existing

        events = self._events.setdefault(incident_id, [])

        if events:
            expected = events[-1].sequence + 1

            if event.sequence != expected:
                raise NonMonotonicSequenceError(
                    f"expected sequence {expected}, got {event.sequence}"
                )

        elif event.sequence < 1:
            raise NonMonotonicSequenceError(
                f"first sequence must be >= 1, got {event.sequence}"
            )

        events.append(event)
        self._by_id[event_id] = event

        return event

    def latest(self, incident_id: str) -> StoredEvent | None:
        events = self._events.get(str(incident_id), [])
        return events[-1] if events else None

    def list_since(
        self,
        incident_id: str,
        after_sequence: int = 0,
    ) -> list[StoredEvent]:
        return [
            event
            for event in self._events.get(str(incident_id), [])
            if event.sequence > after_sequence
        ]

    def latest_sequence(self, incident_id: str) -> int:
        latest = self.latest(incident_id)
        return latest.sequence if latest else 0

    def get_by_id(self, event_id: str) -> StoredEvent | None:
        return self._by_id.get(str(event_id))

    def count(self, incident_id: str) -> int:
        return len(self._events.get(str(incident_id), []))