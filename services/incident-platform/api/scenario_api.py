from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from scenario_service import (
    ScenarioValidationError,
    execute_scenario,
    get_run,
    get_scenario,
    list_scenarios,
)


router = APIRouter(tags=["scenarios"])


class ScenarioRunRequest(BaseModel):
    parameters: Dict[str, Any] = Field(default_factory=dict)
    incident_id: Optional[str] = None
    created_by: str = Field(default="operator", min_length=1, max_length=120)


@router.get("/api/scenarios")
def scenarios():
    return list_scenarios()


@router.get("/api/scenarios/{scenario_id}")
def scenario(scenario_id: str):
    result = get_scenario(scenario_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Scenario not found",
        )

    return result


@router.post("/api/scenarios/{scenario_id}/runs", status_code=201)
def run_scenario(
    scenario_id: str,
    request: ScenarioRunRequest,
):
    try:
        return execute_scenario(
            scenario_id=scenario_id,
            parameters=request.parameters,
            incident_id=request.incident_id,
            created_by=request.created_by,
        )
    except ScenarioValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Scenario execution failed: {exc}",
        )


@router.get("/api/scenario-runs/{run_id}")
def scenario_run(run_id: str):
    result = get_run(run_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Scenario run not found",
        )

    return result
