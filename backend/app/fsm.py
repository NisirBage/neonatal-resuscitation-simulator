from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.scenario import Scenario, State, Transition, validate_scenario


EventType = Literal[
    "session_started",
    "student_input",
    "audio_input",
    "timer_event",
    "instructor_event",
    "state_transition",
    "no_transition",
]


class FSMError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class SessionAlreadyStartedError(FSMError):
    def __init__(self, session_id: UUID):
        super().__init__(
            code="session_already_started",
            message="simulation session has already started",
            details={"session_id": str(session_id)},
        )


class SessionNotStartedError(FSMError):
    def __init__(self) -> None:
        super().__init__(
            code="session_not_started",
            message="simulation session has not started",
        )


class StateNotFoundError(FSMError):
    def __init__(self, state_id: str):
        super().__init__(
            code="state_not_found",
            message="scenario state was not found",
            details={"state_id": state_id},
        )


class ActionNotFoundError(FSMError):
    def __init__(self, state_id: str, action_id: str):
        super().__init__(
            code="action_not_found",
            message="action was not found in the current state",
            details={"state_id": state_id, "action_id": action_id},
        )


class TimerNotFoundError(FSMError):
    def __init__(self, state_id: str, timer_id: str):
        super().__init__(
            code="timer_not_found",
            message="timer was not found in the current state",
            details={"state_id": state_id, "timer_id": timer_id},
        )


class SimulationEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    transition_id: str | None = None
    target_state_id: str | None = None


