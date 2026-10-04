from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from models.incident import Incident
from incident_lifecycle import IncidentStatus
from api.incident_api import IncidentAPI


class FakeStore:
    def __init__(self):
        self.incidents = {}
        self.events = {}

    def create_incident(self, incident):
        self.incidents[incident.incident_id] = incident.to_dict()
        self.events[incident.incident_id] = []

        return self.incidents[incident.incident_id]

    def get_incident(self, incident_id):
        return self.incidents.get(incident_id)

    def list_incidents(self, status=None, priority=None):
        values = list(self.incidents.values())

        if status:
            values = [
                item for item in values
                if item["status"] == status
            ]

        if priority:
            values = [
                item for item in values
                if item["priority"] == priority
            ]

        return values

    def update_status(
        self,
        incident_id,
        current_version,
        status,
        resolved_at=None,
    ):
        incident = self.incidents.get(incident_id)

        if incident is None:
            return None

        if incident["version"] != current_version:
            return None

        incident["status"] = status
        incident["version"] += 1
        incident["updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        incident["resolved_at"] = (
            resolved_at.isoformat()
            if resolved_at
            else None
        )

        return incident

    def append_event(
        self,
        incident_id,
        event_id,
        event_type,
        payload,
        occurred_at=None,
    ):
        event = {
            "event_id": str(event_id),
            "incident_id": str(incident_id),
            "event_type": event_type,
            "sequence": len(self.events[incident_id]) + 1,
            "payload": payload,
        }

        self.events[incident_id].append(event)

        return event

    def get_timeline(
        self,
        incident_id,
        after_sequence=0,
    ):
        return [
            event
            for event in self.events[incident_id]
            if event["sequence"] > after_sequence
        ]


def build_api():
    return IncidentAPI(FakeStore())


def test_create_incident():
    api = build_api()

    result = api.create_incident(
        title="Product latency degradation",
        priority="P1",
        affected_services=[
            "ii-product-service",
            "ii-postgres",
        ],
        primary_suspect="ii-postgres",
        confidence=0.91,
    )

    assert result["title"] == "Product latency degradation"
    assert result["status"] == "DETECTED"
    assert result["priority"] == "P1"
    assert result["version"] == 1
    assert result["primary_suspect"] == "ii-postgres"


def test_create_rejects_invalid_priority():
    api = build_api()

    try:
        api.create_incident(
            title="Invalid priority",
            priority="URGENT",
        )
        assert False
    except ValueError:
        pass


def test_create_rejects_invalid_confidence():
    api = build_api()

    try:
        api.create_incident(
            title="Invalid confidence",
            priority="P1",
            confidence=1.5,
        )
        assert False
    except ValueError:
        pass


def test_status_transition_is_enforced():
    api = build_api()

    incident = api.create_incident(
        title="Database failure",
        priority="P0",
    )

    incident_id = UUID(incident["incident_id"])

    updated = api.change_status(
        incident_id,
        "ACKNOWLEDGED",
        1,
    )

    assert updated["status"] == "ACKNOWLEDGED"
    assert updated["version"] == 2


def test_invalid_status_transition_is_rejected():
    api = build_api()

    incident = api.create_incident(
        title="Database failure",
        priority="P0",
    )

    incident_id = UUID(incident["incident_id"])

    try:
        api.change_status(
            incident_id,
            "RESOLVED",
            1,
        )
        assert False
    except ValueError:
        pass


def test_version_conflict_is_rejected():
    api = build_api()

    incident = api.create_incident(
        title="Version conflict",
        priority="P1",
    )

    incident_id = UUID(incident["incident_id"])

    api.change_status(
        incident_id,
        "ACKNOWLEDGED",
        1,
    )

    try:
        api.change_status(
            incident_id,
            "TRIAGED",
            1,
        )
        assert False
    except RuntimeError:
        pass


def test_timeline_is_persisted_after_status_change():
    api = build_api()

    incident = api.create_incident(
        title="Timeline persistence",
        priority="P2",
    )

    incident_id = UUID(incident["incident_id"])

    api.change_status(
        incident_id,
        "ACKNOWLEDGED",
        1,
    )

    timeline = api.timeline(incident_id)

    assert len(timeline) == 1
    assert timeline[0]["event_type"] == (
        "INCIDENT_STATUS_CHANGED"
    )
    assert timeline[0]["sequence"] == 1


def test_full_lifecycle():
    api = build_api()

    incident = api.create_incident(
        title="Full lifecycle",
        priority="P1",
    )

    incident_id = UUID(incident["incident_id"])

    version = 1

    for status in [
        "ACKNOWLEDGED",
        "TRIAGED",
        "INVESTIGATING",
        "MITIGATING",
        "RECOVERY_VERIFY",
        "RESOLVED",
    ]:
        result = api.change_status(
            incident_id,
            status,
            version,
        )

        version += 1

        assert result["status"] == status
        assert result["version"] == version

    assert result["resolved_at"] is not None

    timeline = api.timeline(incident_id)

    assert len(timeline) == 6
    assert [
        event["sequence"]
        for event in timeline
    ] == list(range(1, 7))


def test_filter_incidents():
    api = build_api()

    api.create_incident(
        title="P0 failure",
        priority="P0",
    )

    api.create_incident(
        title="P2 degradation",
        priority="P2",
    )

    p0 = api.list_incidents(
        priority="P0",
    )

    assert len(p0) == 1
    assert p0[0]["title"] == "P0 failure"


def test_incident_not_found():
    api = build_api()

    try:
        api.change_status(
            uuid4(),
            "ACKNOWLEDGED",
            1,
        )
        assert False
    except KeyError:
        pass
