import json
import os
import sys


SCHEMA_VERSION = 1


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_correlation_graph(snapshot, changed_nodes):
    nodes = snapshot.get("nodes", [])
    edges = snapshot.get("edges", [])

    # Convert node IDs into human-readable service names.
    node_names = {
        node["id"]: node["name"]
        for node in nodes
    }

    graph = {}

    # Every changed node gets an entry, even if it has
    # no relationships.
    for changed in changed_nodes:
        graph[changed] = {
            "related_services": [],
            "relationships": []
        }

    # Find relationships between changed nodes and their
    # directly connected services.
    for edge in edges:
        source = node_names.get(
            edge["source"],
            edge["source"]
        )

        target = node_names.get(
            edge["target"],
            edge["target"]
        )

        # Changed service -> related service
        if source in changed_nodes:
            graph.setdefault(
                source,
                {
                    "related_services": [],
                    "relationships": []
                }
            )

            if target not in graph[source]["related_services"]:
                graph[source]["related_services"].append(target)

            graph[source]["relationships"].append({
                "direction": "outgoing",
                "related_service": target,
                "remote_port": edge.get("remote_port")
            })

        # Related service -> changed service
        if target in changed_nodes:
            graph.setdefault(
                target,
                {
                    "related_services": [],
                    "relationships": []
                }
            )

            if source not in graph[target]["related_services"]:
                graph[target]["related_services"].append(source)

            graph[target]["relationships"].append({
                "direction": "incoming",
                "related_service": source,
                "remote_port": edge.get("remote_port")
            })

    return graph


def get_snapshot_timestamp(snapshot):
    """
    Preserve the timestamp from the discovery snapshot.

    We intentionally do not generate a new timestamp here.
    The timestamp should represent when the topology snapshot
    was actually captured.
    """

    return (
        snapshot.get("generated_at")
        or snapshot.get("timestamp")
        or snapshot.get("observed_at")
        or snapshot.get("captured_at")
    )


def build_result(snapshot, event):
    # The topology change event stores all change information
    # inside the "changes" object.
    changes = event.get("changes", {})

    # A node is considered changed if it was either added
    # or removed by the topology comparison.
    changed_nodes = sorted(
        set(
            changes.get("added_nodes", [])
            + changes.get("removed_nodes", [])
        )
    )

    # Build correlations using the topology snapshot.
    correlations = build_correlation_graph(
        snapshot,
        set(changed_nodes)
    )

    return {
        "schema_version": SCHEMA_VERSION,

        "event_type": "correlation_graph",

        # Preserve the actual observation timestamp from
        # the source topology snapshot.
        "generated_at": get_snapshot_timestamp(snapshot),

        "source_event": event.get(
            "event_type",
            "topology_change"
        ),

        "changed_nodes": changed_nodes,

        "added_nodes": changes.get(
            "added_nodes",
            []
        ),

        "removed_nodes": changes.get(
            "removed_nodes",
            []
        ),

        "added_edges": changes.get(
            "added_edges",
            []
        ),

        "removed_edges": changes.get(
            "removed_edges",
            []
        ),

        "correlations": correlations
    }


def main():
    if len(sys.argv) != 3:
        print(
            "Usage:\n"
            "python correlation.py "
            "<snapshot.json> <topology_change_event.json>"
        )
        sys.exit(1)

    snapshot_path = sys.argv[1]
    event_path = sys.argv[2]

    try:
        snapshot = load_json(snapshot_path)
        event = load_json(event_path)

    except FileNotFoundError as e:
        print(
            f"\n[correlation] ERROR: File not found:\n"
            f"{e.filename}"
        )
        sys.exit(1)

    except json.JSONDecodeError as e:
        print(
            f"\n[correlation] ERROR: Invalid JSON:\n"
            f"{e}"
        )
        sys.exit(1)

    result = build_result(
        snapshot,
        event
    )

    output_dir = "output"

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    output_file = os.path.join(
        output_dir,
        "correlation_graph.json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            indent=2
        )

    print("\n=== CORRELATION GRAPH ===\n")

    print(
        json.dumps(
            result,
            indent=2
        )
    )

    print(
        f"\n[correlation] "
        f"Graph saved: {output_file}"
    )


if __name__ == "__main__":
    main()