class SimulationState(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    scenario_id: str
    current_state_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_history: list[SimulationEvent] = Field(default_factory=list)


class FSMEngine:
    def __init__(
        self,
        scenario: Scenario,
        simulation_state: SimulationState | None = None,
    ) -> None:
        self.scenario = validate_scenario(scenario)
        self._states_by_id: dict[str, State] = {
            state.id: state for state in self.scenario.states
        }
        self._lock = RLock()
        self._state = simulation_state

        if self._state is not None:
            self._ensure_state_exists(self._state.current_state_id)

    def start(self, session_id: UUID | None = None) -> SimulationState:
        with self._lock:
            if self._state is not None:
                raise SessionAlreadyStartedError(self._state.session_id)

            now = datetime.now(timezone.utc)
            self._state = SimulationState(
                session_id=session_id or uuid4(),
                scenario_id=self.scenario.id,
                current_state_id=self.scenario.initial_state,
                started_at=now,
                updated_at=now,
            )
            self._append_event(
                SimulationEvent(
                    type="session_started",
                    state_id=self.scenario.initial_state,
                    timestamp=now,
                    payload={
                        "scenario_id": self.scenario.id,
                        "scenario_version": self.scenario.version,
                    },
                )
            )
            return self._copy_state()

    def process_student_input(
        self,
        action_id: str,
        response: str | bool,
    ) -> SimulationState:
        with self._lock:
            state = self._require_state()
            current_state = self.get_current_state()
            self._ensure_action_exists(current_state, action_id)

            event = SimulationEvent(
                type="student_input",
                state_id=state.current_state_id,
                payload={"action_id": action_id, "response": response},
            )
            self._append_event(event)

            transition = self._find_action_transition(
                current_state,
                action_id=action_id,
                response=response,
                transcript=None,
            )
            self._process_transition(transition, event.payload)
            return self._copy_state()

    def process_audio_input(
        self,
        action_id: str,
        transcript: str,
        confidence: float | None = None,
    ) -> SimulationState:
        with self._lock:
            state = self._require_state()
            current_state = self.get_current_state()
            self._ensure_action_exists(current_state, action_id)

            payload: dict[str, Any] = {
                "action_id": action_id,
                "transcript": transcript,
            }
            if confidence is not None:
                payload["confidence"] = confidence

            event = SimulationEvent(
                type="audio_input",
                state_id=state.current_state_id,
                payload=payload,
            )
            self._append_event(event)

            transition = self._find_action_transition(
                current_state,
                action_id=action_id,
                response=transcript,
                transcript=transcript,
            )
            self._process_transition(transition, event.payload)
            return self._copy_state()

    def process_timer_event(self, timer_id: str) -> SimulationState:
        with self._lock:
            state = self._require_state()
            current_state = self.get_current_state()
            self._ensure_timer_exists(current_state, timer_id)

            event = SimulationEvent(
                type="timer_event",
                state_id=state.current_state_id,
                payload={"timer_id": timer_id},
            )
            self._append_event(event)

            transition = self._find_transition(
                current_state,
                lambda candidate: (
                    candidate.trigger == "timer" and candidate.timer_id == timer_id
                ),
            )
            self._process_transition(transition, event.payload)
            return self._copy_state()

    def process_instructor_event(self, event_name: str) -> SimulationState:
        with self._lock:
            state = self._require_state()
            current_state = self.get_current_state()

            event = SimulationEvent(
                type="instructor_event",
                state_id=state.current_state_id,
                payload={"event": event_name},
            )
            self._append_event(event)

            transition = self._find_transition(
                current_state,
                lambda candidate: (
                    candidate.trigger == "instructor"
                    and candidate.instructor_event == event_name
                ),
            )
            self._process_transition(transition, event.payload)
            return self._copy_state()

    def get_current_state(self) -> State:
        with self._lock:
            state = self._require_state()
            return deepcopy(self._ensure_state_exists(state.current_state_id))

    def get_history(self) -> list[SimulationEvent]:
        with self._lock:
            state = self._require_state()
            return deepcopy(state.event_history)

    def serialize(self) -> dict[str, Any]:
        with self._lock:
            state = self._require_state()
            return state.model_dump(mode="json")

    @classmethod
    def deserialize(
        cls,
        scenario: Scenario,
        data: dict[str, Any] | str,
    ) -> "FSMEngine":
        simulation_state = SimulationState.model_validate_json(data) if isinstance(
            data,
            str,
        ) else SimulationState.model_validate(data)
        return cls(scenario=scenario, simulation_state=simulation_state)

    def _process_transition(
        self,
        transition: Transition | None,
        input_payload: dict[str, Any],
    ) -> None:
        state = self._require_state()

        if transition is None:
            self._append_event(
                SimulationEvent(
                    type="no_transition",
                    state_id=state.current_state_id,
                    payload=input_payload,
                )
            )
            return

        self._ensure_state_exists(transition.target_state)
        previous_state_id = state.current_state_id
        state.current_state_id = transition.target_state
        state.updated_at = datetime.now(timezone.utc)

        self._append_event(
            SimulationEvent(
                type="state_transition",
                state_id=previous_state_id,
                transition_id=transition.id,
                target_state_id=transition.target_state,
                payload={
                    "from_state": previous_state_id,
                    "to_state": transition.target_state,
                    "input": input_payload,
                },
            )
        )

    def _find_action_transition(
        self,
        state: State,
        action_id: str,
        response: str | bool,
        transcript: str | None,
    ) -> Transition | None:
        return self._find_transition(
            state,
            lambda candidate: (
                candidate.trigger == "action"
                and candidate.action_id == action_id
                and self._transition_matches_input(candidate, response, transcript)
            ),
        )

    def _find_transition(
        self,
        state: State,
        predicate: Callable[[Transition], bool],
    ) -> Transition | None:
        for transition in state.transitions:
            if predicate(transition):
                return transition
        return None

    def _transition_matches_input(
        self,
        transition: Transition,
        response: str | bool,
        transcript: str | None,
    ) -> bool:
        has_match_criteria = any(
            [
                transition.expected_response is not None,
                transition.text_match is not None,
                transition.transcript_match is not None,
                transition.conditions,
            ]
        )

        if not has_match_criteria:
            return True

        if transition.expected_response is not None and self._values_match(
            response,
            transition.expected_response,
        ):
            return True

        if transition.text_match is not None and isinstance(response, str):
            return transition.text_match.casefold() in response.casefold()

        if transition.transcript_match is not None and transcript is not None:
            return transition.transcript_match.casefold() in transcript.casefold()

        if transition.conditions:
            return self._conditions_match(transition.conditions, response, transcript)

        return False

    def _conditions_match(
        self,
        conditions: dict[str, Any],
        response: str | bool,
        transcript: str | None,
    ) -> bool:
        values = {
            "response": response,
            "transcript": transcript,
        }

        for key, expected in conditions.items():
            if key not in values:
                return False
            if not self._values_match(values[key], expected):
                return False

        return True

    def _values_match(self, actual: Any, expected: Any) -> bool:
        if isinstance(actual, str) and isinstance(expected, str):
            return actual.casefold() == expected.casefold()
        return actual == expected

    def _append_event(self, event: SimulationEvent) -> None:
        state = self._require_state()
        state.event_history.append(event)
        state.updated_at = event.timestamp

    def _require_state(self) -> SimulationState:
        if self._state is None:
            raise SessionNotStartedError()
        return self._state

    def _copy_state(self) -> SimulationState:
        return deepcopy(self._require_state())

    def _ensure_state_exists(self, state_id: str) -> State:
        state = self._states_by_id.get(state_id)
        if state is None:
            raise StateNotFoundError(state_id)
        return state

    def _ensure_action_exists(self, state: State, action_id: str) -> None:
        if not any(action.id == action_id for action in state.actions):
            raise ActionNotFoundError(state.id, action_id)

    def _ensure_timer_exists(self, state: State, timer_id: str) -> None:
        if not any(timer.id == timer_id for timer in state.timers):
            raise TimerNotFoundError(state.id, timer_id)
