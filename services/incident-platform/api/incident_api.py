from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from incident_lifecycle import (
    IncidentStatus,
    InvalidIncidentTransition,
    transition,
)
from models.incident import Incident


def utc_now():
    return datetime.now(timezone.utc)


class IncidentAPI:
    """
    Application service for Incident Platform REST operations.

    The HTTP framework can call these methods directly.
    Keeping the business logic here makes the state machine testable
    independently of FastAPI/Flask.
    """

    def __init__(self, store):
        self.store = store

    def create_incident(
        self,
        title: str,
        priority: str,
        affected_services: list[str] | None = None,
        primary_suspect: str | None = None,
        confidence: float | None = None,
    ) -> dict:

        if not title.strip():
            raise ValueError("title is required")

        if priority not in {"P0", "P1", "P2", "P3"}:
            raise ValueError("priority must be P0, P1, P2 or P3")

        if confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

        incident = Incident(
            title=title,
            priority=priority,
            affected_services=affected_services or [],
            primary_suspect=primary_suspect,
            confidence=confidence,
        )

        self.store.create_incident(incident)

        return incident.to_dict()

    def get_incident(self, incident_id: UUID) -> dict | None:
        return self.store.get_incident(incident_id)

    def list_incidents(
        self,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[dict]:

        if status:
            IncidentStatus(status)

        if priority and priority not in {"P0", "P1", "P2", "P3"}:
            raise ValueError("invalid priority")

        return self.store.list_incidents(
            status=status,
            priority=priority,
        )

    def change_status(
        self,
        incident_id: UUID,
        target_status: str,
        expected_version: int,
    ) -> dict:

        current = self.store.get_incident(incident_id)

        if current is None:
            raise KeyError(f"Incident not found: {incident_id}")

        current_status = IncidentStatus(current["status"])
        target = IncidentStatus(target_status)

        next_status = transition(
            current_status,
            target,
        )

        resolved_at = (
            utc_now()
            if next_status == IncidentStatus.RESOLVED
            else None
        )

        updated = self.store.update_status(
            incident_id=incident_id,
            current_version=expected_version,
            status=next_status.value,
            resolved_at=resolved_at,
        )

        if updated is None:
            raise RuntimeError(
                "Incident version conflict. "
                "Reload the incident before changing its status."
            )

        event_id = uuid4()

        self.store.append_event(
            incident_id=incident_id,
            event_id=event_id,
            event_type="INCIDENT_STATUS_CHANGED",
            payload={
                "from_status": current_status.value,
                "to_status": next_status.value,
                "version": updated["version"],
            },
        )

        return updated

    def timeline(
        self,
        incident_id: UUID,
        after_sequence: int = 0,
    ) -> list[dict]:

        incident = self.store.get_incident(incident_id)

        if incident is None:
            raise KeyError(f"Incident not found: {incident_id}")

        return self.store.get_timeline(
            incident_id,
            after_sequence,
        )
