from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from models.incident import Incident


SEVERITY_TO_PRIORITY = {
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
}


REQUIRED_ENVELOPE_FIELDS = {
    "event_id",
    "event_type",
    "schema_version",
    "occurred_at",
    "producer",
    "correlation_id",
    "incident_id",
    "payload",
}


REQUIRED_ANOMALY_FIELDS = {
    "anomaly_id",
    "service_id",
    "metric",
    "observed_value",
    "expected_value",
    "deviation",
    "detector",
    "severity",
    "confidence",
    "window_start",
    "window_end",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def priority_from_severity(severity: str) -> str:
    return SEVERITY_TO_PRIORITY.get(
        str(severity).lower(),
        "P2",
    )


def build_incident_title(payload: dict) -> str:
    return (
        f'{payload["service_id"]}: '
        f'{payload["metric"]} anomaly detected'
    )


def _validate_event(event: dict) -> UUID:
    if not isinstance(event, dict):
        raise HTTPException(
            status_code=400,
            detail="Event must be a JSON object.",
        )

    missing = REQUIRED_ENVELOPE_FIELDS - set(event.keys())

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing event fields: {sorted(missing)}",
        )

    if event["event_type"] != "ANOMALY_DETECTED":
        raise HTTPException(
            status_code=400,
            detail="Only ANOMALY_DETECTED events are accepted.",
        )

    if event["schema_version"] != 1:
        raise HTTPException(
            status_code=400,
            detail="Unsupported event schema_version.",
        )

    try:
        event_id = UUID(str(event["event_id"]))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="event_id must be a UUID.",
        )

    payload = event["payload"]

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="payload must be an object.",
        )

    missing_payload = REQUIRED_ANOMALY_FIELDS - set(payload.keys())

    if missing_payload:
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing anomaly payload fields: "
                f"{sorted(missing_payload)}"
            ),
        )

    return event_id


def build_intelligence_router(
    incident_api,
    realtime_service,
    store,
):
    router = APIRouter(
        prefix="/api/intelligence",
        tags=["intelligence"],
    )

    @router.post("/events")
    async def ingest_intelligence_event(event: dict):
        event_id = _validate_event(event)
        payload = event["payload"]

        # ----------------------------------------------------
        # Canonical idempotency check:
        # the incoming intelligence event_id is the durable
        # identity of the ANOMALY_DETECTED event.
        # ----------------------------------------------------
        existing = store.get_incident_by_event_id(event_id)

        if existing is not None:
            return {
                "created": False,
                "duplicate": True,
                "incident": existing,
            }

        # ----------------------------------------------------
        # Create incident.
        # Severity -> priority is the first vertical-slice
        # mapping. Later impact analysis can enrich/override it.
        # ----------------------------------------------------
        incident = Incident(
            title=build_incident_title(payload),
            priority=priority_from_severity(payload["severity"]),
            affected_services=[payload["service_id"]],
            primary_suspect=payload["service_id"],
            confidence=payload["confidence"],
        )

        created = store.create_incident(incident)
        incident_id = incident.incident_id

        # ----------------------------------------------------
        # Persist anomaly as durable domain data.
        # ----------------------------------------------------
        if hasattr(store, "create_anomaly"):
            store.create_anomaly(
                incident_id,
                payload,
            )

        # ----------------------------------------------------
        # Persist + publish INCIDENT_CREATED.
        # This receives a generated event ID because it is a
        # new Member2 lifecycle event.
        # ----------------------------------------------------
        incident_created = realtime_service.create_event(
            incident_id=incident_id,
            event_type="INCIDENT_CREATED",
            payload={
                "incident": created,
                "source_event_id": str(event_id),
            },
            producer="incident-platform",
        )

        await realtime_service.persist_and_publish(
            incident_created
        )

        # ----------------------------------------------------
        # Persist + publish the original intelligence event.
        # IMPORTANT: preserve incoming event_id.
        # ----------------------------------------------------
        anomaly_realtime_event = realtime_service.create_event(
            incident_id=incident_id,
            event_type="ANOMALY_DETECTED",
            payload=event,
            producer=event["producer"],
            event_id=event_id,
        )

        await realtime_service.persist_and_publish(
            anomaly_realtime_event
        )

        return {
            "created": True,
            "duplicate": False,
            "incident": created,
        }

    return router