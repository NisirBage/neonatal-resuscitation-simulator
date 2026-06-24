import json
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.fsm import FSMError, SimulationEvent
from app.scenario import Scenario, State, load_scenario
from app.scenario_runner import ScenarioRunner
from app.services.export_service import export_session_history_csv
from app.session_service import SessionManager, SessionRecord


router = APIRouter()

SCENARIOS_DIR = Path(settings.SCENARIOS_DIR)

session_manager = SessionManager()
scenario_runner = ScenarioRunner(session_manager=session_manager)


class StartSessionRequest(BaseModel):
    scenario_id: str


class StudentInputRequest(BaseModel):
    action_id: str
    response: str | bool


class InstructorEventRequest(BaseModel):
    event_name: str


class ActionSummary(BaseModel):
    id: str
    type: str
    prompt: str | None = None
    options: list[str] = Field(default_factory=list)
    transcript_required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimerSummary(BaseModel):
    id: str
    duration_seconds: int
    event: str
    auto_start: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionSummary(BaseModel):
    id: str
    trigger: str
    target_state: str
    action_id: str | None = None
    timer_id: str | None = None
    instructor_event: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurrentStateResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    actions: list[ActionSummary] = Field(default_factory=list)
    timers: list[TimerSummary] = Field(default_factory=list)
    transitions: list[TransitionSummary] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    session_id: UUID
    scenario_id: str
    status: str
    current_state: CurrentStateResponse


class SessionListItem(BaseModel):
    session_id: UUID
    scenario_id: str
    scenario_name: str
    status: str
    current_state_id: str


class SessionStateResponse(SessionResponse):
    history: list[SimulationEvent] = Field(default_factory=list)


class SessionMetricsResponse(BaseModel):
    session_id: UUID
    total_duration_seconds: float
    student_input_count: int
    voice_input_count: int
    successful_transition_count: int
    no_transition_count: int
    instructor_intervention_count: int
    timer_event_count: int
    completion_status: str


@router.post("/sessions/start", response_model=SessionResponse)
async def start_session(request: StartSessionRequest) -> SessionResponse:
    scenario = _load_scenario_by_id(request.scenario_id)
    try:
        record = await scenario_runner.start_session(scenario)
    except (FSMError, ValueError) as exc:
        raise _http_error_from_exception(exc) from exc

    return _build_session_response(record)


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions() -> list[SessionListItem]:
    records = _list_active_records()
    return [
        SessionListItem(
            session_id=record.session_id,
            scenario_id=record.scenario.id,
            scenario_name=record.scenario.name,
            status=record.status,
            current_state_id=record.engine.serialize()["current_state_id"],
        )
        for record in records
    ]


@router.get("/sessions/{session_id}", response_model=SessionStateResponse)
async def get_session(session_id: UUID) -> SessionStateResponse:
    try:
        record = _get_active_record(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    return _build_session_state_response(record)


@router.get("/sessions/{session_id}/export/csv")
async def export_session_csv(session_id: UUID) -> Response:
    try:
        record = _get_active_record(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    csv_content = export_session_history_csv(
        session_id=session_id,
        history=record.engine.get_history(),
    )
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="session_{session_id}.csv"'
        },
    )


@router.get("/sessions/{session_id}/metrics", response_model=SessionMetricsResponse)
async def get_session_metrics(session_id: UUID) -> SessionMetricsResponse:
    try:
        record = _get_active_record(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    from app.services.metrics_service import compute_session_metrics
    metrics = compute_session_metrics(
        history=record.engine.get_history(),
        current_state_id=record.engine.get_current_state().id,
    )
    return SessionMetricsResponse(session_id=session_id, **metrics)


@router.post("/sessions/{session_id}/input", response_model=SessionResponse)
async def process_student_input(
    session_id: UUID,
    request: StudentInputRequest,
) -> SessionResponse:
    try:
        record = await scenario_runner.process_student_input(
            session_id=session_id,
            action_id=request.action_id,
            response=request.response,
        )
    except KeyError as exc:
        raise _not_found(session_id) from exc
    except (FSMError, RuntimeError, ValueError) as exc:
        raise _http_error_from_exception(exc) from exc

    return _build_session_response(record)


@router.post("/sessions/{session_id}/timer/{timer_id}", response_model=SessionResponse)
async def process_timer(session_id: UUID, timer_id: str) -> SessionResponse:
    try:
        record = await scenario_runner.process_timer(
            session_id=session_id,
            timer_id=timer_id,
        )
    except KeyError as exc:
        raise _not_found(session_id) from exc
    except (FSMError, RuntimeError, ValueError) as exc:
        raise _http_error_from_exception(exc) from exc

    return _build_session_response(record)


@router.post("/sessions/{session_id}/instructor", response_model=SessionResponse)
async def process_instructor_event(
    session_id: UUID,
    request: InstructorEventRequest,
) -> SessionResponse:
    try:
        record = await scenario_runner.process_instructor_action(
            session_id=session_id,
            event_name=request.event_name,
        )
    except KeyError as exc:
        raise _not_found(session_id) from exc
    except (FSMError, RuntimeError, ValueError) as exc:
        raise _http_error_from_exception(exc) from exc

    return _build_session_response(record)


@router.post("/sessions/{session_id}/stop", response_model=SessionResponse)
async def stop_session(session_id: UUID) -> SessionResponse:
    try:
        record = await scenario_runner.stop_session(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    return _build_session_response(record)


def _load_scenario_by_id(scenario_id: str) -> Scenario:
    if not scenario_id or any(character in scenario_id for character in ("/", "\\")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid scenario id",
        )

    if not SCENARIOS_DIR.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="scenarios directory does not exist",
        )

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


def _build_session_response(record: SessionRecord) -> SessionResponse:
    return SessionResponse(
        session_id=record.session_id,
        scenario_id=record.scenario.id,
        status=record.status,
        current_state=_build_current_state_response(record.engine.get_current_state()),
    )


def _list_active_records() -> list[SessionRecord]:
    with session_manager._lock:
        return list(session_manager._sessions.values())


def _get_active_record(session_id: UUID) -> SessionRecord:
    with session_manager._lock:
        return session_manager._get_record(session_id)


def _build_session_state_response(record: SessionRecord) -> SessionStateResponse:
    return SessionStateResponse(
        session_id=record.session_id,
        scenario_id=record.scenario.id,
        status=record.status,
        current_state=_build_current_state_response(record.engine.get_current_state()),
        history=record.engine.get_history(),
    )


def _build_current_state_response(state: State) -> CurrentStateResponse:
    return CurrentStateResponse(
        id=state.id,
        name=state.name,
        description=state.description,
        actions=[
            ActionSummary(
                id=action.id,
                type=action.type,
                prompt=action.prompt,
                options=action.options,
                transcript_required=action.transcript_required,
                metadata=action.metadata,
            )
            for action in state.actions
        ],
        timers=[
            TimerSummary(
                id=timer.id,
                duration_seconds=timer.duration_seconds,
                event=timer.event,
                auto_start=timer.auto_start,
                metadata=timer.metadata,
            )
            for timer in state.timers
        ],
        transitions=[
            TransitionSummary(
                id=transition.id,
                trigger=transition.trigger,
                target_state=transition.target_state,
                action_id=transition.action_id,
                timer_id=transition.timer_id,
                instructor_event=transition.instructor_event,
                metadata=transition.metadata,
            )
            for transition in state.transitions
        ],
        metadata=state.metadata,
    )


def _not_found(session_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"session '{session_id}' was not found",
    )


def _http_error_from_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, FSMError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.to_dict(),
        )

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
    )
