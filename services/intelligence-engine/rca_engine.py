from datetime import datetime, timezone


RCA_WEIGHTS = {
    "temporal_precedence": 0.30,
    "dependency_centrality": 0.25,
    "symptom_coverage": 0.20,
    "change_correlation": 0.15,
    "metric_strength": 0.10
}


def clamp(value):
    return max(0.0, min(1.0, float(value)))


def weighted_score(features):
    return round(
        sum(
            RCA_WEIGHTS[name] * clamp(features.get(name, 0.0))
            for name in RCA_WEIGHTS
        ),
        4
    )


def temporal_precedence(anomaly_times, candidate_time):
    if not anomaly_times or not candidate_time:
        return 0.0

    candidate = datetime.fromisoformat(
        candidate_time.replace("Z", "+00:00")
    )

    times = [
        datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        for value in anomaly_times
    ]

    earlier = sum(
        1 for value in times
        if candidate <= value
    )

    return clamp(earlier / len(times))


def dependency_centrality(service_id, topology):
    nodes = {
        node["id"]
        for node in topology.get("nodes", [])
    }

    if service_id not in nodes:
        return 0.0

    degree = 0

    for edge in topology.get("edges", []):
        if (
            edge["source"] == service_id
            or edge["target"] == service_id
        ):
            degree += 1

    max_degree = max(1, len(nodes) - 1)

    return clamp(degree / max_degree)


def symptom_coverage(service_id, anomalies, affected_services):
    if not anomalies:
        return 0.0

    service_anomalies = [
        anomaly
        for anomaly in anomalies
        if anomaly["service_id"] == service_id
    ]

    affected_count = len(set(affected_services))

    local_strength = min(
        1.0,
        len(service_anomalies) / max(1, len(anomalies))
    )

    spread_strength = min(
        1.0,
        affected_count / 3.0
    )

    return round(
        0.7 * local_strength + 0.3 * spread_strength,
        4
    )


def metric_strength(service_id, anomalies):
    values = [
        float(anomaly.get("confidence", 0.0))
        for anomaly in anomalies
        if anomaly["service_id"] == service_id
    ]

    if not values:
        return 0.0

    return clamp(sum(values) / len(values))


def change_correlation(service_id, changes):
    if not changes:
        return 0.0

    matching = [
        change
        for change in changes
        if change.get("service_id") == service_id
    ]

    if not matching:
        return 0.0

    return 1.0


def build_hypothesis(
    service_id,
    anomalies,
    topology,
    changes=None
):
    anomaly_times = [
        anomaly["window_start"]
        for anomaly in anomalies
        if anomaly.get("window_start")
    ]

    candidate_time = min(anomaly_times) if anomaly_times else None

    features = {
        "temporal_precedence": temporal_precedence(
            anomaly_times,
            candidate_time
        ),
        "dependency_centrality": dependency_centrality(
            service_id,
            topology
        ),
        "symptom_coverage": symptom_coverage(
            service_id,
            anomalies,
            [
                anomaly["service_id"]
                for anomaly in anomalies
            ]
        ),
        "change_correlation": change_correlation(
            service_id,
            changes or []
        ),
        "metric_strength": metric_strength(
            service_id,
            anomalies
        )
    }

    score = weighted_score(features)

    reasons = []

    if features["dependency_centrality"] > 0:
        reasons.append(
            "service participates in observed dependency topology"
        )

    if features["symptom_coverage"] > 0:
        reasons.append(
            "service has correlated anomaly symptoms"
        )

    if features["metric_strength"] >= 0.8:
        reasons.append(
            "anomaly confidence is strong"
        )

    if features["change_correlation"] > 0:
        reasons.append(
            "service has a correlated change"
        )

    return {
        "service_id": service_id,
        "score": score,
        "confidence": round(
            min(0.99, score),
            4
        ),
        "reasons": reasons,
        "features": features
    }


def run_rca(
    incident_candidate_id,
    anomalies,
    topology,
    changes=None
):
    affected_services = sorted({
        anomaly["service_id"]
        for anomaly in anomalies
    })

    hypotheses = [
        build_hypothesis(
            service_id,
            anomalies,
            topology,
            changes
        )
        for service_id in affected_services
    ]

    hypotheses.sort(
        key=lambda item: (
            -item["score"],
            item["service_id"]
        )
    )

    primary = (
        hypotheses[0]["service_id"]
        if hypotheses
        else None
    )

    evidence = [
        {
            "type": "anomaly",
            "anomaly_id": anomaly["anomaly_id"],
            "service_id": anomaly["service_id"],
            "metric": anomaly["metric"],
            "severity": anomaly["severity"]
        }
        for anomaly in anomalies
    ]

    return {
        "incident_candidate_id": incident_candidate_id,
        "primary_suspect": primary,
        "hypotheses": hypotheses,
        "evidence": evidence
    }
