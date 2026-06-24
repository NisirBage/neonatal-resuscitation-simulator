from __future__ import annotations

import csv
import io
import json
from typing import Any
from uuid import UUID

from app.fsm import SimulationEvent

CSV_COLUMNS = [
    "timestamp",
    "session_id",
    "event_type",
    "state_id",
    "action_id",
    "response",
    "transition_id",
    "target_state_id",
    "details",
]


def export_session_history_csv(
    session_id: UUID,
    history: list[SimulationEvent],
) -> str:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()

    for event in history:
        writer.writerow(_flatten_event(session_id, event))

    return buffer.getvalue()


def _flatten_event(session_id: UUID, event: SimulationEvent) -> dict[str, str]:
    payload = event.payload or {}
    action_id = ""
    response = ""
    details = ""

    if event.type == "student_input":
        action_id = _stringify(payload.get("action_id"))
        response = _stringify(payload.get("response"))
    elif event.type == "audio_input":
        action_id = _stringify(payload.get("action_id"))
        response = _stringify(payload.get("transcript"))
        details = _serialize_residual_payload(
            payload,
            excluded_keys={"action_id", "transcript"},
        )
    elif event.type == "timer_event":
        action_id = _stringify(payload.get("timer_id"))
    elif event.type == "instructor_event":
        action_id = _stringify(payload.get("event"))
    elif event.type in {"state_transition", "no_transition", "session_started"}:
        details = _serialize_payload(payload)
    else:
        details = _serialize_payload(payload)

    return {
        "timestamp": event.timestamp.isoformat(),
        "session_id": str(session_id),
        "event_type": event.type,
        "state_id": event.state_id,
        "action_id": action_id,
        "response": response,
        "transition_id": event.transition_id or "",
        "target_state_id": event.target_state_id or "",
        "details": details,
    }


def _stringify(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def _serialize_payload(payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def _serialize_residual_payload(
    payload: dict[str, Any],
    excluded_keys: set[str],
) -> str:
    residual = {
        key: value
        for key, value in payload.items()
        if key not in excluded_keys and value is not None
    }
    return _serialize_payload(residual)