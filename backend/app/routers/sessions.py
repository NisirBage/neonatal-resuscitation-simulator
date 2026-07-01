import json
import logging
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

logger = logging.getLogger(__name__)

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
    corrective_ventilation_cycles: int = 0


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


class ReplayEventItem(BaseModel):
    id: str
    type: str
    timestamp: str
    state_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    transition_id: str | None = None
    target_state_id: str | None = None


class ReplayResponse(BaseModel):
    session_id: UUID
    event_count: int
    events: list[ReplayEventItem]


@router.post(
    "/sessions/start",
    response_model=SessionResponse,
    summary="Start a simulation session",
    description="Creates a new in-memory session for the given scenario and returns the initial FSM state.",
    responses={404: {"description": "Scenario not found"}, 422: {"description": "FSM initialisation error"}},
)
async def start_session(request: StartSessionRequest) -> SessionResponse:
    scenario = _load_scenario_by_id(request.scenario_id)
    try:
        record = await scenario_runner.start_session(scenario)
    except (FSMError, ValueError) as exc:
        raise _http_error_from_exception(exc) from exc

    logger.info(
        f"Session created: id={record.session_id} scenario={request.scenario_id}",
        extra={"event": "session_created"},
    )
    return _build_session_response(record)


@router.get(
    "/sessions",
    response_model=list[SessionListItem],
    summary="List active sessions",
    description="Returns all sessions currently held in memory (running or recently stopped).",
)
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


@router.get(
    "/sessions/{session_id}",
    response_model=SessionStateResponse,
    summary="Get session state",
    description="Returns the current FSM state plus the full event history for the session.",
    responses={404: {"description": "Session not found"}},
)
async def get_session(session_id: UUID) -> SessionStateResponse:
    try:
        record = _get_active_record(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    return _build_session_state_response(record)


@router.get(
    "/sessions/{session_id}/export/csv",
    summary="Export raw event log as CSV",
    description="Downloads a UTF-8 BOM CSV of every FSM event with timestamps, state IDs, and payloads.",
    responses={404: {"description": "Session not found"}},
)
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


@router.get(
    "/sessions/{session_id}/export/clinical-csv",
    summary="Export clinical timeline as CSV",
    description=(
        "Downloads a second-by-second clinical timeline CSV suitable for instructor review. "
        "Columns: Time, Voice Command / Response, System Action, Instructor Action, Notes."
    ),
    responses={404: {"description": "Session not found"}},
)
async def export_clinical_csv(session_id: UUID) -> Response:
    try:
        record = _get_active_record(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    from app.services.clinical_timeline_service import generate_clinical_csv
    csv_content = generate_clinical_csv(
        session_id=session_id,
        history=record.engine.get_history(),
        scenario=record.scenario,
    )
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="session_{session_id}_clinical.csv"'
            ),
        },
    )


@router.get(
    "/sessions/{session_id}/export/clinical-xlsx",
    summary="Export professional assessment report as Excel",
    description=(
        "Downloads a formatted XLSX workbook with colour-coded clinical timeline, "
        "clinical phase column, training score, and simulation summary section."
    ),
    responses={404: {"description": "Session not found"}},
)
async def export_clinical_xlsx(session_id: UUID) -> Response:
    try:
        record = _get_active_record(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    from app.services.clinical_timeline_service import generate_clinical_xlsx
    xlsx_bytes = generate_clinical_xlsx(
        session_id=session_id,
        history=record.engine.get_history(),
        scenario=record.scenario,
        current_state_id=record.engine.get_current_state().id,
    )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="session_{session_id}_clinical.xlsx"'
            ),
        },
    )


@router.get(
    "/sessions/{session_id}/metrics",
    response_model=SessionMetricsResponse,
    summary="Get session performance metrics",
    description=(
        "Computes and returns training metrics in a single O(N) pass over the event history: "
        "total duration, student inputs, voice inputs, successful transitions, "
        "unmatched inputs, instructor interventions, timer events, and completion status."
    ),
    responses={404: {"description": "Session not found"}},
)
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


