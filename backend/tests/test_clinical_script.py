"""
Tests for backend/app/clinical_script.py — the single source of truth.

Contracts enforced:
1. VOICE_PROMPTS and CSV_PROMPTS cover exactly the same state IDs.
2. scenarios/baby_birth.json voice_prompt fields match VOICE_PROMPTS exactly.
3. get_csv_prompt / get_voice_prompt return sensible defaults for unknown IDs.
4. get_timer_alarm_label returns CSV and XLSX labels for all known timer IDs.
5. get_timer_started_label returns a label for all known timer IDs.
6. get_instructor_action_label returns a label for all known instructor events.
7. get_clinical_phase returns a label for all known state IDs.
8. get_transition_outcome returns labels for key states only.
9. get_outcome_label returns correct labels for terminal states.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app import clinical_script as cs

# ── 1. State-ID coverage ──────────────────────────────────────────────────────

def test_voice_and_csv_prompts_same_keys() -> None:
    assert set(cs.VOICE_PROMPTS.keys()) == set(cs.CSV_PROMPTS.keys()), (
        "VOICE_PROMPTS and CSV_PROMPTS must cover the same state IDs"
    )


# ── 2. Scenario JSON voice_prompts match VOICE_PROMPTS ───────────────────────

_SCENARIO_PATH = (
    pathlib.Path(__file__).parent.parent.parent / "scenarios" / "baby_birth.json"
)


def _load_scenario() -> dict:
    with open(_SCENARIO_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_scenario_voice_prompts_match_clinical_script() -> None:
    """Every state with a voice_prompt in baby_birth.json must match VOICE_PROMPTS exactly."""
    scenario = _load_scenario()
    mismatches: list[str] = []
    for state in scenario["states"]:
        state_id = state["id"]
        json_prompt = state.get("metadata", {}).get("voice_prompt")
        if json_prompt is None:
            continue
        expected = cs.VOICE_PROMPTS.get(state_id)
        if expected is None:
            mismatches.append(f"{state_id}: present in JSON but missing from VOICE_PROMPTS")
        elif json_prompt != expected:
            mismatches.append(
                f"{state_id}:\n  JSON:   {json_prompt!r}\n  Script: {expected!r}"
            )
    assert not mismatches, "Scenario JSON voice_prompts diverge from VOICE_PROMPTS:\n" + "\n".join(mismatches)


def test_all_voice_prompts_have_scenario_coverage() -> None:
    """Every state in VOICE_PROMPTS must appear in the scenario JSON."""
    scenario = _load_scenario()
    scenario_ids = {s["id"] for s in scenario["states"]}
    missing = set(cs.VOICE_PROMPTS.keys()) - scenario_ids
    assert not missing, f"States in VOICE_PROMPTS not found in scenario JSON: {missing}"


# ── 3. Default / fallback behaviour ──────────────────────────────────────────

def test_get_voice_prompt_known() -> None:
    assert cs.get_voice_prompt("baby_born") == "Baby is born at {TIME}."


def test_get_voice_prompt_unknown_uses_title_case() -> None:
    result = cs.get_voice_prompt("some_unknown_state")
    assert result == "Some Unknown State"


def test_get_csv_prompt_known() -> None:
    assert cs.get_csv_prompt("baby_born") == "BABY BORN AT"


def test_get_csv_prompt_unknown_uses_uppercase() -> None:
    result = cs.get_csv_prompt("some_unknown_state")
    assert result == "SOME UNKNOWN STATE"


# ── 4. Timer alarm labels ─────────────────────────────────────────────────────

_KNOWN_TIMER_IDS = [
    "birth_timer",
    "ventilation_timer",
    "continue_ventilation_timer",
    "corrective_ventilation_timer",
    "heart_rate_reassessment_timer",
]


@pytest.mark.parametrize("timer_id", _KNOWN_TIMER_IDS)
def test_csv_alarm_label_not_empty(timer_id: str) -> None:
    assert cs.get_timer_alarm_label(timer_id)


@pytest.mark.parametrize("timer_id", _KNOWN_TIMER_IDS)
def test_xlsx_alarm_label_not_empty(timer_id: str) -> None:
    assert cs.get_timer_alarm_label(timer_id, xlsx=True)


def test_csv_alarm_label_birth() -> None:
    assert cs.get_timer_alarm_label("birth_timer") == "BIRTH TIMER ALARM"


def test_xlsx_alarm_label_birth() -> None:
    label = cs.get_timer_alarm_label("birth_timer", xlsx=True)
    assert "Birth Timer" in label


def test_alarm_label_unknown_falls_back() -> None:
    csv_label = cs.get_timer_alarm_label("mystery_timer")
    assert "Alarm" in csv_label or csv_label  # non-empty string


# ── 5. Timer started labels ───────────────────────────────────────────────────

@pytest.mark.parametrize("timer_id", _KNOWN_TIMER_IDS)
def test_timer_started_label_not_empty(timer_id: str) -> None:
    assert cs.get_timer_started_label(timer_id)


def test_timer_started_birth() -> None:
    assert cs.get_timer_started_label("birth_timer") == "BIRTH TIMER STARTED"


# ── 6. Instructor action labels ───────────────────────────────────────────────

_KNOWN_INSTRUCTOR_EVENTS = list(cs.INSTRUCTOR_ACTION_LABELS.keys())


@pytest.mark.parametrize("event_name", _KNOWN_INSTRUCTOR_EVENTS)
def test_instructor_action_label_not_empty(event_name: str) -> None:
    assert cs.get_instructor_action_label(event_name)


def test_instructor_action_unknown_falls_back() -> None:
    result = cs.get_instructor_action_label("some_unknown_event")
    assert result  # non-empty


# ── 7. Clinical phase labels ──────────────────────────────────────────────────

@pytest.mark.parametrize("state_id", list(cs.VOICE_PROMPTS.keys()))
def test_clinical_phase_known(state_id: str) -> None:
    phase = cs.get_clinical_phase(state_id)
    assert phase  # non-empty


def test_clinical_phase_unknown_falls_back() -> None:
    result = cs.get_clinical_phase("totally_unknown_state")
    assert result == "Totally Unknown State"


# ── 8. Transition outcome labels ──────────────────────────────────────────────

def test_transition_outcome_routine_care() -> None:
    assert cs.get_transition_outcome("routine_care") == "ROUTINE CARE"


def test_transition_outcome_simulation_complete() -> None:
    assert cs.get_transition_outcome("simulation_complete") == "STOP RESUSCITATION PROTOCOL"


def test_transition_outcome_non_key_state_is_none() -> None:
    assert cs.get_transition_outcome("baby_born") is None
    assert cs.get_transition_outcome("crying_assessment") is None


# ── 9. Outcome labels ─────────────────────────────────────────────────────────

def test_outcome_label_simulation_complete() -> None:
    assert cs.get_outcome_label("simulation_complete") == "Resuscitation Complete"


def test_outcome_label_routine_care() -> None:
    assert cs.get_outcome_label("routine_care") == "Routine Newborn Care"


def test_outcome_label_in_progress_for_non_terminal() -> None:
    assert cs.get_outcome_label("ventilation_in_progress") == "In Progress"
