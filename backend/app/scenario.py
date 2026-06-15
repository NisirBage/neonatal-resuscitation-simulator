import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ActionType = Literal["yes_no", "text", "audio", "instructor"]
TransitionTrigger = Literal["action", "timer", "instructor"]


class Action(BaseModel):
    id: str
    type: ActionType
    prompt: str | None = None
    options: list[str] = Field(default_factory=list)
    transcript_required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action(self) -> "Action":
        if self.type == "yes_no" and set(self.options) != {"yes", "no"}:
            raise ValueError("yes_no actions must define exactly yes and no options")

        if self.type == "audio" and not self.transcript_required:
            raise ValueError("audio actions must require transcription")

        return self


class Timer(BaseModel):
    id: str
    duration_seconds: int = Field(gt=0)
    event: str
    auto_start: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Transition(BaseModel):
    id: str
    trigger: TransitionTrigger
    target_state: str
    action_id: str | None = None
    timer_id: str | None = None
    instructor_event: str | None = None
    expected_response: str | bool | None = None
    text_match: str | None = None
    transcript_match: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_trigger_configuration(self) -> "Transition":
        if self.trigger == "action" and self.action_id is None:
            raise ValueError("action transitions must define action_id")

        if self.trigger == "timer" and self.timer_id is None:
            raise ValueError("timer transitions must define timer_id")

        if self.trigger == "instructor" and self.instructor_event is None:
            raise ValueError("instructor transitions must define instructor_event")

        return self


class State(BaseModel):
    id: str
    name: str
    description: str | None = None
    actions: list[Action] = Field(default_factory=list)
    timers: list[Timer] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Scenario(BaseModel):
    id: str
    name: str
    version: str
    initial_state: str
    states: list[State]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scenario_graph(self) -> "Scenario":
        validate_scenario(self)
        return self


def load_scenario(path: str) -> Scenario:
    scenario_path = Path(path)
    with scenario_path.open(encoding="utf-8") as scenario_file:
        scenario_data = json.load(scenario_file)

    return Scenario.model_validate(scenario_data)


def validate_scenario(scenario: Scenario) -> Scenario:
    state_ids = [state.id for state in scenario.states]
    unique_state_ids = set(state_ids)

    if len(unique_state_ids) != len(state_ids):
        raise ValueError("scenario states must have unique ids")

    if scenario.initial_state not in unique_state_ids:
        raise ValueError("initial_state must reference an existing state")

    for state in scenario.states:
        action_ids = [action.id for action in state.actions]
        timer_ids = [timer.id for timer in state.timers]
        transition_ids = [transition.id for transition in state.transitions]

        if len(set(action_ids)) != len(action_ids):
            raise ValueError(f"state '{state.id}' actions must have unique ids")

        if len(set(timer_ids)) != len(timer_ids):
            raise ValueError(f"state '{state.id}' timers must have unique ids")

        if len(set(transition_ids)) != len(transition_ids):
            raise ValueError(f"state '{state.id}' transitions must have unique ids")

        for transition in state.transitions:
            if transition.target_state not in unique_state_ids:
                raise ValueError(
                    f"transition '{transition.id}' targets unknown state "
                    f"'{transition.target_state}'"
                )

            if transition.action_id is not None and transition.action_id not in action_ids:
                raise ValueError(
                    f"transition '{transition.id}' references unknown action "
                    f"'{transition.action_id}' in state '{state.id}'"
                )

            if transition.timer_id is not None and transition.timer_id not in timer_ids:
                raise ValueError(
                    f"transition '{transition.id}' references unknown timer "
                    f"'{transition.timer_id}' in state '{state.id}'"
                )

    return scenario
