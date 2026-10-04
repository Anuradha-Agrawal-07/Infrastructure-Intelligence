import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest


SERVICE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "incident-platform"
)

if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


from api.intelligence_api import (  # noqa: E402
    build_incident_title,
    priority_from_severity,
)


def anomaly_event(
    severity="high",
    service_id="order-service",
    metric="request_latency_ms",
):
    return {
        "event_id": str(uuid4()),
        "event_type": "ANOMALY_DETECTED",
        "schema_version": 1,
        "occurred_at": "2026-10-04T12:00:00Z",
        "producer": "intelligence-engine",
        "correlation_id": str(uuid4()),
        "incident_id": None,
        "payload": {
            "anomaly_id": str(uuid4()),
            "service_id": service_id,
            "metric": metric,
            "observed_value": 900.0,
            "expected_value": 100.0,
            "deviation": 8.0,
            "detector": "rolling_zscore",
            "severity": severity,
            "confidence": 0.96,
            "window_start": "2026-10-04T11:59:00Z",
            "window_end": "2026-10-04T12:00:00Z",
        },
    }


def test_severity_to_priority_mapping():
    assert priority_from_severity("critical") == "P0"
    assert priority_from_severity("high") == "P1"
    assert priority_from_severity("medium") == "P2"
    assert priority_from_severity("low") == "P3"
    assert priority_from_severity("unknown") == "P2"


def test_incident_title_mapping():
    event = anomaly_event()

    assert (
        build_incident_title(event["payload"])
        == "order-service: request_latency_ms anomaly detected"
    )


