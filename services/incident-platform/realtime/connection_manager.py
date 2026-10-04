from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[Any]] = defaultdict(set)

    async def connect(
        self,
        incident_id: UUID,
        websocket: Any,
    ) -> None:
        await websocket.accept()
        self._connections[incident_id].add(websocket)

    def disconnect(
        self,
        incident_id: UUID,
        websocket: Any,
    ) -> None:
        connections = self._connections.get(incident_id)

        if not connections:
            return

        connections.discard(websocket)

        if not connections:
            self._connections.pop(incident_id, None)

    async def broadcast(
        self,
        incident_id: UUID,
        message: dict[str, Any],
    ) -> int:
        connections = list(
            self._connections.get(incident_id, set())
        )

        delivered = 0
        failed = []

        for websocket in connections:
            try:
                await websocket.send_json(message)
                delivered += 1
            except Exception:
                failed.append(websocket)

        for websocket in failed:
            self.disconnect(incident_id, websocket)

        return delivered

    def connection_count(self, incident_id: UUID) -> int:
        return len(
            self._connections.get(incident_id, set())
        )
