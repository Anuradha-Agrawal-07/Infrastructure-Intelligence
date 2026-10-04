from datetime import datetime, timezone


PRIORITY_ORDER = {
    "P0": 4,
    "P1": 3,
    "P2": 2,
    "P3": 1
}


def determine_priority(
    anomalies,
    affected_services,
    critical_services=None
):
    critical_services = set(critical_services or [])

    has_critical = any(
        anomaly.get("severity") == "CRITICAL"
        for anomaly in anomalies
    )

    affected_critical = bool(
        critical_services.intersection(
            affected_services
        )
    )

    if has_critical and affected_critical:
        return "P0"

    if has_critical:
        return "P1"

    if len(affected_services) >= 3:
        return "P1"

    if len(affected_services) >= 2:
        return "P2"

    return "P3"


def response_target(priority):
    return {
        "P0": "15m",
        "P1": "30m",
        "P2": "60m",
        "P3": "4h"
    }.get(priority, "4h")


def customer_path(
    affected_services,
    service_paths=None
):
    service_paths = service_paths or {}

    paths = []

    for service in affected_services:
        path = service_paths.get(service)

        if path:
            paths.append(path)

    return paths


def blast_radius(
    affected_services,
    topology
):
    affected = set(affected_services)
    impacted = set(affected)

    changed = True

    while changed:
        changed = False

        for edge in topology.get("edges", []):
            if edge["source"] in impacted:
                if edge["target"] not in impacted:
                    impacted.add(edge["target"])
                    changed = True

            if edge["target"] in impacted:
                if edge["source"] not in impacted:
                    impacted.add(edge["source"])
                    changed = True

    return sorted(impacted)


def determine_business_capability(
    affected_services,
    service_capabilities=None
):
    service_capabilities = service_capabilities or {}

    capabilities = sorted({
        service_capabilities[service]
        for service in affected_services
        if service in service_capabilities
    })

    return capabilities


def build_impact_result(
    incident_candidate_id,
    anomalies,
    topology,
    critical_services=None,
    service_paths=None,
    service_capabilities=None
):
    affected_services = sorted({
        anomaly["service_id"]
        for anomaly in anomalies
    })

    priority = determine_priority(
        anomalies,
        affected_services,
        critical_services
    )

    return {
        "incident_candidate_id": incident_candidate_id,
        "priority": priority,
        "response_target": response_target(priority),
        "affected_services": affected_services,
        "customer_path": customer_path(
            affected_services,
            service_paths
        ),
        "blast_radius": blast_radius(
            affected_services,
            topology
        ),
        "business_capability": determine_business_capability(
            affected_services,
            service_capabilities
        )
    }
