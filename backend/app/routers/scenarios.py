import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.scenario import Scenario, load_scenario, validate_scenario


router = APIRouter()

SCENARIOS_DIR = Path(settings.SCENARIOS_DIR)


class ScenarioListItem(BaseModel):
    file_name: str
    id: str
    name: str
    version: str


class ScenarioMetadataResponse(BaseModel):
    scenario_id: str
    name: str
    version: str
    state_count: int
    initial_state: str


class ScenarioValidationResponse(BaseModel):
    scenario_id: str
    valid: bool
    errors: list[str] = Field(default_factory=list)


class ScenarioLoadResponse(BaseModel):
    scenario_id: str
    name: str
    version: str
    state_count: int


@router.get("/scenarios", response_model=list[ScenarioListItem])
async def list_scenarios() -> list[ScenarioListItem]:
    return _list_available_scenarios()


@router.get("/scenarios/{scenario_id}", response_model=ScenarioMetadataResponse)
async def get_scenario(scenario_id: str) -> ScenarioMetadataResponse:
    scenario = _load_scenario_by_id(scenario_id)
    return ScenarioMetadataResponse(
        scenario_id=scenario.id,
        name=scenario.name,
        version=scenario.version,
        state_count=len(scenario.states),
        initial_state=scenario.initial_state,
    )


@router.post(
    "/scenarios/{scenario_id}/validate",
    response_model=ScenarioValidationResponse,
)
async def validate_scenario_endpoint(scenario_id: str) -> ScenarioValidationResponse:
    try:
        scenario = _load_scenario_by_id(scenario_id)
        validate_scenario(scenario)
    except HTTPException as exc:
        return ScenarioValidationResponse(
            scenario_id=scenario_id,
            valid=False,
            errors=[str(exc.detail)],
        )
    except (ValidationError, ValueError) as exc:
        return ScenarioValidationResponse(
            scenario_id=scenario_id,
            valid=False,
            errors=[str(exc)],
        )

    return ScenarioValidationResponse(scenario_id=scenario.id, valid=True)


@router.post("/scenarios/{scenario_id}/load", response_model=ScenarioLoadResponse)
async def load_scenario_endpoint(scenario_id: str) -> ScenarioLoadResponse:
    scenario = _load_scenario_by_id(scenario_id)
    return ScenarioLoadResponse(
        scenario_id=scenario.id,
        name=scenario.name,
        version=scenario.version,
        state_count=len(scenario.states),
    )


def _list_available_scenarios() -> list[ScenarioListItem]:
    if not SCENARIOS_DIR.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="scenarios directory does not exist",
        )

    scenarios: list[ScenarioListItem] = []
    for scenario_path in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            scenario = load_scenario(str(scenario_path))
        except (OSError, json.JSONDecodeError, ValidationError, ValueError):
            continue

        scenarios.append(
            ScenarioListItem(
                file_name=scenario_path.name,
                id=scenario.id,
                name=scenario.name,
                version=scenario.version,
            )
        )

    return scenarios


def _load_scenario_by_id(scenario_id: str) -> Scenario:
    _validate_scenario_id(scenario_id)

    for scenario_path in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            scenario = load_scenario(str(scenario_path))
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            if scenario_path.stem == scenario_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"scenario '{scenario_id}' is invalid: {exc}",
                ) from exc
            continue

        if scenario.id == scenario_id:
            return scenario

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"scenario '{scenario_id}' was not found",
    )


def _validate_scenario_id(scenario_id: str) -> None:
    if not scenario_id or any(character in scenario_id for character in ("/", "\\")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid scenario id",
        )
