import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "services" / "intelligence-engine"

sys.path.insert(0, str(ENGINE))

from telemetry_baseline import (
    baseline_metric,
    detect_zscore,
    severity_from_zscore
)

from anomaly_detector import (
    build_anomaly,
    build_anomaly_event
)


class TelemetryBaselineTests(unittest.TestCase):

    def test_baseline(self):
        result = baseline_metric([
            {"value": 10},
            {"value": 12},
            {"value": 14}
        ])

        self.assertEqual(result["expected_value"], 12)
        self.assertGreater(result["stddev"], 0)

    def test_zscore_detects_outlier(self):
        result = detect_zscore(
            observed=20,
            expected=10,
            stddev=2,
            threshold=3
        )

        self.assertTrue(result["detected"])
        self.assertEqual(result["z_score"], 5)

    def test_normal_value_not_anomaly(self):
        result = detect_zscore(
            observed=11,
            expected=10,
            stddev=2,
            threshold=3
        )

        self.assertFalse(result["detected"])

    def test_severity(self):
        self.assertEqual(
            severity_from_zscore(3),
            "MEDIUM"
        )

        self.assertEqual(
            severity_from_zscore(4),
            "HIGH"
        )

        self.assertEqual(
            severity_from_zscore(5),
            "CRITICAL"
        )


class AnomalyDetectorTests(unittest.TestCase):

    def test_builds_anomaly(self):
        anomaly = build_anomaly(
            service_id="order-service",
            metric="request_latency_ms",
            observed_value=200,
            baseline_values=[10, 12, 11, 13, 12],
            window_start="2026-10-04T15:00:00Z",
            window_end="2026-10-04T15:01:00Z"
        )

        self.assertIsNotNone(anomaly)
        self.assertEqual(
            anomaly["service_id"],
            "order-service"
        )
        self.assertEqual(
            anomaly["metric"],
            "request_latency_ms"
        )
        self.assertIn(
            anomaly["severity"],
            ["MEDIUM", "HIGH", "CRITICAL"]
        )
        self.assertGreater(anomaly["confidence"], 0)

    def test_normal_metric_returns_none(self):
        anomaly = build_anomaly(
            service_id="order-service",
            metric="request_latency_ms",
            observed_value=11,
            baseline_values=[10, 12, 11, 13, 12],
            window_start="2026-10-04T15:00:00Z",
            window_end="2026-10-04T15:01:00Z"
        )

        self.assertIsNone(anomaly)

    def test_event_envelope(self):
        anomaly = build_anomaly(
            service_id="order-service",
            metric="error_rate",
            observed_value=50,
            baseline_values=[1, 2, 1, 2, 1],
            window_start="2026-10-04T15:00:00Z",
            window_end="2026-10-04T15:01:00Z"
        )

        event = build_anomaly_event(anomaly)

        self.assertEqual(
            event["event_type"],
            "ANOMALY_DETECTED"
        )
        self.assertEqual(
            event["schema_version"],
            1
        )
        self.assertEqual(
            event["producer"],
            "intelligence-engine"
        )
        self.assertEqual(
            event["payload"]["service_id"],
            "order-service"
        )
        self.assertIsNone(event["incident_id"])
        self.assertTrue(event["event_id"])
        self.assertTrue(event["correlation_id"])


if __name__ == "__main__":
    unittest.main()
