from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from scenarios.injectors.fault_injector import (
    ScenarioValidationError,
    get_injector,
)


ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = ROOT / "scenarios" / "definitions"


def _database_url():
    return os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    )


def _connect():
    return psycopg.connect(_database_url())


def _now():
    return datetime.now(timezone.utc)


def load_definitions():
    definitions = []

    for path in sorted(DEFINITIONS.glob("*.json")):
        with path.open("r", encoding="utf-8-sig") as handle:
            definitions.append(json.load(handle))

    return definitions


def seed_catalog():
    definitions = load_definitions()

    with _connect() as conn:
        for definition in definitions:
            conn.execute(
                """
                INSERT INTO scenario_catalog
                    (
                        scenario_id,
                        name,
                        category,
                        description,
                        risk_level,
                        injector_type,
                        parameters,
                        expected_signals,
                        recovery_required,
                        verification_required
                    )
                VALUES
                    (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                ON CONFLICT (scenario_id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    risk_level = EXCLUDED.risk_level,
                    injector_type = EXCLUDED.injector_type,
                    parameters = EXCLUDED.parameters,
                    expected_signals = EXCLUDED.expected_signals,
                    recovery_required = EXCLUDED.recovery_required,
                    verification_required = EXCLUDED.verification_required
                """,
                (
                    definition["scenario_id"],
                    definition["name"],
                    definition["category"],
                    definition["description"],
                    definition["risk_level"],
                    definition["injector_type"],
                    json.dumps(definition["parameters"]),
                    json.dumps(definition["expected_signals"]),
                    definition["recovery_required"],
                    definition["verification_required"],
                ),
            )

        conn.commit()

    return definitions


def list_scenarios():
    seed_catalog()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT scenario_id, name, category, description,
                   risk_level, injector_type, parameters,
                   expected_signals, recovery_required,
                   verification_required, enabled
            FROM scenario_catalog
            WHERE enabled = TRUE
            ORDER BY scenario_id
            """
        ).fetchall()

    return [
        {
            "scenario_id": row[0],
            "name": row[1],
            "category": row[2],
            "description": row[3],
            "risk_level": row[4],
            "injector_type": row[5],
            "parameters": row[6],
            "expected_signals": row[7],
            "recovery_required": row[8],
            "verification_required": row[9],
            "enabled": row[10],
        }
        for row in rows
    ]


def get_scenario(scenario_id):
    seed_catalog()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT scenario_id, name, category, description,
                   risk_level, injector_type, parameters,
                   expected_signals, recovery_required,
                   verification_required, enabled
            FROM scenario_catalog
            WHERE scenario_id = %s
            """,
            (scenario_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "scenario_id": row[0],
        "name": row[1],
        "category": row[2],
        "description": row[3],
        "risk_level": row[4],
        "injector_type": row[5],
        "parameters": row[6],
        "expected_signals": row[7],
        "recovery_required": row[8],
        "verification_required": row[9],
        "enabled": row[10],
    }


