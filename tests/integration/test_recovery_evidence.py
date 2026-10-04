import sys
import unittest
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "services" / "intelligence-engine"

if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from recovery_evidence import (
    build_recovery_evidence,
    build_recovery_event,
    verify_recovery,
)


class RecoveryEvidenceTests(unittest.TestCase):

    def setUp(self):
        self.thresholds = {
            "request_latency_ms": {"min": 0, "max": 200},
            "error_rate": {"min": 0, "max": 0.05},
        }

    def test_recovery_is_verified_when_all_required_metrics_pass(self):
        result = verify_recovery(
            [
                {
                    "service_id": "ii-product-service",
                    "metric": "request_latency_ms",
                    "value": 120,
                },
                {
                    "service_id": "ii-product-service",
                    "metric": "error_rate",
                    "value": 0.01,
                },
            ],
            self.thresholds,
        )

        self.assertTrue(result["verified"])

    def test_recovery_fails_when_metric_is_out_of_bounds(self):
        result = verify_recovery(
            [
                {
                    "service_id": "ii-product-service",
                    "metric": "request_latency_ms",
                    "value": 450,
                },
                {
                    "service_id": "ii-product-service",
                    "metric": "error_rate",
                    "value": 0.01,
                },
            ],
            self.thresholds,
        )

        self.assertFalse(result["verified"])

    def test_missing_required_metric_cannot_verify_recovery(self):
        result = verify_recovery(
            [
                {
                    "service_id": "ii-product-service",
                    "metric": "request_latency_ms",
                    "value": 120,
                },
            ],
            self.thresholds,
        )

        self.assertFalse(result["verified"])

    def test_builds_recovery_evidence(self):
        verification = verify_recovery(
            [
                {
                    "service_id": "ii-product-service",
                    "metric": "request_latency_ms",
                    "value": 120,
                },
                {
                    "service_id": "ii-product-service",
                    "metric": "error_rate",
                    "value": 0.01,
                },
            ],
            self.thresholds,
        )

        evidence = build_recovery_evidence(
            "11111111-1111-1111-1111-111111111111",
            "ii-product-service",
            verification,
            [{"type": "metric", "ref": "metric-1"}],
        )

        UUID(evidence["evidence_id"])
        self.assertTrue(evidence["verified"])
        self.assertEqual(evidence["type"], "recovery_verification")

    def test_builds_recovery_event(self):
        verification = verify_recovery(
            [
                {
                    "service_id": "ii-product-service",
                    "metric": "request_latency_ms",
                    "value": 120,
                },
                {
                    "service_id": "ii-product-service",
                    "metric": "error_rate",
                    "value": 0.01,
                },
            ],
            self.thresholds,
        )

        evidence = build_recovery_evidence(
            "11111111-1111-1111-1111-111111111111",
            "ii-product-service",
            verification,
        )

        event = build_recovery_event(
            evidence,
            "22222222-2222-2222-2222-222222222222",
            "11111111-1111-1111-1111-111111111111",
        )

        UUID(event["event_id"])
        self.assertEqual(event["event_type"], "RECOVERY_EVIDENCE")
        self.assertEqual(
            event["incident_id"],
            "11111111-1111-1111-1111-111111111111",
        )
        self.assertTrue(event["payload"]["verified"])


if __name__ == "__main__":
    unittest.main()
