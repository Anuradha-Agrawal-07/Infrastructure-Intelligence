from __future__ import annotations

from enum import Enum


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    MITIGATING = "MITIGATING"
    RECOVERY_VERIFY = "RECOVERY_VERIFY"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    REOPENED = "REOPENED"


_ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DETECTED: {
        IncidentStatus.ACKNOWLEDGED,
        IncidentStatus.FALSE_POSITIVE,
    },
    IncidentStatus.ACKNOWLEDGED: {
        IncidentStatus.TRIAGED,
        IncidentStatus.FALSE_POSITIVE,
    },
    IncidentStatus.TRIAGED: {
        IncidentStatus.INVESTIGATING,
        IncidentStatus.FALSE_POSITIVE,
    },
    IncidentStatus.INVESTIGATING: {
        IncidentStatus.MITIGATING,
        IncidentStatus.FALSE_POSITIVE,
    },
    IncidentStatus.MITIGATING: {
        IncidentStatus.RECOVERY_VERIFY,
    },
    IncidentStatus.RECOVERY_VERIFY: {
        IncidentStatus.RESOLVED,
        IncidentStatus.INVESTIGATING,
    },
    IncidentStatus.RESOLVED: {
        IncidentStatus.REOPENED,
    },
    IncidentStatus.FALSE_POSITIVE: {
        IncidentStatus.RESOLVED,
    },
    IncidentStatus.REOPENED: {
        IncidentStatus.INVESTIGATING,
    },
}


class InvalidIncidentTransition(ValueError):
    pass


def can_transition(
    current: IncidentStatus | str,
    target: IncidentStatus | str,
) -> bool:
    current_status = IncidentStatus(current)
    target_status = IncidentStatus(target)
    return target_status in _ALLOWED_TRANSITIONS.get(current_status, set())


def transition(
    current: IncidentStatus | str,
    target: IncidentStatus | str,
) -> IncidentStatus:
    current_status = IncidentStatus(current)
    target_status = IncidentStatus(target)

    if not can_transition(current_status, target_status):
        raise InvalidIncidentTransition(
            f"Invalid incident transition: "
            f"{current_status.value} -> {target_status.value}"
        )

    return target_status
