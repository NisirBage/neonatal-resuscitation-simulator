"""
Regression test covering:
  1. Student happy path unchanged (13 steps)
  2. GET /api/sessions/sessions returns correct structure
  3. POST /instructor fires transition and returns new state
  4. POST /timer/{id} fires timer event
  5. GET /export/csv returns data after instructor interaction
  6. Instructor can stop session
"""
import urllib.request
import urllib.error
import json
import sys

BASE = "http://127.0.0.1:8765"

def _call(method, path, body=None):
    data = json.dumps(body).encode() if body else b""
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}, method=method
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def get(path): return _call("GET", path)
def post(path, body=None): return _call("POST", path, body)
def submit(sid, action, response): return post(f"/api/sessions/sessions/{sid}/input", {"action_id": action, "response": response})
def instructor(sid, event): return post(f"/api/sessions/sessions/{sid}/instructor", {"event_name": event})
def stop(sid): return post(f"/api/sessions/sessions/{sid}/stop")

failures = []

# ──────────────────────────────────────────────────────────────────────────────
# TEST 1: Student happy path (all 13 steps must be unchanged)
# ──────────────────────────────────────────────────────────────────────────────
r = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
sid = r["session_id"]
assert r["current_state"]["id"] == "baby_born"

steps = [
    ("confirm_birth",               "yes",        "put_on_mothers_chest"),
    ("placed_on_chest",             "yes",        "initial_steps"),
    ("warm_dry_stimulate",          "yes",        "initial_steps"),
    ("position_airway",             "yes",        "initial_steps"),
    ("clear_airway_if_needed",      "yes",        "crying_assessment"),
    ("is_baby_crying",              "no",         "apnea_assessment"),
    ("is_apneic",                   "yes",        "heart_rate_assessment"),
    ("heart_rate_category",         "under_100",  "ventilation_path"),
    ("start_ventilation",           "yes",        "ventilation_started_state"),
    ("apply_pulse_oximeter",        "yes",        "ventilation_in_progress"),
    ("confirm_effective_ventilation","yes",        "spo2_assessment"),
    ("spo2_category",               "acceptable", "routine_observation"),
    ("continue_observation",        "yes",        "simulation_complete"),
]
hp_ok = True
for action, response, expected in steps:
    r = submit(sid, action, response)
    got = r["current_state"]["id"]
    ok = got == expected
    if not ok:
        failures.append(f"happy path {action}={response}: expected={expected} got={got}")
        hp_ok = False
stop(sid)
print("TEST 1 — happy path 13/13: " + ("PASSED" if hp_ok else "FAILED"))

# ──────────────────────────────────────────────────────────────────────────────
# TEST 2: GET /sessions returns ActiveSessionItem[] structure
# ──────────────────────────────────────────────────────────────────────────────
r = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
sid2 = r["session_id"]

sessions = get("/api/sessions/sessions")
ok = (
    isinstance(sessions, list) and
    len(sessions) >= 1 and
    all(
        k in sessions[0]
        for k in ("session_id", "scenario_id", "scenario_name", "status", "current_state_id")
    )
)
if not ok:
    failures.append(f"session list structure wrong: {sessions}")
print("TEST 2 — GET /sessions structure: " + ("PASSED" if ok else "FAILED"))

# ──────────────────────────────────────────────────────────────────────────────
# TEST 3: POST /instructor fires transition correctly
# ──────────────────────────────────────────────────────────────────────────────
r = instructor(sid2, "start_birth_workflow")
got = r["current_state"]["id"]
ok = got == "put_on_mothers_chest"
if not ok:
    failures.append(f"instructor event: expected put_on_mothers_chest got {got}")
print("TEST 3 — POST /instructor state transition: " + ("PASSED" if ok else "FAILED"))

# Advance to ventilation_in_progress for timer test
instructor(sid2, "advance_to_crying_assessment")
instructor(sid2, "initial_steps_complete")
instructor(sid2, "baby_not_crying")
instructor(sid2, "assess_heart_rate")
instructor(sid2, "heart_rate_under_100")
instructor(sid2, "ventilation_started")
r = instructor(sid2, "pulse_oximeter_applied")
got = r["current_state"]["id"]
ok = got == "ventilation_in_progress"
if not ok:
    failures.append(f"fast-forward to ventilation_in_progress: got {got}")
print("TEST 3b — instructor fast-forward to ventilation_in_progress: " + ("PASSED" if ok else "FAILED"))

# ──────────────────────────────────────────────────────────────────────────────
# TEST 4: POST /timer/{id} fires manual timer in ventilation_in_progress
# ──────────────────────────────────────────────────────────────────────────────
r = post(f"/api/sessions/sessions/{sid2}/timer/ventilation_timer")
got = r["current_state"]["id"]
ok = got == "heart_rate_after_ventilation"
if not ok:
    failures.append(f"timer trigger: expected heart_rate_after_ventilation got {got}")
print("TEST 4 — POST /timer/{id} fires transition: " + ("PASSED" if ok else "FAILED"))

# ──────────────────────────────────────────────────────────────────────────────
# TEST 5: GET /export/csv returns valid CSV
# ──────────────────────────────────────────────────────────────────────────────
req = urllib.request.Request(BASE + f"/api/sessions/sessions/{sid2}/export/csv")
with urllib.request.urlopen(req) as resp:
    csv_status = resp.status
    csv_bytes = resp.read()

csv_text = csv_bytes.decode("utf-8-sig")
rows = [r for r in csv_text.splitlines() if r.strip()]
ok = csv_status == 200 and len(rows) >= 2
if not ok:
    failures.append(f"CSV export: status={csv_status} rows={len(rows)}")
print(f"TEST 5 — CSV export ({len(rows)} rows including header): " + ("PASSED" if ok else "FAILED"))

# ──────────────────────────────────────────────────────────────────────────────
# TEST 6: Instructor stop session
# ──────────────────────────────────────────────────────────────────────────────
r = stop(sid2)
ok = "session_id" in r
# Session should now be gone
try:
    get(f"/api/sessions/sessions/{sid2}")
    failures.append("session still exists after stop")
    ok = False
except urllib.error.HTTPError as e:
    ok = e.code == 404
print("TEST 6 — stop session + confirm 404: " + ("PASSED" if ok else "FAILED"))

# ──────────────────────────────────────────────────────────────────────────────
# TEST 7: describe_breathing text transitions (P1-FSM-02 fix)
# ──────────────────────────────────────────────────────────────────────────────
def advance_to_apnea(sid):
    submit(sid, "confirm_birth", "yes")
    submit(sid, "placed_on_chest", "yes")
    submit(sid, "warm_dry_stimulate", "yes")
    submit(sid, "position_airway", "yes")
    submit(sid, "clear_airway_if_needed", "yes")
    submit(sid, "is_baby_crying", "no")

text_ok = True
for word in ("apnea", "gasping", "breathing"):
    r = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    s = r["session_id"]
    advance_to_apnea(s)
    r = submit(s, "describe_breathing", word)
    got = r["current_state"]["id"]
    if got != "heart_rate_assessment":
        failures.append(f"describe_breathing '{word}': expected heart_rate_assessment got {got}")
        text_ok = False
    stop(s)
print("TEST 7 — describe_breathing apnea/gasping/breathing: " + ("PASSED" if text_ok else "FAILED"))

# ──────────────────────────────────────────────────────────────────────────────
print()
if failures:
    print("RESULT: FAILED")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
else:
    print("RESULT: ALL 7 TESTS PASSED")
