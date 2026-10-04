from __future__ import annotations

from realtime.event_store import StoredEvent
from database.postgres_store import PostgresIncidentStore


class PostgresRealtimeEventStore:
    def __init__(self, store: PostgresIncidentStore) -> None:
        self.store = store

    def append(self, event: StoredEvent) -> StoredEvent:
        self.store.append_event(
            incident_id=event.incident_id,
            event_type=event.event_type,
            payload=event.to_dict(),
            event_id=event.event_id,
        )

        return event

    def latest(self, incident_id: str) -> StoredEvent | None:
        timeline = self.store.get_timeline(incident_id)

        if not timeline:
            return None

        item = timeline[-1]

        return StoredEvent(
            event_id=str(item["event_id"]),
            event_type=item["event_type"],
            incident_id=str(incident_id),
            sequence=int(item["sequence"]),
            payload=item.get("payload", {}),
            occurred_at=str(item["occurred_at"]),
            producer=item.get("producer", "incident-platform"),
        )

    def list_since(
        self,
        incident_id: str,
        after_sequence: int = 0,
    ) -> list[StoredEvent]:

        timeline = self.store.get_timeline(incident_id)

        events: list[StoredEvent] = []

        for item in timeline:
            sequence = int(item["sequence"])

            if sequence <= after_sequence:
                continue

            events.append(
                StoredEvent(
                    event_id=str(item["event_id"]),
                    event_type=item["event_type"],
                    incident_id=str(incident_id),
                    sequence=sequence,
                    payload=item.get("payload", {}),
                    occurred_at=str(item["occurred_at"]),
                    producer=item.get("producer", "incident-platform"),
                )
            )

        return events

    def latest_sequence(self, incident_id: str) -> int:
        latest = self.latest(incident_id)
        return latest.sequence if latest else 0