"""
Full acceptance test suite for the Neonatal Resuscitation Simulator.
Run against a live backend on port 8765.

Covers:
  AT-01  Student happy path (13 steps)
  AT-02  Instructor override path (fast-forward via instructor events)
  AT-03  Advanced resuscitation path (HR<60, chest compressions, epinephrine)
  AT-04  Timer-driven path (manual timer triggers)
  AT-05  Persistence recovery path (requires manual server restart)
  AT-06  CSV export path
  AT-07  Session lifecycle (start / list / stop / 404)
  AT-08  SCENARIOS_DIR path fix (scenarios endpoint)
  AT-09  Self-loop persistence
  AT-10  describe_breathing text variants

Scenario FSM instructor events (verified from baby_birth.json):
  baby_born              -> start_birth_workflow         -> put_on_mothers_chest
  put_on_mothers_chest   -> advance_to_crying_assessment -> initial_steps
  initial_steps          -> initial_steps_complete       -> crying_assessment
  crying_assessment      -> baby_not_crying              -> apnea_assessment
  apnea_assessment       -> assess_heart_rate            -> heart_rate_assessment
  heart_rate_assessment  -> heart_rate_under_100         -> ventilation_path
  ventilation_path       -> ventilation_started          -> ventilation_started_state
  ventilation_started_state -> pulse_oximeter_applied    -> ventilation_in_progress
  ventilation_in_progress   -> ventilation_timer_complete-> heart_rate_after_ventilation
  heart_rate_after_ventilation -> heart_rate_under_60    -> advanced_resuscitation
  heart_rate_increasing  -> heart_rate_increasing        -> continue_ventilation_15s
  continue_ventilation_15s -> continue_ventilation_complete -> routine_observation
  spo2_assessment        -> spo2_low                     -> advanced_resuscitation
  advanced_resuscitation -> advanced_resuscitation_complete -> simulation_complete

Timer events (fire via POST /sessions/{id}/timer/{timer_id}):
  ventilation_in_progress      -> ventilation_timer         -> heart_rate_after_ventilation
  heart_rate_after_ventilation -> heart_rate_reassessment_timer -> heart_rate_increasing
  continue_ventilation_15s     -> continue_ventilation_timer -> routine_observation
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "http://127.0.0.1:8765"
RESULTS = []


def _call(method, path, body=None):
    data = json.dumps(body).encode() if body else b""
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()), r.status


def get(path):
    return _call("GET", path)


def post(path, body=None):
    return _call("POST", path, body)


def submit(sid, action, response):
    return post(f"/api/sessions/sessions/{sid}/input", {"action_id": action, "response": response})


def instructor(sid, event):
    return post(f"/api/sessions/sessions/{sid}/instructor", {"event_name": event})


def timer(sid, timer_id):
    return post(f"/api/sessions/sessions/{sid}/timer/{timer_id}")


def stop(sid):
    return post(f"/api/sessions/sessions/{sid}/stop")


def record(test_id, name, step, expected, actual, passed, notes=""):
    RESULTS.append({
        "id": test_id,
        "name": name,
        "step": step,
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "notes": notes,
    })
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {step}")
    if not passed:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")


def _fast_forward_to_ventilation_in_progress(sid):
    """Drive a session from baby_born to ventilation_in_progress via instructor events."""
    for event in [
        "start_birth_workflow",       # baby_born -> put_on_mothers_chest
        "advance_to_crying_assessment", # put_on_mothers_chest -> initial_steps
        "initial_steps_complete",     # initial_steps -> crying_assessment
        "baby_not_crying",            # crying_assessment -> apnea_assessment
        "assess_heart_rate",          # apnea_assessment -> heart_rate_assessment
        "heart_rate_under_100",       # heart_rate_assessment -> ventilation_path
        "ventilation_started",        # ventilation_path -> ventilation_started_state
        "pulse_oximeter_applied",     # ventilation_started_state -> ventilation_in_progress
    ]:
        instructor(sid, event)


# ─── AT-01: Student Happy Path ─────────────────────────────────────────────

def test_at01():
    print("\nAT-01: Student Happy Path")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    record("AT-01", "Student Happy Path", "Start session", "baby_born", r["current_state"]["id"],
           r["current_state"]["id"] == "baby_born")

    steps = [
        # (action_id, response, expected_next_state)
        ("confirm_birth",                "yes",        "put_on_mothers_chest"),
        ("placed_on_chest",              "yes",        "initial_steps"),
        ("warm_dry_stimulate",           "yes",        "initial_steps"),     # self-loop
        ("position_airway",              "yes",        "initial_steps"),     # self-loop
        ("clear_airway_if_needed",       "yes",        "crying_assessment"),
        ("is_baby_crying",               "no",         "apnea_assessment"),
        ("is_apneic",                    "yes",        "heart_rate_assessment"),
        ("heart_rate_category",          "under_100",  "ventilation_path"),
        ("start_ventilation",            "yes",        "ventilation_started_state"),
        ("apply_pulse_oximeter",         "yes",        "ventilation_in_progress"),
        ("confirm_effective_ventilation","yes",        "spo2_assessment"),
        ("spo2_category",                "acceptable", "routine_observation"),
        ("continue_observation",         "yes",        "simulation_complete"),
    ]
    for action, response, expected in steps:
        r, _ = submit(sid, action, response)
        got = r["current_state"]["id"]
        record("AT-01", "Student Happy Path", f"{action}={response} -> {expected}",
               expected, got, got == expected)

    stop(sid)
    return sid


# ─── AT-02: Instructor Override Path ──────────────────────────────────────

def test_at02():
    print("\nAT-02: Instructor Override Path")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    record("AT-02", "Instructor Path", "Start session at baby_born",
           "baby_born", r["current_state"]["id"], r["current_state"]["id"] == "baby_born")

    # Instructor events follow the actual FSM transition map
    overrides = [
        ("start_birth_workflow",          "put_on_mothers_chest"),
        ("advance_to_crying_assessment",  "initial_steps"),
        ("initial_steps_complete",        "crying_assessment"),
        ("baby_not_crying",               "apnea_assessment"),
        ("assess_heart_rate",             "heart_rate_assessment"),
        ("heart_rate_under_100",          "ventilation_path"),
        ("ventilation_started",           "ventilation_started_state"),
        ("pulse_oximeter_applied",        "ventilation_in_progress"),
    ]
    for event, expected in overrides:
        r, _ = instructor(sid, event)
        got = r["current_state"]["id"]
        record("AT-02", "Instructor Path", f"instructor({event}) -> {expected}",
               expected, got, got == expected)

    # Verify session list shows this session
    sessions, _ = get("/api/sessions/sessions")
    found = any(s["session_id"] == sid for s in sessions)
    record("AT-02", "Instructor Path", "Session appears in GET /sessions",
           "present", "present" if found else "absent", found)

    stop(sid)


# ─── AT-03: Advanced Resuscitation Path ───────────────────────────────────

def test_at03():
    print("\nAT-03: Advanced Resuscitation Path")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]

    _fast_forward_to_ventilation_in_progress(sid)

    # Use instructor timer complete event to exit ventilation_in_progress
    r, _ = instructor(sid, "ventilation_timer_complete")
    record("AT-03", "Advanced Resuscitation", "ventilation_timer_complete -> heart_rate_after_ventilation",
           "heart_rate_after_ventilation", r["current_state"]["id"],
           r["current_state"]["id"] == "heart_rate_after_ventilation")

    # HR under 60 -> advanced_resuscitation
    r, _ = instructor(sid, "heart_rate_under_60")
    record("AT-03", "Advanced Resuscitation", "heart_rate_under_60 -> advanced_resuscitation",
           "advanced_resuscitation", r["current_state"]["id"],
           r["current_state"]["id"] == "advanced_resuscitation")

    # Self-loop: hold_advanced_resuscitation
    r, _ = instructor(sid, "hold_advanced_resuscitation")
    got = r["current_state"]["id"]
    record("AT-03", "Advanced Resuscitation", "hold_advanced_resuscitation self-loop stays in advanced_resuscitation",
           "advanced_resuscitation", got, got == "advanced_resuscitation")

    # Student self-loop actions in advanced_resuscitation
    for action, label in [
        ("start_chest_compressions", "chest compressions self-loop"),
        ("prepare_epinephrine",      "epinephrine self-loop"),
    ]:
        r, _ = submit(sid, action, "yes")
        got = r["current_state"]["id"]
        record("AT-03", "Advanced Resuscitation", f"{label} stays in advanced_resuscitation",
               "advanced_resuscitation", got, got == "advanced_resuscitation")

    # Instructor exit to simulation_complete
    r, _ = instructor(sid, "advanced_resuscitation_complete")
    got = r["current_state"]["id"]
    record("AT-03", "Advanced Resuscitation", "advanced_resuscitation_complete -> simulation_complete",
           "simulation_complete", got, got == "simulation_complete")

    stop(sid)


# ─── AT-04: Timer-Driven Path ──────────────────────────────────────────────

def test_at04():
    print("\nAT-04: Timer-Driven Path")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]

    _fast_forward_to_ventilation_in_progress(sid)

    # Manual timer trigger: ventilation_timer in ventilation_in_progress
    r, _ = timer(sid, "ventilation_timer")
    got = r["current_state"]["id"]
    record("AT-04", "Timer Path", "POST /timer/ventilation_timer -> heart_rate_after_ventilation",
           "heart_rate_after_ventilation", got, got == "heart_rate_after_ventilation")

    # Heart rate reassessment timer: heart_rate_after_ventilation -> heart_rate_increasing
    r, _ = timer(sid, "heart_rate_reassessment_timer")
    got = r["current_state"]["id"]
    record("AT-04", "Timer Path", "heart_rate_reassessment_timer -> heart_rate_increasing",
           "heart_rate_increasing", got, got == "heart_rate_increasing")

    # Advance to continue_ventilation_15s via instructor event
    r, _ = instructor(sid, "heart_rate_increasing")
    record("AT-04", "Timer Path", "heart_rate_increasing -> continue_ventilation_15s",
           "continue_ventilation_15s", r["current_state"]["id"],
           r["current_state"]["id"] == "continue_ventilation_15s")

    # Continue ventilation timer
    r, _ = timer(sid, "continue_ventilation_timer")
    got = r["current_state"]["id"]
    record("AT-04", "Timer Path", "continue_ventilation_timer -> routine_observation",
           "routine_observation", got, got == "routine_observation")

    stop(sid)


# ─── AT-06: CSV Export Path ────────────────────────────────────────────────

def test_at06():
    print("\nAT-06: CSV Export Path")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    submit(sid, "confirm_birth", "yes")
    submit(sid, "placed_on_chest", "yes")

    req = urllib.request.Request(BASE + f"/api/sessions/sessions/{sid}/export/csv")
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        ct = resp.headers.get("Content-Type", "")
        cd = resp.headers.get("Content-Disposition", "")

    record("AT-06", "CSV Export", "Content-Type contains text/csv",
           "text/csv", ct, "text/csv" in ct)
    record("AT-06", "CSV Export", "Content-Disposition contains filename",
           "filename present", cd, "filename" in cd)

    csv_text = raw.decode("utf-8-sig")
    rows = [row for row in csv_text.splitlines() if row.strip()]
    record("AT-06", "CSV Export", "CSV has header row starting with 'timestamp'",
           "header present", rows[0][:9], rows[0].startswith("timestamp"))

    expected_cols = {"timestamp", "session_id", "event_type", "state_id",
                     "action_id", "response", "transition_id", "target_state_id", "details"}
    actual_cols = set(rows[0].split(","))
    missing = expected_cols - actual_cols
    record("AT-06", "CSV Export", "All 9 columns present",
           "none missing", f"missing={missing}" if missing else "none missing", not missing)

    record("AT-06", "CSV Export", "Data rows present (session_started + 2 inputs + transitions)",
           ">=5 rows", f"{len(rows)} rows", len(rows) >= 5)

    record("AT-06", "CSV Export", "UTF-8 BOM present in raw bytes (Excel compat)",
           "BOM present", "BOM present" if raw[:3] == b'\xef\xbb\xbf' else "BOM absent",
           raw[:3] == b'\xef\xbb\xbf')

    stop(sid)


# ─── AT-07: Session Lifecycle ──────────────────────────────────────────────

def test_at07():
    print("\nAT-07: Session Lifecycle")
    r, status = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    record("AT-07", "Session Lifecycle", "POST /start returns session_id",
           "session_id present", "present" if sid else "absent", bool(sid))

    sessions, _ = get("/api/sessions/sessions")
    found = any(s["session_id"] == sid for s in sessions)
    record("AT-07", "Session Lifecycle", "Session appears in GET /sessions list",
           "found", "found" if found else "not found", found)

    detail, _ = get(f"/api/sessions/sessions/{sid}")
    record("AT-07", "Session Lifecycle", "GET /sessions/{id} returns session with history field",
           "has history field", "has history" if "history" in detail else "missing",
           "history" in detail)

    stop(sid)
    try:
        get(f"/api/sessions/sessions/{sid}")
        record("AT-07", "Session Lifecycle", "GET stopped session returns 404",
               "404", "200", False)
    except urllib.error.HTTPError as e:
        record("AT-07", "Session Lifecycle", "GET stopped session returns 404",
               "404", str(e.code), e.code == 404)


# ─── AT-08: SCENARIOS_DIR Path Fix ────────────────────────────────────────

def test_at08():
    print("\nAT-08: SCENARIOS_DIR Path Fix")
    scenarios, _ = get("/api/scenarios/scenarios")
    found_baby = any(s["id"] == "baby_birth" for s in scenarios)
    record("AT-08", "SCENARIOS_DIR Fix", "GET /scenarios returns baby_birth",
           "baby_birth present", "present" if found_baby else "absent", found_baby)
    record("AT-08", "SCENARIOS_DIR Fix", "Scenario count >= 1",
           ">=1", f"{len(scenarios)} found", len(scenarios) >= 1)

    detail, _ = get("/api/scenarios/scenarios/baby_birth")
    state_count = detail.get("state_count")
    record("AT-08", "SCENARIOS_DIR Fix", "GET /scenarios/baby_birth returns state_count=17",
           "17", str(state_count), state_count == 17)


# ─── AT-09: Self-Loop Persistence ─────────────────────────────────────────

def test_at09():
    print("\nAT-09: Self-Loop Persistence")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    submit(sid, "confirm_birth", "yes")
    submit(sid, "placed_on_chest", "yes")

    # warm_dry_stimulate self-loop: stays in initial_steps
    r, _ = submit(sid, "warm_dry_stimulate", "yes")
    record("AT-09", "Self-Loop", "warm_dry_stimulate stays in initial_steps",
           "initial_steps", r["current_state"]["id"], r["current_state"]["id"] == "initial_steps")

    # Verify transition appears in event history
    detail, _ = get(f"/api/sessions/sessions/{sid}")
    history = detail.get("history", [])
    has_selfloop = any(
        e.get("type") == "state_transition" and e.get("transition_id") == "warm_dry_stimulate_done"
        for e in history
    )
    record("AT-09", "Self-Loop", "warm_dry_stimulate_done transition in event history",
           "present", "present" if has_selfloop else "absent", has_selfloop)

    # Verify event count increased (self-loop was recorded)
    initial_count = len(history)
    submit(sid, "position_airway", "yes")
    detail2, _ = get(f"/api/sessions/sessions/{sid}")
    new_count = len(detail2.get("history", []))
    record("AT-09", "Self-Loop", "History grows on each self-loop",
           f">{initial_count}", f"{new_count}", new_count > initial_count)

    # Invalid input: no_transition, state unchanged
    r, _ = submit(sid, "position_airway", "wrong_answer_xyz")
    record("AT-09", "Self-Loop", "Invalid input stays in same state (no_transition)",
           "initial_steps", r["current_state"]["id"], r["current_state"]["id"] == "initial_steps")

    stop(sid)


# ─── AT-10: Text Variants ──────────────────────────────────────────────────

def test_at10():
    print("\nAT-10: describe_breathing Text Variants")

    def advance_to_apnea(s):
        for action, response in [
            ("confirm_birth", "yes"), ("placed_on_chest", "yes"),
            ("warm_dry_stimulate", "yes"), ("position_airway", "yes"),
            ("clear_airway_if_needed", "yes"), ("is_baby_crying", "no"),
        ]:
            submit(s, action, response)

    for word in ("apnea", "gasping", "breathing"):
        r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
        s = r["session_id"]
        advance_to_apnea(s)
        r, _ = submit(s, "describe_breathing", word)
        got = r["current_state"]["id"]
        record("AT-10", "Text Variants", f"describe_breathing '{word}' -> heart_rate_assessment",
               "heart_rate_assessment", got, got == "heart_rate_assessment")
        stop(s)


# ─── AT-05: Persistence Recovery (manual) ─────────────────────────────────

def test_at05_instructions():
    print("\nAT-05: Persistence Recovery Path")
    print("  [SKIP] Requires manual server restart.")
    print("         Run terminals/regression_persistence.py interactively.")
    RESULTS.append({
        "id": "AT-05",
        "name": "Persistence Recovery",
        "step": "Session restored after server restart with correct state and history",
        "expected": "Session restored, state preserved, history intact, timers recreated",
        "actual": "SKIPPED - requires manual server restart cycle",
        "passed": None,
        "notes": "Covered by regression_persistence.py. Pass confirmed in prior session.",
    })


# ─── Entry Point ───────────────────────────────────────────────────────────

def run_all():
    print(f"Acceptance Test Suite -- {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"Backend: {BASE}")
    print("=" * 60)

    test_at01()
    test_at02()
    test_at03()
    test_at04()
    test_at05_instructions()
    test_at06()
    test_at07()
    test_at08()
    test_at09()
    test_at10()

    print("\n" + "=" * 60)
    passed = sum(1 for r in RESULTS if r["passed"] is True)
    failed = sum(1 for r in RESULTS if r["passed"] is False)
    skipped = sum(1 for r in RESULTS if r["passed"] is None)
    total = passed + failed + skipped

    print(f"PASSED:  {passed}")
    print(f"FAILED:  {failed}")
    print(f"SKIPPED: {skipped}")
    print(f"TOTAL:   {total}")
    print()
    print("RESULT:", "PASSED" if failed == 0 else "FAILED")

    return RESULTS, passed, failed, skipped


if __name__ == "__main__":
    results, passed, failed, skipped = run_all()
    sys.exit(0 if failed == 0 else 1)
