import json
import sys
from datetime import datetime, timezone


def load_snapshot(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def node_key(node):
    return node["name"]


def edge_key(edge, nodes_by_id):
    source = nodes_by_id.get(edge["source"], edge["source"])
    target = nodes_by_id.get(edge["target"], edge["target"])

    return (
        source,
        target,
        edge.get("remote_port")
    )


def compare_snapshots(old_path, new_path):
    old = load_snapshot(old_path)
    new = load_snapshot(new_path)

    # -------------------------
    # Compare nodes
    # -------------------------

    old_nodes = {
        node_key(node): node
        for node in old.get("nodes", [])
    }

    new_nodes = {
        node_key(node): node
        for node in new.get("nodes", [])
    }

    added_nodes = sorted(
        set(new_nodes) - set(old_nodes)
    )

    removed_nodes = sorted(
        set(old_nodes) - set(new_nodes)
    )

    # -------------------------
    # Compare edges
    # -------------------------

    old_ids = {
        node["id"]: node["name"]
        for node in old.get("nodes", [])
    }

    new_ids = {
        node["id"]: node["name"]
        for node in new.get("nodes", [])
    }

    old_edges = {
        edge_key(edge, old_ids): edge
        for edge in old.get("edges", [])
    }

    new_edges = {
        edge_key(edge, new_ids): edge
        for edge in new.get("edges", [])
    }

    added_edges = sorted(
        set(new_edges) - set(old_edges)
    )

    removed_edges = sorted(
        set(old_edges) - set(new_edges)
    )

    return {
        "old_snapshot": old_path,
        "new_snapshot": new_path,

        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,

        "added_edges": [
            {
                "source": edge[0],
                "target": edge[1],
                "remote_port": edge[2]
            }
            for edge in added_edges
        ],

        "removed_edges": [
            {
                "source": edge[0],
                "target": edge[1],
                "remote_port": edge[2]
            }
            for edge in removed_edges
        ]
    }


def create_event(comparison):
    has_changes = any([
        comparison["added_nodes"],
        comparison["removed_nodes"],
        comparison["added_edges"],
        comparison["removed_edges"]
    ])

    return {
        "event_type": "topology_change",
        "timestamp": datetime.now(timezone.utc).isoformat(),

        "change_detected": has_changes,

        "source_snapshot": comparison["old_snapshot"],
        "target_snapshot": comparison["new_snapshot"],

        "changes": {
            "added_nodes": comparison["added_nodes"],
            "removed_nodes": comparison["removed_nodes"],
            "added_edges": comparison["added_edges"],
            "removed_edges": comparison["removed_edges"]
        }
    }


def main():

    if len(sys.argv) != 3:
        print(
            "Usage:\n"
            "python compare_snapshots.py "
            "<old_snapshot.json> <new_snapshot.json>"
        )
        sys.exit(1)

    old_path = sys.argv[1]
    new_path = sys.argv[2]

    comparison = compare_snapshots(
        old_path,
        new_path
    )

    event = create_event(comparison)

    # Print human-readable comparison
    print("\n=== TOPOLOGY COMPARISON ===\n")
    print(json.dumps(comparison, indent=2))

    # Save machine-readable event
    event_file = "output/topology_change_event.json"

    with open(event_file, "w", encoding="utf-8") as f:
        json.dump(event, f, indent=2)

    print(
        f"\n[discovery] "
        f"Topology change event saved: {event_file}"
    )


if __name__ == "__main__":
    main()