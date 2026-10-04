import sys
import unittest
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "services" / "intelligence-engine"

if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from intelligence_events import (
    build_correlation_event,
    build_event,
    build_impact_event,
    build_rca_event,
)


class IntelligenceEventsTests(unittest.TestCase):

    def test_event_envelope_fields(self):
        correlation_id = "11111111-1111-1111-1111-111111111111"

        event = build_event(
            "CORRELATION_RESULT",
            {"incident_candidate_id": "candidate-1"},
            correlation_id,
        )

        self.assertEqual(event["event_type"], "CORRELATION_RESULT")
        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["producer"], "intelligence-engine")
        self.assertIsNone(event["incident_id"])

        UUID(event["event_id"])
        UUID(event["correlation_id"])

        self.assertTrue(event["occurred_at"].endswith("Z"))

    def test_correlation_event_generates_correlation_id(self):
        result = {
            "incident_candidate_id": "candidate-42",
            "affected_services": ["ii-product-service"],
            "confidence": 0.91,
        }

        event = build_correlation_event(result)

        self.assertEqual(event["event_type"], "CORRELATION_RESULT")
        UUID(event["correlation_id"])
        self.assertEqual(event["payload"], result)

    def test_rca_event_preserves_incident_association(self):
        result = {
            "primary_suspect": "ii-postgres",
            "hypotheses": [],
            "evidence": [],
        }

        event = build_rca_event(
            result,
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        )

        self.assertEqual(event["event_type"], "RCA_RESULT")
        self.assertEqual(
            event["incident_id"],
            "22222222-2222-2222-2222-222222222222",
        )
        self.assertEqual(event["payload"], result)

    def test_impact_event_preserves_payload(self):
        result = {
            "priority": "P1",
            "response_target_minutes": 30,
            "affected_services": ["ii-product-service"],
        }

        event = build_impact_event(
            result,
            "11111111-1111-1111-1111-111111111111",
        )

        self.assertEqual(event["event_type"], "IMPACT_RESULT")
        self.assertIsNone(event["incident_id"])
        self.assertEqual(event["payload"], result)


if __name__ == "__main__":
    unittest.main()
