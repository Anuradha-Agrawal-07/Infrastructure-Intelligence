from __future__ import annotations

import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]

if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import FastAPI

from api.incident_api import IncidentAPI
from api.intelligence_api import build_intelligence_router
from database.postgres_store import PostgresIncidentStore

from realtime.connection_manager import ConnectionManager
from realtime.postgres_event_store import PostgresRealtimeEventStore
from realtime.redis_fanout import RedisFanout
from realtime.realtime_service import RealtimeService
from realtime.websocket_router import build_realtime_router


def create_app(
    store=None,
    realtime_service=None,
):
    app = FastAPI(
        title="Infrastructure Intelligence Incident Platform",
        version="0.3.0",
    )

    if store is None:
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/infrastructure_intelligence",
        )

        store = PostgresIncidentStore(
            database_url,
        )

    incident_api = IncidentAPI(store)

    if realtime_service is None:
        event_store = PostgresRealtimeEventStore(
            store,
        )

        connection_manager = ConnectionManager()
        redis_fanout = RedisFanout()

        realtime_service = RealtimeService(
            event_store=event_store,
            redis_fanout=redis_fanout,
            connection_manager=connection_manager,
        )
    else:
        connection_manager = realtime_service.connection_manager

        if connection_manager is None:
            connection_manager = ConnectionManager()
            realtime_service.connection_manager = (
                connection_manager
            )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "incident-platform",
            "realtime": True,
        }

    @app.post("/api/incidents")
    def create_incident(payload: dict):
        return incident_api.create_incident(
            title=payload["title"],
            priority=payload.get(
                "priority",
                "P2",
            ),
            affected_services=payload.get(
                "affected_services",
                [],
            ),
            primary_suspect=payload.get(
                "primary_suspect",
            ),
            confidence=payload.get(
                "confidence",
            ),
        )

    @app.get("/api/incidents")
    def list_incidents(
        priority: str | None = None,
        status: str | None = None,
    ):
        return incident_api.list_incidents(
            priority=priority,
            status=status,
        )

    @app.get("/api/incidents/{incident_id}")
    def get_incident(incident_id):
        return incident_api.get_incident(
            incident_id,
        )

    @app.patch("/api/incidents/{incident_id}/status")
    def change_status(
        incident_id,
        payload: dict,
    ):
        return incident_api.change_status(
            incident_id,
            payload["status"],
            payload["version"],
        )

    @app.get("/api/incidents/{incident_id}/timeline")
    def timeline(incident_id):
        return incident_api.timeline(
            incident_id,
        )

    realtime_router = build_realtime_router(
        realtime_service,
        connection_manager,
    )

    app.include_router(
        realtime_router,
    )

    intelligence_router = build_intelligence_router(
        incident_api=incident_api,
        realtime_service=realtime_service,
        store=store,
    )

    app.include_router(intelligence_router)
    return app


app = create_app()

# ============================================================
# Incident Room UI / Collaboration integration
# ============================================================

from pathlib import Path as _IncidentRoomPath

from fastapi.middleware.cors import CORSMiddleware as _IncidentRoomCORS
from fastapi.staticfiles import StaticFiles as _IncidentRoomStaticFiles

from api.collaboration_api import router as _incident_room_router

try:
    app.add_middleware(
        _IncidentRoomCORS,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
except RuntimeError:
    pass

app.include_router(_incident_room_router)

_incident_room_root = (
    _IncidentRoomPath(__file__).resolve().parents[3]
    / "frontend"
)

if _incident_room_root.exists():
    app.mount(
        "/incident-room",
        _IncidentRoomStaticFiles(
            directory=str(_incident_room_root),
            html=True,
        ),
        name="incident-room",
    )

# Phase 5 scenario execution + recovery API
try:
    from api.scenario_api import router as scenario_router
except ImportError:
    from scenario_api import router as scenario_router

app.include_router(scenario_router)
