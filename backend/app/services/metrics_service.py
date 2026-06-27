from __future__ import annotations

from app.fsm import SimulationEvent

# All state IDs that represent a completed simulation (terminal states)
COMPLETION_STATE_IDS = {"simulation_complete", "routine_care"}


def compute_session_metrics(
    history: list[SimulationEvent],
    current_state_id: str,
) -> dict:
    """Derive performance metrics from the FSM event history.

    All values are computed in a single pass. Nothing is persisted.
    """
    if not history:
        return {
            "total_duration_seconds": 0.0,
            "student_input_count": 0,
            "voice_input_count": 0,
            "successful_transition_count": 0,
            "no_transition_count": 0,
            "instructor_intervention_count": 0,
            "timer_event_count": 0,
            "completion_status": _completion_status(current_state_id),
        }

    student_inputs = 0
    voice_inputs = 0
    transitions = 0
    no_transitions = 0
    instructor_events = 0
    timer_events = 0

    for event in history:
        t = event.type
        if t == "student_input":
            student_inputs += 1
        elif t == "audio_input":
            voice_inputs += 1
        elif t == "state_transition":
            transitions += 1
        elif t == "no_transition":
            no_transitions += 1
        elif t == "instructor_event":
            instructor_events += 1
        elif t == "timer_event":
            timer_events += 1

    duration = (history[-1].timestamp - history[0].timestamp).total_seconds()

    return {
        "total_duration_seconds": round(duration, 1),
        "student_input_count": student_inputs,
        "voice_input_count": voice_inputs,
        "successful_transition_count": transitions,
        "no_transition_count": no_transitions,
        "instructor_intervention_count": instructor_events,
        "timer_event_count": timer_events,
        "completion_status": _completion_status(current_state_id),
    }


def _completion_status(current_state_id: str) -> str:
    return "complete" if current_state_id in COMPLETION_STATE_IDS else "in_progress"
