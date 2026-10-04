from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _metric_ok(metric: dict, thresholds: dict) -> bool:
    name = metric.get("metric")
    value = metric.get("value")

    if name not in thresholds or value is None:
        return False

    rule = thresholds[name]
    return rule["min"] <= float(value) <= rule["max"]


def verify_recovery(metrics: list[dict], thresholds: dict) -> dict:
    checks = []

    for metric in metrics:
        checks.append({
            "metric": metric.get("metric"),
            "service_id": metric.get("service_id"),
            "value": metric.get("value"),
            "passed": _metric_ok(metric, thresholds),
        })

    required = list(thresholds.keys())
    passed_names = {
        check["metric"]
        for check in checks
        if check["passed"]
    }

    verified = all(name in passed_names for name in required)

    return {
        "verified": verified,
        "checked_metrics": checks,
        "required_metrics": required,
        "verified_at": utc_now(),
    }


def build_recovery_evidence(
    incident_id: str | UUID,
    service_id: str,
    verification: dict,
    evidence_refs: list[dict] | None = None,
) -> dict:
    return {
        "evidence_id": str(uuid4()),
        "type": "recovery_verification",
        "incident_id": str(incident_id),
        "service_id": service_id,
        "verified": bool(verification["verified"]),
        "observations": verification["checked_metrics"],
        "evidence_refs": evidence_refs or [],
        "observed_at": verification["verified_at"],
    }


def build_recovery_event(
    evidence: dict,
    correlation_id: str | UUID,
    incident_id: str | UUID,
) -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": "RECOVERY_EVIDENCE",
        "schema_version": 1,
        "occurred_at": evidence["observed_at"],
        "producer": "intelligence-engine",
        "correlation_id": str(correlation_id),
        "incident_id": str(incident_id),
        "payload": evidence,
    }