@pytest.mark.asyncio
async def test_anomaly_creates_incident_and_realtime_events():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from realtime.realtime_service import RealtimeService

    class FakeStore:
        def __init__(self):
            self.incident = None
            self.events = []
            self.anomalies = []

        def create_incident(self, incident):
            self.incident = incident.to_dict()
            return self.incident

        def create_anomaly(self, incident_id, anomaly):
            row = {
                "id": anomaly["anomaly_id"],
                "incident_id": str(incident_id),
                "payload": anomaly,
            }
            self.anomalies.append(row)
            return row

        def get_incident(self, incident_id):
            return self.incident

        def get_incident_by_event_id(self, event_id):
            target = str(event_id)

            for event in self.events:
                if str(event["event_id"]) == target:
                    return self.incident

            return None

        def append_event(
            self,
            incident_id,
            event_id,
            event_type,
            payload,
            occurred_at=None,
        ):
            event = {
                "incident_id": str(incident_id),
                "event_id": str(event_id),
                "event_type": event_type,
                "payload": payload,
            }
            self.events.append(event)
            return event

        def get_timeline(self, incident_id, after_sequence=0):
            return self.events

        def update_status(
            self,
            incident_id,
            current_version,
            status,
            resolved_at=None,
        ):
            return self.incident

    class FakeEventStore:
        def __init__(self):
            self.events = []

        def latest(self, incident_id):
            matching = [
                event
                for event in self.events
                if str(event.incident_id) == str(incident_id)
            ]
            return matching[-1] if matching else None

        def append(self, event):
            self.events.append(event)
            return event

        def list_since(self, incident_id, after_sequence=0):
            return [
                event
                for event in self.events
                if str(event.incident_id) == str(incident_id)
                and event.sequence > after_sequence
            ]

    class FakeRedis:
        async def publish(self, event):
            return None

    class FakeConnections:
        def __init__(self):
            self.messages = []

        async def broadcast(self, incident_id, message):
            self.messages.append(message)

    store = FakeStore()
    event_store = FakeEventStore()
    connections = FakeConnections()

    realtime = RealtimeService(
        event_store=event_store,
        redis_fanout=FakeRedis(),
        connection_manager=connections,
    )

    app = create_app(
        store=store,
        realtime_service=realtime,
    )

    client = TestClient(app)

    event = anomaly_event()

    response = client.post(
        "/api/intelligence/events",
        json=event,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["created"] is True
    assert body["duplicate"] is False
    assert body["incident"]["status"] == "DETECTED"
    assert body["incident"]["priority"] == "P1"
    assert body["incident"]["affected_services"] == ["order-service"]

    # Durable anomaly domain record.
    assert len(store.anomalies) == 1
    assert store.anomalies[0]["incident_id"] == body["incident"]["incident_id"]

    # Two lifecycle/realtime events.
    assert len(event_store.events) == 2

    event_types = [
        event.event_type
        for event in event_store.events
    ]

    assert event_types == [
        "INCIDENT_CREATED",
        "ANOMALY_DETECTED",
    ]

    # Original intelligence event_id is preserved.
    anomaly_realtime_event = event_store.events[1]

    assert str(anomaly_realtime_event.event_id) == event["event_id"]

    # Both were broadcast.
    assert len(connections.messages) == 2


@pytest.mark.asyncio
async def test_duplicate_anomaly_event_is_idempotent():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from realtime.realtime_service import RealtimeService

    class FakeStore:
        def __init__(self):
            self.incidents = []
            self.events = []
            self.anomalies = []

        def create_incident(self, incident):
            row = incident.to_dict()
            self.incidents.append(row)
            return row

        def create_anomaly(self, incident_id, anomaly):
            row = {
                "id": anomaly["anomaly_id"],
                "incident_id": str(incident_id),
                "payload": anomaly,
            }
            self.anomalies.append(row)
            return row

        def get_incident(self, incident_id):
            for incident in self.incidents:
                if incident["incident_id"] == str(incident_id):
                    return incident
            return None

        def get_incident_by_event_id(self, event_id):
            target = str(event_id)

            for event in self.events:
                if str(event["event_id"]) == target:
                    for incident in self.incidents:
                        if incident["incident_id"] == event["incident_id"]:
                            return incident

            return None

        def append_event(
            self,
            incident_id,
            event_id,
            event_type,
            payload,
            occurred_at=None,
        ):
            event = {
                "incident_id": str(incident_id),
                "event_id": str(event_id),
                "event_type": event_type,
                "payload": payload,
            }
            self.events.append(event)
            return event

        def get_timeline(self, incident_id, after_sequence=0):
            return self.events

        def update_status(
            self,
            incident_id,
            current_version,
            status,
            resolved_at=None,
        ):
            return self.get_incident(incident_id)

    class FakeEventStore:
        def __init__(self, store):
            self.store = store
            self.events = []

        def latest(self, incident_id):
            matching = [
                event
                for event in self.events
                if str(event.incident_id) == str(incident_id)
            ]
            return matching[-1] if matching else None

        def append(self, event):
            self.events.append(event)
            self.store.events.append({
                "incident_id": str(event.incident_id),
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "payload": event.payload,
            })
            return event

        def list_since(self, incident_id, after_sequence=0):
            return []

    class FakeRedis:
        async def publish(self, event):
            return None

    class FakeConnections:
        def __init__(self):
            self.messages = []

        async def broadcast(self, incident_id, message):
            self.messages.append(message)

    store = FakeStore()
    event_store = FakeEventStore(store)
    connections = FakeConnections()

    realtime = RealtimeService(
        event_store=event_store,
        redis_fanout=FakeRedis(),
        connection_manager=connections,
    )

    app = create_app(
        store=store,
        realtime_service=realtime,
    )

    client = TestClient(app)

    event = anomaly_event()

    first = client.post(
        "/api/intelligence/events",
        json=event,
    )

    second = client.post(
        "/api/intelligence/events",
        json=event,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_body = first.json()
    second_body = second.json()

    assert first_body["created"] is True
    assert first_body["duplicate"] is False

    assert second_body["created"] is False
    assert second_body["duplicate"] is True

    # Exactly one incident.
    assert len(store.incidents) == 1

    # Exactly one anomaly.
    assert len(store.anomalies) == 1

    # Exactly two realtime events:
    # INCIDENT_CREATED + ANOMALY_DETECTED.
    assert len(event_store.events) == 2

    # Duplicate request caused no additional broadcast.
    assert len(connections.messages) == 2

    # Both responses point to the same incident.
    assert (
        first_body["incident"]["incident_id"]
        == second_body["incident"]["incident_id"]
    )


def test_anomaly_integration_file_compiles():
    source = (
        Path(__file__).resolve().parents[3]
        / "services"
        / "incident-platform"
        / "api"
        / "intelligence_api.py"
    )

    compile(
        source.read_text(encoding="utf-8"),
        str(source),
        "exec",
    )