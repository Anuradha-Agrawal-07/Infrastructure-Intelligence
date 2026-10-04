import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "services" / "incident-platform"

if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

from incident_lifecycle import (
    IncidentStatus,
    InvalidIncidentTransition,
    can_transition,
    transition,
)
from models.incident import Incident
from repository.incident_repository import IncidentRepository


def test_initial_status_is_detected():
    incident = Incident(
        title="Database latency",
        priority="P1",
    )

    assert incident.status == IncidentStatus.DETECTED
    assert incident.version == 1


def test_valid_lifecycle_transition():
    assert transition(
        IncidentStatus.DETECTED,
        IncidentStatus.ACKNOWLEDGED,
    ) == IncidentStatus.ACKNOWLEDGED

    assert transition(
        IncidentStatus.ACKNOWLEDGED,
        IncidentStatus.TRIAGED,
    ) == IncidentStatus.TRIAGED

    assert transition(
        IncidentStatus.TRIAGED,
        IncidentStatus.INVESTIGATING,
    ) == IncidentStatus.INVESTIGATING

    assert transition(
        IncidentStatus.INVESTIGATING,
        IncidentStatus.MITIGATING,
    ) == IncidentStatus.MITIGATING

    assert transition(
        IncidentStatus.MITIGATING,
        IncidentStatus.RECOVERY_VERIFY,
    ) == IncidentStatus.RECOVERY_VERIFY

    assert transition(
        IncidentStatus.RECOVERY_VERIFY,
        IncidentStatus.RESOLVED,
    ) == IncidentStatus.RESOLVED


def test_invalid_transition_is_rejected():
    assert not can_transition(
        IncidentStatus.DETECTED,
        IncidentStatus.RESOLVED,
    )

    try:
        transition(
            IncidentStatus.DETECTED,
            IncidentStatus.RESOLVED,
        )
        assert False, "Expected InvalidIncidentTransition"
    except InvalidIncidentTransition:
        pass


def test_false_positive_and_reopen_paths():
    assert can_transition(
        IncidentStatus.DETECTED,
        IncidentStatus.FALSE_POSITIVE,
    )

    assert can_transition(
        IncidentStatus.FALSE_POSITIVE,
        IncidentStatus.RESOLVED,
    )

    assert can_transition(
        IncidentStatus.RESOLVED,
        IncidentStatus.REOPENED,
    )

    assert can_transition(
        IncidentStatus.REOPENED,
        IncidentStatus.INVESTIGATING,
    )


def test_repository_create_and_get():
    repo = IncidentRepository()

    incident = Incident(
        title="Product latency degradation",
        priority="P1",
    )

    repo.create(incident)

    stored = repo.get(incident.incident_id)

    assert stored is incident
    assert stored.title == "Product latency degradation"


def test_repository_rejects_duplicate_incident():
    repo = IncidentRepository()

    incident = Incident(
        title="Duplicate test",
        priority="P2",
    )

    repo.create(incident)

    try:
        repo.create(incident)
        assert False, "Expected duplicate incident failure"
    except ValueError:
        pass


def test_repository_status_change_increments_version():
    repo = IncidentRepository()

    incident = Incident(
        title="Service degradation",
        priority="P1",
    )

    repo.create(incident)

    old_version = incident.version

    updated = repo.change_status(
        incident.incident_id,
        IncidentStatus.ACKNOWLEDGED,
        uuid4(),
    )

    assert updated.status == IncidentStatus.ACKNOWLEDGED
    assert updated.version == old_version + 1

    timeline = repo.timeline(incident.incident_id)

    assert len(timeline) == 1
    assert timeline[0].event_type == "INCIDENT_STATUS_CHANGED"
    assert timeline[0].sequence == 1


def test_repository_missing_incident_is_rejected():
    repo = IncidentRepository()

    try:
        repo.change_status(
            uuid4(),
            IncidentStatus.ACKNOWLEDGED,
            uuid4(),
        )
        assert False, "Expected missing incident failure"
    except KeyError:
        pass


def test_repository_timeline_sequences_are_monotonic():
    repo = IncidentRepository()

    incident = Incident(
        title="Timeline test",
        priority="P2",
    )

    repo.create(incident)

    repo.change_status(
        incident.incident_id,
        IncidentStatus.ACKNOWLEDGED,
        uuid4(),
    )

    repo.change_status(
        incident.incident_id,
        IncidentStatus.TRIAGED,
        uuid4(),
    )

    timeline = repo.timeline(incident.incident_id)

    assert [event.sequence for event in timeline] == [1, 2]

