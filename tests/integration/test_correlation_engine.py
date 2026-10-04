import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "services" / "intelligence-engine"

sys.path.insert(0, str(ENGINE))

from correlation_engine import (
    build_adjacency,
    candidate_id,
    correlate
)


class CorrelationEngineTests(unittest.TestCase):

    def setUp(self):
        self.topology = {
            "schema_version": 1,
            "generated_at": "2026-10-04T15:00:00Z",
            "nodes": [
                {
                    "id": "api-gateway",
                    "type": "service",
                    "name": "api-gateway"
                },
                {
                    "id": "order-service",
                    "type": "service",
                    "name": "order-service"
                },
                {
                    "id": "postgres",
                    "type": "service",
                    "name": "postgres"
                }
            ],
            "edges": [
                {
                    "edge_id": "api-order",
                    "source": "api-gateway",
                    "target": "order-service",
                    "protocol": "tcp",
                    "remote_port": 4002
                },
                {
                    "edge_id": "order-postgres",
                    "source": "order-service",
                    "target": "postgres",
                    "protocol": "tcp",
                    "remote_port": 5432
                }
            ]
        }

        self.anomalies = [
            {
                "anomaly_id": "a1",
                "service_id": "order-service",
                "metric": "request_latency_ms",
                "observed_value": 200,
                "expected_value": 12,
                "deviation": 188,
                "detector": "rolling_zscore",
                "severity": "CRITICAL",
                "confidence": 0.95,
                "window_start": "2026-10-04T15:00:00Z",
                "window_end": "2026-10-04T15:01:00Z"
            },
            {
                "anomaly_id": "a2",
                "service_id": "postgres",
                "metric": "error_rate",
                "observed_value": 40,
                "expected_value": 1,
                "deviation": 39,
                "detector": "rolling_zscore",
                "severity": "HIGH",
                "confidence": 0.90,
                "window_start": "2026-10-04T15:00:00Z",
                "window_end": "2026-10-04T15:01:00Z"
            }
        ]

    def test_builds_adjacency(self):
        adjacency = build_adjacency(self.topology)

        self.assertIn(
            "order-service",
            adjacency["api-gateway"]
        )

        self.assertIn(
            "postgres",
            adjacency["order-service"]
        )

    def test_candidate_id_is_deterministic(self):
        first = candidate_id(self.anomalies)
        second = candidate_id(list(reversed(self.anomalies)))

        self.assertEqual(first, second)

    def test_correlates_anomalies(self):
        result = correlate(
            self.topology,
            self.anomalies
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result["affected_services"],
            ["order-service", "postgres"]
        )

        self.assertEqual(
            result["related_services"],
            ["api-gateway"]
        )

        self.assertEqual(
            len(result["evidence_edges"]),
            2
        )

        self.assertEqual(
            len(result["raw_alerts"]),
            2
        )

        self.assertIn(
            "order-service",
            result["grouped_alerts"]
        )

        self.assertIn(
            "postgres",
            result["grouped_alerts"]
        )

        self.assertGreater(
            result["confidence"],
            0
        )

    def test_empty_anomalies(self):
        result = correlate(
            self.topology,
            []
        )

        self.assertIsNone(result)

    def test_unrelated_service_is_not_in_related(self):
        topology = {
            "nodes": [
                {"id": "service-a"},
                {"id": "service-b"},
                {"id": "service-c"}
            ],
            "edges": [
                {
                    "edge_id": "a-b",
                    "source": "service-a",
                    "target": "service-b"
                }
            ]
        }

        anomaly = {
            "anomaly_id": "x",
            "service_id": "service-a",
            "metric": "cpu_percent",
            "severity": "HIGH",
            "confidence": 0.9
        }

        result = correlate(
            topology,
            [anomaly]
        )

        self.assertEqual(
            result["affected_services"],
            ["service-a"]
        )

        self.assertEqual(
            result["related_services"],
            ["service-b"]
        )

        self.assertNotIn(
            "service-c",
            result["related_services"]
        )


if __name__ == "__main__":
    unittest.main()
