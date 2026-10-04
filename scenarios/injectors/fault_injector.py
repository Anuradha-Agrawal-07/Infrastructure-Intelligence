from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict


class ScenarioValidationError(ValueError):
    pass


@dataclass
class InjectionResult:
    run_id: str
    injector_type: str
    status: str
    signals: Dict[str, Any]
    started_at: float
    completed_at: float


class FaultInjector:
    """
    Safe scenario injector contract.

    Implementations are synthetic only.
    No arbitrary shell commands are accepted.
    """

    name = "base"

    def validate(self, parameters: Dict[str, Any]) -> None:
        raise NotImplementedError

    def inject(self, parameters: Dict[str, Any], timeout_seconds: int) -> InjectionResult:
        raise NotImplementedError

    def recover(self, parameters: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
        raise NotImplementedError

    def verify(self, parameters: Dict[str, Any], recovery_result: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class SyntheticLatencyInjector(FaultInjector):
    name = "synthetic_latency"

    def validate(self, parameters):
        latency_ms = int(parameters.get("latency_ms", 1200))
        duration = int(parameters.get("duration_seconds", 5))

        if not 100 <= latency_ms <= 5000:
            raise ScenarioValidationError("latency_ms must be between 100 and 5000")

        if not 1 <= duration <= 30:
            raise ScenarioValidationError("duration_seconds must be between 1 and 30")

    def inject(self, parameters, timeout_seconds):
        self.validate(parameters)

        latency_ms = int(parameters.get("latency_ms", 1200))
        duration = int(parameters.get("duration_seconds", 5))

        if duration > timeout_seconds:
            raise ScenarioValidationError("scenario duration exceeds timeout")

        started = time.time()

        return InjectionResult(
            run_id=str(uuid.uuid4()),
            injector_type=self.name,
            status="INJECTED",
            signals={
                "request_latency_ms": latency_ms,
                "error_rate": min(1.0, latency_ms / 10000.0),
                "duration_seconds": duration,
            },
            started_at=started,
            completed_at=time.time(),
        )

    def recover(self, parameters, timeout_seconds):
        return {
            "recovered": True,
            "request_latency_ms": 0,
            "error_rate": 0.0,
        }

    def verify(self, parameters, recovery_result):
        latency = float(recovery_result.get("request_latency_ms", 0))
        error_rate = float(recovery_result.get("error_rate", 1))

        passed = latency <= 200 and error_rate <= 0.05

        return {
            "verified": passed,
            "checks": {
                "request_latency_ms": {
                    "observed": latency,
                    "threshold": 200,
                    "passed": latency <= 200,
                },
                "error_rate": {
                    "observed": error_rate,
                    "threshold": 0.05,
                    "passed": error_rate <= 0.05,
                },
            },
        }


class SyntheticErrorRateInjector(FaultInjector):
    name = "synthetic_error_rate"

    def validate(self, parameters):
        error_rate = float(parameters.get("error_rate", 0.25))
        duration = int(parameters.get("duration_seconds", 5))

        if not 0.05 <= error_rate <= 1.0:
            raise ScenarioValidationError("error_rate must be between 0.05 and 1.0")

        if not 1 <= duration <= 30:
            raise ScenarioValidationError("duration_seconds must be between 1 and 30")

    def inject(self, parameters, timeout_seconds):
        self.validate(parameters)

        error_rate = float(parameters.get("error_rate", 0.25))
        duration = int(parameters.get("duration_seconds", 5))

        if duration > timeout_seconds:
            raise ScenarioValidationError("scenario duration exceeds timeout")

        now = time.time()

        return InjectionResult(
            run_id=str(uuid.uuid4()),
            injector_type=self.name,
            status="INJECTED",
            signals={
                "error_rate": error_rate,
                "http_5xx_rate": error_rate,
                "duration_seconds": duration,
            },
            started_at=now,
            completed_at=time.time(),
        )

    def recover(self, parameters, timeout_seconds):
        return {
            "recovered": True,
            "error_rate": 0.0,
            "http_5xx_rate": 0.0,
        }

    def verify(self, parameters, recovery_result):
        error_rate = float(recovery_result.get("error_rate", 1))
        five_xx = float(recovery_result.get("http_5xx_rate", 1))

        return {
            "verified": error_rate <= 0.05 and five_xx <= 0.05,
            "checks": {
                "error_rate": {
                    "observed": error_rate,
                    "threshold": 0.05,
                    "passed": error_rate <= 0.05,
                },
                "http_5xx_rate": {
                    "observed": five_xx,
                    "threshold": 0.05,
                    "passed": five_xx <= 0.05,
                },
            },
        }


class SyntheticDependencyFailureInjector(FaultInjector):
    name = "synthetic_dependency_failure"

    def validate(self, parameters):
        dependency = str(parameters.get("dependency", "postgres"))
        duration = int(parameters.get("duration_seconds", 5))

        if not 1 <= len(dependency) <= 100:
            raise ScenarioValidationError("dependency must contain 1-100 characters")

        if not 1 <= duration <= 30:
            raise ScenarioValidationError("duration_seconds must be between 1 and 30")

    def inject(self, parameters, timeout_seconds):
        self.validate(parameters)

        dependency = str(parameters.get("dependency", "postgres"))
        duration = int(parameters.get("duration_seconds", 5))

        if duration > timeout_seconds:
            raise ScenarioValidationError("scenario duration exceeds timeout")

        now = time.time()

        return InjectionResult(
            run_id=str(uuid.uuid4()),
            injector_type=self.name,
            status="INJECTED",
            signals={
                "dependency": dependency,
                "connection_count": 0,
                "error_rate": 0.75,
                "duration_seconds": duration,
            },
            started_at=now,
            completed_at=time.time(),
        )

    def recover(self, parameters, timeout_seconds):
        return {
            "recovered": True,
            "connection_count": 10,
            "error_rate": 0.0,
        }

    def verify(self, parameters, recovery_result):
        connections = float(recovery_result.get("connection_count", 0))
        error_rate = float(recovery_result.get("error_rate", 1))

        return {
            "verified": connections > 0 and error_rate <= 0.05,
            "checks": {
                "connection_count": {
                    "observed": connections,
                    "minimum": 1,
                    "passed": connections > 0,
                },
                "error_rate": {
                    "observed": error_rate,
                    "threshold": 0.05,
                    "passed": error_rate <= 0.05,
                },
            },
        }


INJECTORS = {
    "synthetic_latency": SyntheticLatencyInjector(),
    "synthetic_error_rate": SyntheticErrorRateInjector(),
    "synthetic_dependency_failure": SyntheticDependencyFailureInjector(),
}


def get_injector(injector_type: str) -> FaultInjector:
    try:
        return INJECTORS[injector_type]
    except KeyError:
        raise ScenarioValidationError(
            f"Injector '{injector_type}' is not allowlisted"
        )
