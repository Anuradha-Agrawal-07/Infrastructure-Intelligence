from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_event(
    event_type: str,
    payload: dict,
    correlation_id: str | UUID,
    incident_id: str | UUID | None = None,
    occurred_at: str | None = None,
) -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "schema_version": 1,
        "occurred_at": occurred_at or utc_now(),
        "producer": "intelligence-engine",
        "correlation_id": str(correlation_id),
        "incident_id": str(incident_id) if incident_id is not None else None,
        "payload": payload,
    }


def build_correlation_event(
    correlation_result: dict,
    correlation_id: str | UUID | None = None,
) -> dict:
    return build_event(
        "CORRELATION_RESULT",
        correlation_result,
        correlation_id or uuid4(),
    )


def build_rca_event(
    rca_result: dict,
    correlation_id: str | UUID,
    incident_id: str | UUID | None = None,
) -> dict:
    return build_event(
        "RCA_RESULT",
        rca_result,
        correlation_id,
        incident_id,
    )


def build_impact_event(
    impact_result: dict,
    correlation_id: str | UUID,
    incident_id: str | UUID | None = None,
) -> dict:
    return build_event(
        "IMPACT_RESULT",
        impact_result,
        correlation_id,
        incident_id,
    )
