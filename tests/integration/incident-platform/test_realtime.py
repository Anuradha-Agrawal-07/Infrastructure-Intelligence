from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from realtime.connection_manager import ConnectionManager
from realtime.event_store import EventStore
from realtime.events import RealtimeEvent
from realtime.realtime_service import RealtimeService


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages = []
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        if self.closed:
            raise RuntimeError("socket closed")

        self.messages.append(message)


def build_service():
    store = EventStore()
    manager = ConnectionManager()
    service = RealtimeService(
        event_store=store,
        connection_manager=manager,
    )
    return service, store, manager


@pytest.mark.asyncio
async def test_persist_then_broadcast():
    service, store, manager = build_service()

    incident_id = uuid4()
    websocket = FakeWebSocket()

    await manager.connect(
        incident_id,
        websocket,
    )

    event = service.create_event(
        incident_id,
        "INCIDENT_STATUS_CHANGED",
        {
            "from_status": "DETECTED",
            "to_status": "ACKNOWLEDGED",
        },
    )

    await service.persist_and_publish(event)

    assert store.latest_sequence(incident_id) == 1
    assert len(websocket.messages) == 1

    message = websocket.messages[0]

    assert message["type"] == "EVENT"
    assert message["event_id"] == str(event.event_id)
    assert message["sequence"] == 1
    assert message["event_type"] == "INCIDENT_STATUS_CHANGED"


@pytest.mark.asyncio
async def test_sequences_are_monotonic():
    service, store, _ = build_service()

    incident_id = uuid4()

    for index in range(1, 4):
        event = service.create_event(
            incident_id,
            "INCIDENT_STATUS_CHANGED",
            {"index": index},
        )

        await service.persist_and_publish(event)

    events = store.list_since(
        incident_id,
        after_sequence=0,
    )

    assert [event.sequence for event in events] == [
        1,
        2,
        3,
    ]


@pytest.mark.asyncio
async def test_catch_up_after_disconnect():
    service, store, manager = build_service()

    incident_id = uuid4()

    websocket = FakeWebSocket()

    await manager.connect(
        incident_id,
        websocket,
    )

    for index in range(1, 4):
        event = service.create_event(
            incident_id,
            "INCIDENT_STATUS_CHANGED",
            {"index": index},
        )

        await service.persist_and_publish(event)

    manager.disconnect(
        incident_id,
        websocket,
    )

    assert manager.connection_count(incident_id) == 0

    new_websocket = FakeWebSocket()

    await manager.connect(
        incident_id,
        new_websocket,
    )

    missed = service.catch_up(
        incident_id,
        after_sequence=1,
    )

    assert [event.sequence for event in missed] == [
        2,
        3,
    ]


@pytest.mark.asyncio
async def test_reconnect_can_resume_from_last_sequence():
    service, store, manager = build_service()

    incident_id = uuid4()

    for index in range(1, 6):
        event = service.create_event(
            incident_id,
            "INCIDENT_STATUS_CHANGED",
            {"index": index},
        )

        await service.persist_and_publish(event)

    resumed = service.catch_up(
        incident_id,
        after_sequence=3,
    )

    assert [event.sequence for event in resumed] == [
        4,
        5,
    ]


def test_duplicate_event_id_is_idempotent():
    store = EventStore()

    incident_id = uuid4()
    event_id = uuid4()

    event = RealtimeEvent(
        event_id=event_id,
        event_type="ANOMALY_DETECTED",
        incident_id=incident_id,
        sequence=1,
        occurred_at=__import__(
            "datetime"
        ).datetime.now(
            __import__("datetime").timezone.utc
        ),
        payload={"severity": "HIGH"},
    )

    store.append(event)
    store.append(event)

    events = store.list_since(
        incident_id,
        0,
    )

    assert len(events) == 1
    assert events[0].event_id == event_id


def test_non_monotonic_sequence_is_rejected():
    store = EventStore()

    incident_id = uuid4()

    first = RealtimeEvent(
        event_id=uuid4(),
        event_type="ANOMALY_DETECTED",
        incident_id=incident_id,
        sequence=1,
        occurred_at=__import__(
            "datetime"
        ).datetime.now(
            __import__("datetime").timezone.utc
        ),
        payload={},
    )

    second = RealtimeEvent(
        event_id=uuid4(),
        event_type="CORRELATION_RESULT",
        incident_id=incident_id,
        sequence=3,
        occurred_at=__import__(
            "datetime"
        ).datetime.now(
            __import__("datetime").timezone.utc
        ),
        payload={},
    )

    store.append(first)

    with pytest.raises(ValueError):
        store.append(second)
