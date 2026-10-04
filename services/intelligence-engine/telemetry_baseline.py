import math
from statistics import mean, pstdev


def rolling_baseline(values):
    if not values:
        return {"expected_value": 0.0, "stddev": 0.0}

    numeric = [float(v) for v in values]

    if len(numeric) == 1:
        return {
            "expected_value": numeric[0],
            "stddev": 0.0
        }

    return {
        "expected_value": mean(numeric),
        "stddev": pstdev(numeric)
    }


def z_score(observed, expected, stddev):
    if stddev == 0:
        return 0.0

    return (float(observed) - expected) / stddev


def baseline_metric(samples):
    """
    samples:
      [
        {"timestamp": "...", "value": 100},
        {"timestamp": "...", "value": 105}
      ]
    """
    values = [sample["value"] for sample in samples]
    return rolling_baseline(values)


def detect_threshold(observed, expected, threshold):
    deviation = abs(float(observed) - float(expected))

    return {
        "detected": deviation > threshold,
        "deviation": deviation
    }


def detect_zscore(observed, expected, stddev, threshold=3.0):
    score = z_score(observed, expected, stddev)

    return {
        "detected": abs(score) >= threshold,
        "z_score": score,
        "deviation": abs(float(observed) - float(expected))
    }


def calculate_confidence(zscore_value, threshold):
    if threshold <= 0:
        return 1.0

    strength = abs(zscore_value) / threshold
    return min(0.99, max(0.0, strength / 2.0))


def severity_from_zscore(zscore_value):
    magnitude = abs(zscore_value)

    if magnitude >= 5:
        return "CRITICAL"

    if magnitude >= 4:
        return "HIGH"

    if magnitude >= 3:
        return "MEDIUM"

    return "LOW"


def detect_anomaly(
    service_id,
    metric,
    observed_value,
    baseline_values,
    window_start,
    window_end,
    detector="rolling_zscore",
    zscore_threshold=3.0
):
    baseline = baseline_metric(
        [{"value": value} for value in baseline_values]
    )

    expected = baseline["expected_value"]
    stddev = baseline["stddev"]

    result = detect_zscore(
        observed_value,
        expected,
        stddev,
        zscore_threshold
    )

    if not result["detected"]:
        return None

    confidence = calculate_confidence(
        result["z_score"],
        zscore_threshold
    )

    return {
        "anomaly_id": None,
        "service_id": service_id,
        "metric": metric,
        "observed_value": float(observed_value),
        "expected_value": float(expected),
        "deviation": float(result["deviation"]),
        "detector": detector,
        "severity": severity_from_zscore(result["z_score"]),
        "confidence": round(confidence, 4),
        "window_start": window_start,
        "window_end": window_end
    }
