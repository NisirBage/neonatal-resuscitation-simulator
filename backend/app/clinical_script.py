"""
clinical_script.py — Single source of truth for all user-facing clinical phrases.

RULE: if you need to change a clinical phrase, change it HERE ONLY.
Never duplicate these strings in scenario JSON, CSV generators, report services,
or any other module.  Every consumer imports from this file.

Consumers:
  - Text-to-Speech / UI cards  → VOICE_PROMPTS (via scenario JSON kept in sync)
  - Clinical CSV               → CSV_PROMPTS, TIMER_ALARM_CSV_LABELS, ...
  - Clinical XLSX              → CSV_PROMPTS, TIMER_ALARM_XLSX_LABELS, ...
  - PDF reports                → get_outcome_label, get_clinical_phase
"""
from __future__ import annotations

# ── Voice prompts ─────────────────────────────────────────────────────────────
# Sentence-case professor wording for TTS and UI instruction cards.
# {TIME} is replaced by the frontend at speech time (browser local clock).
#
# IMPORTANT: the voice_prompt field in scenarios/baby_birth.json MUST match
# these values exactly.  test_clinical_script.py enforces this contract.

VOICE_PROMPTS: dict[str, str] = {
    "baby_born":                    "Baby is born at {TIME}.",
    "put_on_mothers_chest":         "Put baby on mother's abdomen.",
    "crying_assessment":            "Is baby crying?",
    "apnea_assessment":             "Does baby have apnea?",
    "heart_rate_assessment":        "Measure heart rate. Is the heart rate greater than 100 beats per minute?",
    "routine_care":                 "Baby is crying and vigorous. Perform routine care.",
    "ventilation_path":             "Start ventilation and apply pulse oximeter.",
    "ventilation_in_progress":      "Measure heart rate every 15 seconds.",
    "heart_rate_after_ventilation": "Is the heart rate increasing?",
    "ventilation_corrective_steps": "Follow ventilation corrective steps.",
    "continue_ventilation_15s":     "Heart rate is increasing. Continue ventilation for 15 seconds and stop.",
    "simulation_complete":          "Heart rate is greater than 100 beats per minute. Stop resuscitation protocol.",
}

# ── CSV / XLSX prompts ────────────────────────────────────────────────────────
# Uppercase short-form phrases for the Voice Prompt column in clinical exports.
# Wall-clock time sits in the Time column, so {TIME} is omitted here.

CSV_PROMPTS: dict[str, str] = {
    "baby_born":                    "BABY BORN AT",
    "put_on_mothers_chest":         "PUT BABY ON MOTHERS ABDOMEN",
    "crying_assessment":            "IS BABY CRYING",
    "apnea_assessment":             "DOES BABY HAVE APNEA",
    "heart_rate_assessment":        "MEASURE HEART RATE. IS HR GREATER THAN 100 BPM",
    "routine_care":                 "PERFORM ROUTINE CARE",
    "ventilation_path":             "START VENTILATION AND APPLY PULSE OXIMETER",
    "ventilation_in_progress":      "MEASURE HEART RATE EVERY 15 SECONDS",
    "heart_rate_after_ventilation": "IS THE HEART RATE INCREASING",
    "ventilation_corrective_steps": "FOLLOW VENTILATION CORRECTIVE STEPS",
    "continue_ventilation_15s":     "CONTINUE VENTILATION FOR 15 SECONDS AND STOP",
    "simulation_complete":          "STOP RESUSCITATION PROTOCOL",
}

# ── Clinical phase labels ─────────────────────────────────────────────────────
# Human-readable phase name for the Clinical Phase column in XLSX.

CLINICAL_PHASES: dict[str, str] = {
    "baby_born":                    "Birth",
    "put_on_mothers_chest":         "Initial Assessment",
    "crying_assessment":            "Respiratory Assessment",
    "apnea_assessment":             "Respiratory Assessment",
    "heart_rate_assessment":        "Heart Rate Assessment",
    "ventilation_path":             "Ventilation",
    "ventilation_in_progress":      "Ventilation",
    "heart_rate_after_ventilation": "Ventilation Reassessment",
    "ventilation_corrective_steps": "Corrective Ventilation",
    "continue_ventilation_15s":     "Ventilation Reassessment",
    "routine_care":                 "Routine Care",
    "simulation_complete":          "Simulation Complete",
}

# ── Timer alarm labels ────────────────────────────────────────────────────────
# Appear in the System Action column when a timer expires.

TIMER_ALARM_CSV_LABELS: dict[str, str] = {
    "birth_timer":                   "BIRTH TIMER ALARM",
    "baby_born_delay_timer":         "BIRTH ANNOUNCEMENT COMPLETE",
    "ventilation_timer":             "VENTILATION TIMER ALARM",
    "continue_ventilation_timer":    "CONTINUE VENTILATION COMPLETE",
    "corrective_ventilation_timer":  "CORRECTIVE VENTILATION TIMER ALARM",
    "heart_rate_reassessment_timer": "HEART RATE REASSESSMENT COMPLETE",
}

