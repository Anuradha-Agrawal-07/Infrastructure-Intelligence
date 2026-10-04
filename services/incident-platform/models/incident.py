from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from incident_lifecycle import IncidentStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Incident:
    title: str
    priority: str
    incident_id: UUID = field(default_factory=uuid4)
    status: IncidentStatus = IncidentStatus.DETECTED
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    resolved_at: datetime | None = None
    version: int = 1
    affected_services: list[str] = field(default_factory=list)
    primary_suspect: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict:
        return {
            "incident_id": str(self.incident_id),
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": (
                self.resolved_at.isoformat()
                if self.resolved_at
                else None
            ),
            "affected_services": self.affected_services,
            "primary_suspect": self.primary_suspect,
            "confidence": self.confidence,
            "version": self.version,
        }