@router.get(
    "/sessions/{session_id}/replay",
    response_model=ReplayResponse,
    summary="Get event replay data",
    description=(
        "Returns the ordered event history for the session replay viewer. "
        "Events include state transitions, student inputs, timer fires, and instructor overrides."
    ),
    responses={404: {"description": "Session not found"}},
)
async def get_session_replay(session_id: UUID) -> ReplayResponse:
    try:
        record = _get_active_record(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    history = record.engine.get_history()
    events = [
        ReplayEventItem(
            id=str(event.id),
            type=event.type,
            timestamp=event.timestamp.isoformat(),
            state_id=event.state_id,
            payload=event.payload,
            transition_id=event.transition_id,
            target_state_id=event.target_state_id,
        )
        for event in history
    ]
    return ReplayResponse(
        session_id=session_id,
        event_count=len(events),
        events=events,
    )


@router.get(
    "/sessions/{session_id}/report/pdf",
    summary="Generate PDF performance report",
    description=(
        "Generates and downloads a ReportLab PDF with session metadata, training score, "
        "performance metrics table, and full event timeline."
    ),
    responses={404: {"description": "Session not found"}},
)
async def get_session_pdf_report(session_id: UUID) -> Response:
    try:
        record = _get_active_record(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    from app.services.report_service import generate_session_pdf
    logger.info(
        f"PDF report requested: session={session_id}",
        extra={"event": "report_pdf"},
    )
    pdf_bytes = generate_session_pdf(
        session_id=str(session_id),
        scenario_id=record.scenario.id,
        scenario_name=record.scenario.name,
        history=record.engine.get_history(),
        current_state_id=record.engine.get_current_state().id,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="session_{session_id}_report.pdf"',
        },
    )


@router.post(
    "/sessions/{session_id}/input",
    response_model=SessionResponse,
    summary="Submit student response",
    description=(
        "Processes a student action (yes/no answer or text) and advances the FSM "
        "if a matching transition exists. Returns the updated state."
    ),
    responses={404: {"description": "Session not found"}, 422: {"description": "Invalid action or FSM error"}},
)
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

    logger.info(
        f"Student input: session={session_id} action={request.action_id} response={request.response!r}",
        extra={"event": "student_input"},
    )
    return _build_session_response(record)


@router.post(
    "/sessions/{session_id}/timer/{timer_id}",
    response_model=SessionResponse,
    summary="Fire a timer event",
    description="Manually triggers a timer, advancing the FSM via its timer-triggered transition.",
    responses={404: {"description": "Session not found"}, 422: {"description": "Timer or FSM error"}},
)
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

    logger.info(
        f"Timer event: session={session_id} timer={timer_id}",
        extra={"event": "timer_event"},
    )
    return _build_session_response(record)


@router.post(
    "/sessions/{session_id}/instructor",
    response_model=SessionResponse,
    summary="Send instructor override",
    description=(
        "Injects a named instructor event that can force a state transition "
        "regardless of the student's current answer. Used by the instructor dashboard."
    ),
    responses={404: {"description": "Session not found"}, 422: {"description": "Event or FSM error"}},
)
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

    logger.info(
        f"Instructor override: session={session_id} event={request.event_name}",
        extra={"event": "instructor_override"},
    )
    return _build_session_response(record)


@router.post(
    "/sessions/{session_id}/stop",
    response_model=SessionResponse,
    summary="Stop a session",
    description="Marks the session as stopped and persists its final state to the database.",
    responses={404: {"description": "Session not found"}},
)
async def stop_session(session_id: UUID) -> SessionResponse:
    try:
        record = await scenario_runner.stop_session(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc

    logger.info(
        f"Session stopped: id={session_id}",
        extra={"event": "session_stopped"},
    )
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


def _count_corrective_cycles(history: list[SimulationEvent]) -> int:
    return sum(
        1 for e in history
        if e.type == "state_transition" and e.transition_id == "corrective_ventilation_timer_done"
    )


def _build_session_response(record: SessionRecord) -> SessionResponse:
    history = record.engine.get_history()
    return SessionResponse(
        session_id=record.session_id,
        scenario_id=record.scenario.id,
        status=record.status,
        current_state=_build_current_state_response(record.engine.get_current_state()),
        corrective_ventilation_cycles=_count_corrective_cycles(history),
    )


def _list_active_records() -> list[SessionRecord]:
    with session_manager._lock:
        return list(session_manager._sessions.values())


def _get_active_record(session_id: UUID) -> SessionRecord:
    with session_manager._lock:
        return session_manager._get_record(session_id)


def _build_session_state_response(record: SessionRecord) -> SessionStateResponse:
    history = record.engine.get_history()
    return SessionStateResponse(
        session_id=record.session_id,
        scenario_id=record.scenario.id,
        status=record.status,
        current_state=_build_current_state_response(record.engine.get_current_state()),
        history=history,
        corrective_ventilation_cycles=_count_corrective_cycles(history),
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
