import hashlib
import json


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":")
    )


def candidate_id(anomalies):
    identity = [
        {
            "service_id": item["service_id"],
            "metric": item["metric"],
            "severity": item["severity"]
        }
        for item in anomalies
    ]

    identity.sort(
        key=lambda item: (
            item["service_id"],
            item["metric"],
            item["severity"]
        )
    )

    digest = hashlib.sha256(
        canonical_json(identity).encode("utf-8")
    ).hexdigest()

    return f"incident-candidate-{digest[:16]}"


def build_adjacency(topology):
    adjacency = {}

    for node in topology.get("nodes", []):
        adjacency.setdefault(node["id"], set())

    for edge in topology.get("edges", []):
        source = edge["source"]
        target = edge["target"]

        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)

    return adjacency


def correlate(topology, anomalies):
    if not anomalies:
        return None

    adjacency = build_adjacency(topology)

    affected = sorted({
        anomaly["service_id"]
        for anomaly in anomalies
    })

    related = set()

    for service_id in affected:
        for neighbor in adjacency.get(service_id, set()):
            if neighbor not in affected:
                related.add(neighbor)

    evidence_edges = []

    for edge in topology.get("edges", []):
        if (
            edge["source"] in affected
            or edge["target"] in affected
        ):
            evidence_edges.append(edge)

    evidence_edges.sort(
        key=lambda edge: edge["edge_id"]
    )

    grouped_alerts = {}

    for anomaly in anomalies:
        key = anomaly["service_id"]

        grouped_alerts.setdefault(
            key,
            []
        ).append(anomaly)

    confidence = calculate_confidence(
        affected,
        evidence_edges,
        anomalies
    )

    return {
        "incident_candidate_id": candidate_id(anomalies),
        "affected_services": affected,
        "related_services": sorted(related),
        "evidence_edges": evidence_edges,
        "raw_alerts": anomalies,
        "grouped_alerts": grouped_alerts,
        "confidence": confidence
    }


def calculate_confidence(
    affected_services,
    evidence_edges,
    anomalies
):
    if not anomalies:
        return 0.0

    anomaly_strength = sum(
        float(item.get("confidence", 0))
        for item in anomalies
    ) / len(anomalies)

    topology_support = (
        1.0 if evidence_edges else 0.5
    )

    service_support = min(
        1.0,
        len(affected_services) / 3.0
    )

    score = (
        0.60 * anomaly_strength
        + 0.25 * topology_support
        + 0.15 * service_support
    )

    return round(
        min(0.99, max(0.0, score)),
        4
    )
