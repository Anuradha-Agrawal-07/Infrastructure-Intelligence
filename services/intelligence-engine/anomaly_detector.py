import uuid
from datetime import datetime, timezone

from telemetry_baseline import detect_anomaly


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_anomaly(
    service_id,
    metric,
    observed_value,
    baseline_values,
    window_start,
    window_end,
    detector="rolling_zscore"
):
    anomaly = detect_anomaly(
        service_id=service_id,
        metric=metric,
        observed_value=observed_value,
        baseline_values=baseline_values,
        window_start=window_start,
        window_end=window_end,
        detector=detector
    )

    if anomaly is None:
        return None

    anomaly["anomaly_id"] = str(uuid.uuid4())

    return anomaly


def build_anomaly_event(anomaly, correlation_id=None):
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "ANOMALY_DETECTED",
        "schema_version": 1,
        "occurred_at": utc_now(),
        "producer": "intelligence-engine",
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "incident_id": None,
        "payload": anomaly
    }
