from __future__ import annotations

import os
from uuid import UUID

try:
    from fastapi import FastAPI, HTTPException, Query
    from pydantic import BaseModel, Field
except ImportError:
    FastAPI = None
    BaseModel = object


class CreateIncidentRequest(BaseModel):
    title: str = Field(min_length=1)
    priority: str
    affected_services: list[str] = Field(default_factory=list)
    primary_suspect: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class StatusUpdateRequest(BaseModel):
    status: str
    expected_version: int = Field(ge=1)


def create_app(api=None):

    if FastAPI is None:
        raise RuntimeError(
            "FastAPI is not installed. "
            "Install with: python -m pip install fastapi uvicorn"
        )

    app = FastAPI(
        title="Infrastructure Intelligence Incident Platform",
        version="1.0.0",
    )

    if api is not None:
        app.state.incident_api = api

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "incident-platform",
        }

    @app.post("/api/incidents", status_code=201)
    def create_incident(request: CreateIncidentRequest):

        try:
            return app.state.incident_api.create_incident(
                title=request.title,
                priority=request.priority,
                affected_services=request.affected_services,
                primary_suspect=request.primary_suspect,
                confidence=request.confidence,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            )

    @app.get("/api/incidents")
    def list_incidents(
        status: str | None = Query(default=None),
        priority: str | None = Query(default=None),
    ):

        try:
            return app.state.incident_api.list_incidents(
                status=status,
                priority=priority,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            )

    @app.get("/api/incidents/{incident_id}")
    def get_incident(incident_id: UUID):

        result = app.state.incident_api.get_incident(
            incident_id
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Incident not found",
            )

        return result

    @app.patch("/api/incidents/{incident_id}/status")
    def change_status(
        incident_id: UUID,
        request: StatusUpdateRequest,
    ):

        try:
            return app.state.incident_api.change_status(
                incident_id=incident_id,
                target_status=request.status,
                expected_version=request.expected_version,
            )

        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            )

        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            )

        except RuntimeError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            )

    @app.get("/api/incidents/{incident_id}/timeline")
    def get_timeline(
        incident_id: UUID,
        after_sequence: int = Query(
            default=0,
            ge=0,
        ),
    ):

        try:
            return app.state.incident_api.timeline(
                incident_id,
                after_sequence,
            )

        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            )

    return app


# Production entry point.
# The database connection is intentionally constructed here,
# not during module import, so tests can inject a fake store.

if FastAPI is not None:
    from database.postgres_store import PostgresIncidentStore
    from api.incident_api import IncidentAPI

    _store = PostgresIncidentStore(
        os.getenv("DATABASE_URL")
    )

    _api = IncidentAPI(_store)

    app = create_app(_api)