def execute_scenario(
    scenario_id,
    parameters,
    incident_id=None,
    created_by="operator",
):
    scenario = get_scenario(scenario_id)

    if scenario is None:
        raise ScenarioValidationError("Scenario not found")

    if not scenario["enabled"]:
        raise ScenarioValidationError("Scenario is disabled")

    injector = get_injector(scenario["injector_type"])

    timeout_seconds = min(
        30,
        max(
            1,
            int(parameters.get("timeout_seconds", 30)),
        ),
    )

    run_id = str(uuid.uuid4())
    started = _now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO scenario_execution_runs
                (
                    run_id,
                    scenario_id,
                    incident_id,
                    status,
                    parameters,
                    started_at,
                    timeout_seconds,
                    created_by
                )
            VALUES
                (%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
            """,
            (
                run_id,
                scenario_id,
                incident_id,
                "VALIDATING",
                json.dumps(parameters),
                started,
                timeout_seconds,
                created_by,
            ),
        )

        conn.execute(
            """
            INSERT INTO scenario_audit_log
                (audit_id, run_id, action, actor, details)
            VALUES
                (%s,%s,%s,%s,%s::jsonb)
            """,
            (
                str(uuid.uuid4()),
                run_id,
                "SCENARIO_VALIDATION_STARTED",
                created_by,
                json.dumps(
                    {
                        "scenario_id": scenario_id,
                        "parameters": parameters,
                    }
                ),
            ),
        )

        conn.commit()

    try:
        injector.validate(parameters)

        with _connect() as conn:
            conn.execute(
                """
                UPDATE scenario_execution_runs
                SET status = 'INJECTING'
                WHERE run_id = %s
                """,
                (run_id,),
            )

            conn.execute(
                """
                INSERT INTO scenario_audit_log
                    (audit_id, run_id, action, actor, details)
                VALUES
                    (%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    "INJECTION_STARTED",
                    created_by,
                    json.dumps(
                        {
                            "injector_type": scenario["injector_type"],
                            "timeout_seconds": timeout_seconds,
                        }
                    ),
                ),
            )

            conn.commit()

        result = injector.inject(parameters, timeout_seconds)

        with _connect() as conn:
            conn.execute(
                """
                UPDATE scenario_execution_runs
                SET status = 'INJECTED',
                    result = %s::jsonb
                WHERE run_id = %s
                """,
                (
                    json.dumps(
                        {
                            "status": result.status,
                            "signals": result.signals,
                            "injector_type": result.injector_type,
                        }
                    ),
                    run_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO scenario_audit_log
                    (audit_id, run_id, action, actor, details)
                VALUES
                    (%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    "INJECTION_COMPLETED",
                    created_by,
                    json.dumps(result.signals),
                ),
            )

            conn.commit()

        # Recovery is mandatory for these scenarios.
        recovery_result = injector.recover(
            parameters,
            timeout_seconds,
        )

        with _connect() as conn:
            conn.execute(
                """
                UPDATE scenario_execution_runs
                SET status = 'RECOVERY',
                    recovery_result = %s::jsonb
                WHERE run_id = %s
                """,
                (
                    json.dumps(recovery_result),
                    run_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO scenario_audit_log
                    (audit_id, run_id, action, actor, details)
                VALUES
                    (%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    "RECOVERY_COMPLETED",
                    created_by,
                    json.dumps(recovery_result),
                ),
            )

            conn.commit()

        verification_result = injector.verify(
            parameters,
            recovery_result,
        )

        final_status = (
            "VERIFIED"
            if verification_result.get("verified") is True
            else "RECOVERY_FAILED"
        )

        completed = _now()

        with _connect() as conn:
            conn.execute(
                """
                UPDATE scenario_execution_runs
                SET status = %s,
                    verification_result = %s::jsonb,
                    completed_at = %s
                WHERE run_id = %s
                """,
                (
                    final_status,
                    json.dumps(verification_result),
                    completed,
                    run_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO scenario_audit_log
                    (audit_id, run_id, action, actor, details)
                VALUES
                    (%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    "RECOVERY_VERIFICATION_COMPLETED",
                    created_by,
                    json.dumps(verification_result),
                ),
            )

            conn.commit()

        return {
            "run_id": run_id,
            "scenario_id": scenario_id,
            "status": final_status,
            "result": {
                "signals": result.signals,
                "injector_type": result.injector_type,
            },
            "recovery": recovery_result,
            "verification": verification_result,
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
        }

    except Exception as exc:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE scenario_execution_runs
                SET status = 'FAILED',
                    result = %s::jsonb,
                    completed_at = %s
                WHERE run_id = %s
                """,
                (
                    json.dumps({"error": str(exc)}),
                    _now(),
                    run_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO scenario_audit_log
                    (audit_id, run_id, action, actor, details)
                VALUES
                    (%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    "SCENARIO_FAILED",
                    created_by,
                    json.dumps({"error": str(exc)}),
                ),
            )

            conn.commit()

        raise


def get_run(run_id):
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT run_id, scenario_id, incident_id, status,
                   parameters, result, recovery_result,
                   verification_result, started_at,
                   completed_at, timeout_seconds, created_by
            FROM scenario_execution_runs
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "run_id": str(row[0]),
        "scenario_id": row[1],
        "incident_id": str(row[2]) if row[2] else None,
        "status": row[3],
        "parameters": row[4],
        "result": row[5],
        "recovery": row[6],
        "verification": row[7],
        "started_at": row[8].isoformat() if row[8] else None,
        "completed_at": row[9].isoformat() if row[9] else None,
        "timeout_seconds": row[10],
        "created_by": row[11],
    }
