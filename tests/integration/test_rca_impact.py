import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "services" / "intelligence-engine"

sys.path.insert(0, str(ENGINE))

from rca_engine import (
    RCA_WEIGHTS,
    build_hypothesis,
    run_rca,
    weighted_score
)

from impact_engine import (
    blast_radius,
    build_impact_result,
    determine_priority,
    response_target
)


class RCAEngineTests(unittest.TestCase):

    def setUp(self):
        self.topology = {
            "nodes": [
                {"id": "api-gateway"},
                {"id": "order-service"},
                {"id": "postgres"}
            ],
            "edges": [
                {
                    "edge_id": "api-order",
                    "source": "api-gateway",
                    "target": "order-service"
                },
                {
                    "edge_id": "order-db",
                    "source": "order-service",
                    "target": "postgres"
                }
            ]
        }

        self.anomalies = [
            {
                "anomaly_id": "a1",
                "service_id": "order-service",
                "metric": "request_latency_ms",
                "severity": "CRITICAL",
                "confidence": 0.95,
                "window_start": "2026-10-04T15:00:00Z"
            },
            {
                "anomaly_id": "a2",
                "service_id": "postgres",
                "metric": "error_rate",
                "severity": "HIGH",
                "confidence": 0.90,
                "window_start": "2026-10-04T15:01:00Z"
            }
        ]

    def test_weights_match_architecture(self):
        self.assertEqual(
            RCA_WEIGHTS["temporal_precedence"],
            0.30
        )
        self.assertEqual(
            RCA_WEIGHTS["dependency_centrality"],
            0.25
        )
        self.assertEqual(
            RCA_WEIGHTS["symptom_coverage"],
            0.20
        )
        self.assertEqual(
            RCA_WEIGHTS["change_correlation"],
            0.15
        )
        self.assertEqual(
            RCA_WEIGHTS["metric_strength"],
            0.10
        )

        self.assertAlmostEqual(
            sum(RCA_WEIGHTS.values()),
            1.0
        )

    def test_weighted_score(self):
        score = weighted_score({
            "temporal_precedence": 1,
            "dependency_centrality": 1,
            "symptom_coverage": 1,
            "change_correlation": 1,
            "metric_strength": 1
        })

        self.assertEqual(score, 1.0)

    def test_build_hypothesis(self):
        result = build_hypothesis(
            "order-service",
            self.anomalies,
            self.topology
        )

        self.assertEqual(
            result["service_id"],
            "order-service"
        )

        self.assertGreater(
            result["score"],
            0
        )

        self.assertGreater(
            result["confidence"],
            0
        )

        self.assertTrue(
            len(result["reasons"]) > 0
        )

    def test_run_rca(self):
        result = run_rca(
            "incident-candidate-123",
            self.anomalies,
            self.topology
        )

        self.assertEqual(
            result["incident_candidate_id"],
            "incident-candidate-123"
        )

        self.assertIsNotNone(
            result["primary_suspect"]
        )

        self.assertEqual(
            len(result["hypotheses"]),
            2
        )

        self.assertEqual(
            len(result["evidence"]),
            2
        )


class ImpactEngineTests(unittest.TestCase):

    def setUp(self):
        self.topology = {
            "nodes": [
                {"id": "api-gateway"},
                {"id": "order-service"},
                {"id": "postgres"},
                {"id": "unrelated"}
            ],
            "edges": [
                {
                    "edge_id": "api-order",
                    "source": "api-gateway",
                    "target": "order-service"
                },
                {
                    "edge_id": "order-db",
                    "source": "order-service",
                    "target": "postgres"
                }
            ]
        }

        self.anomalies = [
            {
                "anomaly_id": "a1",
                "service_id": "order-service",
                "metric": "request_latency_ms",
                "severity": "CRITICAL",
                "confidence": 0.95
            },
            {
                "anomaly_id": "a2",
                "service_id": "postgres",
                "metric": "error_rate",
                "severity": "HIGH",
                "confidence": 0.90
            }
        ]

    def test_priority(self):
        priority = determine_priority(
            self.anomalies,
            ["order-service", "postgres"],
            ["order-service"]
        )

        self.assertEqual(priority, "P0")
        self.assertEqual(response_target(priority), "15m")

    def test_blast_radius(self):
        result = blast_radius(
            ["order-service"],
            self.topology
        )

        self.assertEqual(
            result,
            [
                "api-gateway",
                "order-service",
                "postgres"
            ]
        )

        self.assertNotIn(
            "unrelated",
            result
        )

    def test_impact_result(self):
        result = build_impact_result(
            "incident-candidate-123",
            self.anomalies,
            self.topology,
            critical_services=["order-service"],
            service_paths={
                "order-service": [
                    "customer",
                    "api-gateway",
                    "order-service"
                ]
            },
            service_capabilities={
                "order-service": "order-management",
                "postgres": "data-storage"
            }
        )

        self.assertEqual(
            result["priority"],
            "P0"
        )

        self.assertEqual(
            result["response_target"],
            "15m"
        )

        self.assertEqual(
            result["affected_services"],
            ["order-service", "postgres"]
        )

        self.assertIn(
            "api-gateway",
            result["blast_radius"]
        )

        self.assertIn(
            "order-management",
            result["business_capability"]
        )


if __name__ == "__main__":
    unittest.main()