# Verbose alarm labels for the XLSX instructor report.
TIMER_ALARM_XLSX_LABELS: dict[str, str] = {
    "birth_timer":                   "Birth Timer Reminder (1 minute)",
    "ventilation_timer":             "Ventilation Timer Reminder (30 seconds)",
    "continue_ventilation_timer":    "15 Second Heart Rate Reminder",
    "corrective_ventilation_timer":  "Corrective Ventilation Reminder (30 seconds)",
    "heart_rate_reassessment_timer": "Heart Rate Reassessment Reminder",
}

# ── Timer started labels ──────────────────────────────────────────────────────
# Appear in System Action when an auto-start timer begins.

TIMER_STARTED_LABELS: dict[str, str] = {
    "birth_timer":                   "BIRTH TIMER STARTED",
    "baby_born_delay_timer":         "",  # internal 15-second delay, not shown in timeline
    "ventilation_timer":             "VENTILATION TIMER 30 SEC",
    "continue_ventilation_timer":    "CONTINUE VENTILATION TIMER STARTED",
    "corrective_ventilation_timer":  "CORRECTIVE VENTILATION TIMER 30 SEC",
    "heart_rate_reassessment_timer": "HEART RATE REASSESSMENT TIMER STARTED",
}

# ── Transition outcome labels ─────────────────────────────────────────────────
# System Action appended when the FSM transitions INTO these target states.

TRANSITION_OUTCOME_LABELS: dict[str, str] = {
    "routine_care":             "ROUTINE CARE",
    "simulation_complete":      "STOP RESUSCITATION PROTOCOL",
    "ventilation_path":         "START VENTILATION",
    "ventilation_in_progress":  "VENTILATION STARTED",
    "continue_ventilation_15s": "CONTINUE VT FOR 15 SEC",
}

# ── Instructor action labels ──────────────────────────────────────────────────
# Human-readable replacements for raw instructor event names.

INSTRUCTOR_ACTION_LABELS: dict[str, str] = {
    "start_birth_workflow":            "Instructor advanced simulation",
    "advance_to_crying_assessment":    "Instructor advanced simulation",
    "baby_not_crying":                 "Instructor forced transition",
    "assess_heart_rate":               "Instructor advanced simulation",
    "heart_rate_100_or_more":          "Instructor forced transition",
    "heart_rate_under_100":            "Instructor forced transition",
    "ventilation_started":             "Instructor advanced simulation",
    "ventilation_timer_complete":      "Instructor skipped timer",
    "heart_rate_increasing":           "Instructor forced transition",
    "heart_rate_not_increasing":       "Instructor forced transition",
    "continue_ventilation_complete":   "Instructor skipped timer",
    "corrective_ventilation_complete": "Instructor advanced simulation",
}

# ── Outcome labels ────────────────────────────────────────────────────────────
# Used in XLSX summary and PDF status field.

OUTCOME_LABELS: dict[str, str] = {
    "simulation_complete": "Resuscitation Complete",
    "routine_care":        "Routine Newborn Care",
}


# ── Helper functions ──────────────────────────────────────────────────────────

def _snake_to_title(snake: str) -> str:
    return " ".join(word.capitalize() for word in snake.split("_"))


def get_voice_prompt(state_id: str) -> str:
    """Sentence-case clinical phrase for TTS / UI (may contain {TIME} placeholder)."""
    return VOICE_PROMPTS.get(state_id, _snake_to_title(state_id))


def get_csv_prompt(state_id: str) -> str:
    """Uppercase clinical phrase for the Voice Prompt column in CSV / XLSX exports."""
    return CSV_PROMPTS.get(state_id, state_id.upper().replace("_", " "))


def get_clinical_phase(state_id: str) -> str:
    """Human-readable clinical phase name for a state ID."""
    return CLINICAL_PHASES.get(state_id, _snake_to_title(state_id))


def get_timer_alarm_label(timer_id: str, *, xlsx: bool = False) -> str:
    """Alarm label for a given timer ID.  Pass xlsx=True for the verbose XLSX form."""
    if xlsx:
        return TIMER_ALARM_XLSX_LABELS.get(timer_id, _snake_to_title(timer_id) + " Reminder")
    return TIMER_ALARM_CSV_LABELS.get(timer_id, _snake_to_title(timer_id) + " Alarm")


def get_timer_started_label(timer_id: str) -> str:
    """'X Timer Started' label for a given timer ID."""
    return TIMER_STARTED_LABELS.get(timer_id, _snake_to_title(timer_id) + " Started")


def get_instructor_action_label(event_name: str) -> str:
    """Human-readable label for a raw instructor event name."""
    return INSTRUCTOR_ACTION_LABELS.get(event_name, _snake_to_title(event_name))


def get_outcome_label(state_id: str) -> str:
    """Clinical outcome label for terminal state IDs."""
    return OUTCOME_LABELS.get(state_id, "In Progress")


def get_transition_outcome(target_state_id: str) -> str | None:
    """System Action label appended when FSM transitions into a key target state."""
    return TRANSITION_OUTCOME_LABELS.get(target_state_id)
