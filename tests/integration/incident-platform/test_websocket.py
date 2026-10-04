from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "services" / "incident-platform"

if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from api.app import create_app
from realtime.events import RealtimeEvent
from realtime.connection_manager import ConnectionManager
from realtime.realtime_service import RealtimeService
from realtime.event_store import EventStore


class FakeRealtimeService:
    def __init__(self):
        self.store = EventStore()
        self.connection_manager = ConnectionManager()

    def catch_up(
        self,
        incident_id,
        after_sequence=0,
    ):
        return self.store.list_since(
            incident_id,
            after_sequence,
        )


class FakeStore:
    def __init__(self):
        self.incidents = {}

    def create(self, incident):
        self.incidents[incident.incident_id] = incident
        return incident

    def get(self, incident_id):
        return self.incidents.get(incident_id)

    def list(self, priority=None, status=None):
        result = list(self.incidents.values())

        if priority is not None:
            result = [
                x for x in result
                if x.priority == priority
            ]

        if status is not None:
            result = [
                x for x in result
                if x.status.value == status
            ]

        return result

    def change_status(
        self,
        incident_id,
        status,
        expected_version,
    ):
        incident = self.incidents[incident_id]
        incident.status = status
        incident.version += 1
        return incident

    def timeline(self, incident_id):
        return []


def build_test_app():
    store = FakeStore()

    realtime = FakeRealtimeService()

    app = create_app(
        store=store,
        realtime_service=realtime,
    )

    return app, realtime


@pytest.mark.asyncio
async def test_websocket_catch_up_complete():
    app, realtime = build_test_app()

    incident_id = uuid4()

    for sequence in range(1, 4):
        event = RealtimeEvent(
            event_id=uuid4(),
            event_type="INCIDENT_STATUS_CHANGED",
            incident_id=incident_id,
            sequence=sequence,
            occurred_at=__import__(
                "datetime"
            ).datetime.now(
                __import__("datetime").timezone.utc
            ),
            payload={
                "sequence": sequence,
            },
        )

        realtime.store.append(event)

    client = TestClient(app)

    with client.websocket_connect(
        f"/ws/incidents/{incident_id}"
    ) as websocket:
        websocket.send_json(
            {
                "type": "SUBSCRIBE",
                "incident_id": str(incident_id),
                "last_sequence": 1,
            }
        )

        first = websocket.receive_json()
        second = websocket.receive_json()
        third = websocket.receive_json()

        assert first["type"] == "EVENT"
        assert first["sequence"] == 2

        assert second["type"] == "EVENT"
        assert second["sequence"] == 3

        assert third["type"] == "CATCH_UP_COMPLETE"
        assert third["to_sequence"] == 3


@pytest.mark.asyncio
async def test_websocket_empty_catch_up():
    app, realtime = build_test_app()

    incident_id = uuid4()

    client = TestClient(app)

    with client.websocket_connect(
        f"/ws/incidents/{incident_id}"
    ) as websocket:
        websocket.send_json(
            {
                "type": "SUBSCRIBE",
                "incident_id": str(incident_id),
                "last_sequence": 0,
            }
        )

        message = websocket.receive_json()

        assert message["type"] == "CATCH_UP_COMPLETE"
        assert message["incident_id"] == str(incident_id)
        assert message["from_sequence"] == 0
        assert message["to_sequence"] == 0
