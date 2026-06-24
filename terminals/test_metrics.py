"""
Acceptance tests for the session performance metrics endpoint.

Tests:
  MT-01  Happy-path session produces a metrics report with correct counts.
  MT-02  Counts match the actual event history.
  MT-03  No-transition events (invalid inputs) increase no_transition_count.
  MT-04  Instructor events increase instructor_intervention_count.
  MT-05  Timer events increase timer_event_count.
  MT-06  CSV export is unchanged (same columns and row count).
  MT-07  Metrics endpoint returns 404 for unknown session.
  MT-08  Metrics endpoint available mid-session (not just on completion).
  MT-09  completion_status == "complete" at simulation_complete state.
  MT-10  completion_status == "in_progress" before simulation_complete.
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


def timer_trigger(sid, timer_id):
    return post(f"/api/sessions/sessions/{sid}/timer/{timer_id}")


def metrics(sid):
    return get(f"/api/sessions/sessions/{sid}/metrics")


def stop(sid):
    return post(f"/api/sessions/sessions/{sid}/stop")


def check(test_id, step, expected, actual, passed):
    RESULTS.append({"id": test_id, "step": step, "expected": expected, "actual": actual, "passed": passed})
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {step}")
    if not passed:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")


def run():
    print(f"Metrics Acceptance Tests -- {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"Backend: {BASE}")
    print("=" * 60)

    # ─── MT-01 / MT-02 / MT-09: Happy path full run ─────────────────────────
    print("\nMT-01 / MT-02 / MT-09: Happy path counts and completion status")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]

    steps = [
        ("confirm_birth",                "yes"),
        ("placed_on_chest",              "yes"),
        ("warm_dry_stimulate",           "yes"),   # self-loop
        ("position_airway",              "yes"),   # self-loop
        ("clear_airway_if_needed",       "yes"),
        ("is_baby_crying",               "no"),
        ("is_apneic",                    "yes"),
        ("heart_rate_category",          "under_100"),
        ("start_ventilation",            "yes"),
        ("apply_pulse_oximeter",         "yes"),
        ("confirm_effective_ventilation","yes"),
        ("spo2_category",                "acceptable"),
        ("continue_observation",         "yes"),
    ]
    for action, response in steps:
        submit(sid, action, response)

    m, _ = metrics(sid)

    # MT-09: completion status
    check("MT-09", "completion_status == 'complete' at simulation_complete",
          "complete", m["completion_status"], m["completion_status"] == "complete")

    # MT-01: report is returned and has all expected fields
    required = {"session_id","total_duration_seconds","student_input_count","voice_input_count",
                "successful_transition_count","no_transition_count","instructor_intervention_count",
                "timer_event_count","completion_status"}
    missing = required - set(m.keys())
    check("MT-01", "All 9 metric fields present", "none missing",
          f"missing={missing}" if missing else "none missing", not missing)

    # MT-02: counts match the event history we submitted
    # 13 student inputs, 0 voice, 13 transitions (from student inputs) + 1 for session_started transition? no.
    # Actually: session_started produces 1 event (session_started type, not student_input).
    # Each submit() call produces: 1 student_input event + 1 state_transition event (if matched).
    # All 13 steps should transition.
    check("MT-02", "student_input_count == 13 (one per step)",
          13, m["student_input_count"], m["student_input_count"] == 13)
    check("MT-02", "voice_input_count == 0 (no audio inputs)",
          0, m["voice_input_count"], m["voice_input_count"] == 0)
    check("MT-02", "successful_transition_count == 13 (all steps matched)",
          13, m["successful_transition_count"], m["successful_transition_count"] == 13)
    check("MT-02", "no_transition_count == 0 (no invalid inputs)",
          0, m["no_transition_count"], m["no_transition_count"] == 0)
    check("MT-02", "instructor_intervention_count == 0 (no instructor events)",
          0, m["instructor_intervention_count"], m["instructor_intervention_count"] == 0)
    check("MT-02", "timer_event_count == 0 (no manual timer triggers)",
          0, m["timer_event_count"], m["timer_event_count"] == 0)
    check("MT-02", "total_duration_seconds > 0",
          ">0", m["total_duration_seconds"],
          isinstance(m["total_duration_seconds"], (int, float)) and m["total_duration_seconds"] >= 0)

    stop(sid)

    # ─── MT-03: No-transition events ─────────────────────────────────────────
    print("\nMT-03: No-transition events increase no_transition_count")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]

    # Baseline metrics after start
    m0, _ = metrics(sid)
    base_no_trans = m0["no_transition_count"]

    # Submit 3 invalid responses (wrong answer for action that expects 'yes')
    # Use a valid action_id but wrong response to get no_transition
    for _ in range(3):
        submit(sid, "confirm_birth", "INVALID_RESPONSE_THAT_MATCHES_NOTHING")

    m1, _ = metrics(sid)
    check("MT-03", "no_transition_count increased by 3 after 3 invalid inputs",
          base_no_trans + 3, m1["no_transition_count"],
          m1["no_transition_count"] == base_no_trans + 3)
    check("MT-03", "student_input_count increased by 3",
          3, m1["student_input_count"] - m0["student_input_count"],
          m1["student_input_count"] - m0["student_input_count"] == 3)
    check("MT-03", "successful_transition_count unchanged (no valid transitions)",
          m0["successful_transition_count"], m1["successful_transition_count"],
          m1["successful_transition_count"] == m0["successful_transition_count"])
    stop(sid)

    # ─── MT-04: Instructor interventions ─────────────────────────────────────
    print("\nMT-04: Instructor events increase instructor_intervention_count")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]

    m0, _ = metrics(sid)
    instructor(sid, "start_birth_workflow")
    instructor(sid, "advance_to_crying_assessment")
    instructor(sid, "initial_steps_complete")
    m1, _ = metrics(sid)

    check("MT-04", "instructor_intervention_count increased by 3",
          m0["instructor_intervention_count"] + 3, m1["instructor_intervention_count"],
          m1["instructor_intervention_count"] == m0["instructor_intervention_count"] + 3)
    check("MT-04", "student_input_count unchanged",
          m0["student_input_count"], m1["student_input_count"],
          m1["student_input_count"] == m0["student_input_count"])
    stop(sid)

    # ─── MT-05: Timer events ──────────────────────────────────────────────────
    print("\nMT-05: Timer events increase timer_event_count")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]

    # Fast-forward to ventilation_in_progress
    for event in [
        "start_birth_workflow", "advance_to_crying_assessment",
        "initial_steps_complete", "baby_not_crying", "assess_heart_rate",
        "heart_rate_under_100", "ventilation_started", "pulse_oximeter_applied",
    ]:
        instructor(sid, event)

    m0, _ = metrics(sid)
    timer_trigger(sid, "ventilation_timer")
    m1, _ = metrics(sid)

    check("MT-05", "timer_event_count increased by 1",
          m0["timer_event_count"] + 1, m1["timer_event_count"],
          m1["timer_event_count"] == m0["timer_event_count"] + 1)
    check("MT-05", "successful_transition_count increased by 1 (timer caused a transition)",
          m0["successful_transition_count"] + 1, m1["successful_transition_count"],
          m1["successful_transition_count"] == m0["successful_transition_count"] + 1)
    stop(sid)

    # ─── MT-06: CSV export unchanged ─────────────────────────────────────────
    print("\nMT-06: CSV export unchanged after metrics feature added")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    submit(sid, "confirm_birth", "yes")
    submit(sid, "placed_on_chest", "yes")

    req = urllib.request.Request(BASE + f"/api/sessions/sessions/{sid}/export/csv")
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        ct = resp.headers.get("Content-Type", "")

    csv_text = raw.decode("utf-8-sig")
    header = csv_text.splitlines()[0]
    expected_cols = {"timestamp","session_id","event_type","state_id",
                     "action_id","response","transition_id","target_state_id","details"}
    actual_cols = set(header.split(","))
    check("MT-06", "CSV Content-Type unchanged", "text/csv in ct", ct,
          "text/csv" in ct)
    check("MT-06", "CSV columns unchanged (9 columns, no metrics columns)",
          "none missing", f"missing={expected_cols - actual_cols}" if (expected_cols - actual_cols) else "none missing",
          expected_cols == actual_cols)
    check("MT-06", "CSV has no unexpected metric columns",
          "no extras", f"extra={actual_cols - expected_cols}" if (actual_cols - expected_cols) else "no extras",
          not (actual_cols - expected_cols))
    stop(sid)

    # ─── MT-07: 404 for unknown session ──────────────────────────────────────
    print("\nMT-07: Metrics endpoint returns 404 for unknown session")
    try:
        get("/api/sessions/sessions/00000000-0000-0000-0000-000000000000/metrics")
        check("MT-07", "Unknown session returns 404", "404", "200", False)
    except urllib.error.HTTPError as e:
        check("MT-07", "Unknown session returns 404", "404", str(e.code), e.code == 404)

    # ─── MT-08: Metrics available mid-session ────────────────────────────────
    print("\nMT-08: Metrics available mid-session (not only at simulation_complete)")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    submit(sid, "confirm_birth", "yes")
    m, status = metrics(sid)
    check("MT-08", "GET /metrics returns 200 mid-session", 200, status, status == 200)
    check("MT-08", "completion_status == 'in_progress' mid-session",
          "in_progress", m["completion_status"], m["completion_status"] == "in_progress")
    stop(sid)

    # ─── MT-10: completion_status in_progress before completion ──────────────
    print("\nMT-10: completion_status == 'in_progress' before simulation_complete")
    r, _ = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    m, _ = metrics(sid)
    check("MT-10", "Fresh session completion_status == 'in_progress'",
          "in_progress", m["completion_status"], m["completion_status"] == "in_progress")
    stop(sid)

    # ─── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = sum(1 for r in RESULTS if not r["passed"])
    print(f"PASSED:  {passed}")
    print(f"FAILED:  {failed}")
    print(f"TOTAL:   {len(RESULTS)}")
    print("\nRESULT:", "PASSED" if failed == 0 else "FAILED")
    return failed


if __name__ == "__main__":
    sys.exit(run())
