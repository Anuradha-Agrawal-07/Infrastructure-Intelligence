from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from models.incident import Incident, utc_now
from incident_lifecycle import IncidentStatus, transition


@dataclass
class IncidentEvent:
    event_id: UUID
    incident_id: UUID
    event_type: str
    sequence: int
    occurred_at: datetime
    payload: dict


class IncidentRepository:
    def __init__(self) -> None:
        self._incidents: dict[UUID, Incident] = {}
        self._events: dict[UUID, list[IncidentEvent]] = {}

    def create(self, incident: Incident) -> Incident:
        if incident.incident_id in self._incidents:
            raise ValueError("Incident already exists")

        self._incidents[incident.incident_id] = incident
        self._events[incident.incident_id] = []

        return incident

    def get(self, incident_id: UUID) -> Incident | None:
        return self._incidents.get(incident_id)

    def list(self) -> list[Incident]:
        return list(self._incidents.values())

    def change_status(
        self,
        incident_id: UUID,
        target: IncidentStatus | str,
        event_id: UUID,
        payload: dict | None = None,
    ) -> Incident:
        incident = self._incidents.get(incident_id)

        if incident is None:
            raise KeyError(f"Incident not found: {incident_id}")

        next_status = transition(incident.status, target)

        incident.status = next_status
        incident.updated_at = utc_now()
        incident.version += 1

        if next_status == IncidentStatus.RESOLVED:
            incident.resolved_at = incident.updated_at

        events = self._events[incident_id]

        event = IncidentEvent(
            event_id=event_id,
            incident_id=incident_id,
            event_type="INCIDENT_STATUS_CHANGED",
            sequence=len(events) + 1,
            occurred_at=incident.updated_at,
            payload={
                "from_status": (
                    incident.status.value
                    if False
                    else None
                ),
                "to_status": next_status.value,
                **(payload or {}),
            },
        )

        events.append(event)

        return incident

    def timeline(self, incident_id: UUID) -> list[IncidentEvent]:
        if incident_id not in self._incidents:
            raise KeyError(f"Incident not found: {incident_id}")

        return list(self._events[incident_id])
