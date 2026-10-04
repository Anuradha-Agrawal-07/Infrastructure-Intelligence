import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "services" / "intelligence-engine"

sys.path.insert(0, str(ENGINE))

from topology_normalizer import normalize_snapshot


class TopologyNormalizerTests(unittest.TestCase):

    def test_normalizes_nodes_and_edges(self):
        snapshot = {
            "containers": [
                {
                    "id": "container-1",
                    "name": "order-service",
                    "image": "order:latest",
                    "state": "running",
                    "networks": ["app-net"],
                    "ports": [4002]
                },
                {
                    "id": "container-2",
                    "name": "postgres",
                    "image": "postgres:16",
                    "state": "running",
                    "networks": ["app-net"],
                    "ports": [5432]
                }
            ],
            "edges": [
                {
                    "source": "order-service",
                    "target": "postgres",
                    "protocol": "tcp",
                    "remote_port": 5432,
                    "state": "TIME_WAIT",
                    "observed_connections": 6,
                    "observed_at": "2026-10-04T15:39:31Z"
                }
            ]
        }

        result = normalize_snapshot(snapshot)

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(len(result["edges"]), 1)
        self.assertEqual(result["nodes"][0]["type"], "service")
        self.assertEqual(
            result["nodes"][0]["identified_via"],
            "discovery-agent"
        )

        edge = result["edges"][0]

        self.assertEqual(edge["source"], "order-service")
        self.assertEqual(edge["target"], "postgres")
        self.assertEqual(edge["remote_port"], 5432)

    def test_skips_invalid_edges(self):
        snapshot = {
            "containers": [],
            "edges": [
                {"source": "a"},
                {"target": "b"},
                {"source": "a", "target": "b"}
            ]
        }

        result = normalize_snapshot(snapshot)

        self.assertEqual(len(result["edges"]), 1)

    def test_empty_snapshot(self):
        result = normalize_snapshot({})

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["edges"], [])


if __name__ == "__main__":
    unittest.main()
