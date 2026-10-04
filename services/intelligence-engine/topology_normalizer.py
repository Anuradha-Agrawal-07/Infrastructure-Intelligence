import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_snapshot(snapshot, services=None):
    services = services or {}
    nodes = []
    edges = []

    for container in snapshot.get("containers", []):
        container_id = (
            container.get("id")
            or container.get("container_id")
            or container.get("name")
        )

        if not container_id:
            continue

        name = container.get("name") or container_id
        service = services.get(name, {})

        nodes.append({
            "id": service.get("service_id", name),
            "type": "service",
            "name": name,
            "image": container.get("image"),
            "state": container.get("state"),
            "networks": container.get("networks", []),
            "ports": container.get("ports", []),
            "identified_via": "discovery-agent"
        })

    for raw_edge in snapshot.get("edges", []):
        source = (
            raw_edge.get("source")
            or raw_edge.get("source_service")
            or raw_edge.get("from")
        )

        target = (
            raw_edge.get("target")
            or raw_edge.get("target_service")
            or raw_edge.get("to")
        )

        if not source or not target:
            continue

        edges.append({
            "edge_id": raw_edge.get(
                "edge_id",
                f"{source}->{target}:{raw_edge.get('remote_port', '')}"
            ),
            "source": source,
            "target": target,
            "protocol": raw_edge.get("protocol", "tcp"),
            "remote_port": raw_edge.get("remote_port"),
            "state": raw_edge.get("state"),
            "observed_connections": raw_edge.get(
                "observed_connections", 0
            ),
            "observed_at": raw_edge.get("observed_at")
        })

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "nodes": nodes,
        "edges": edges
    }


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def main():
    if len(sys.argv) not in (2, 3):
        print(
            "Usage: python topology_normalizer.py <snapshot.json> [services.json]",
            file=sys.stderr
        )
        return 2

    snapshot_path = Path(sys.argv[1])
    services_path = Path(sys.argv[2]) if len(sys.argv) == 3 else None

    snapshot = load_json(snapshot_path)

    services = {}

    if services_path and services_path.exists():
        raw_services = load_json(services_path)

        if isinstance(raw_services, list):
            services = {
                item.get("name", ""): item
                for item in raw_services
                if item.get("name")
            }
        elif isinstance(raw_services, dict):
            services = raw_services

    normalized = normalize_snapshot(snapshot, services)
    print(json.dumps(normalized, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
