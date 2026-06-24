import urllib.request
import json
import sys

BASE = "http://127.0.0.1:8765"

def post(path, body=None):
    data = json.dumps(body).encode() if body else b""
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def submit(sid, action, response):
    return post(f"/api/sessions/sessions/{sid}/input", {"action_id": action, "response": response})

def stop(sid):
    return post(f"/api/sessions/sessions/{sid}/stop")

def start():
    return post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})

def advance_to_apnea(sid):
    submit(sid, "confirm_birth", "yes")
    submit(sid, "placed_on_chest", "yes")
    submit(sid, "warm_dry_stimulate", "yes")
    submit(sid, "position_airway", "yes")
    submit(sid, "clear_airway_if_needed", "yes")
    r = submit(sid, "is_baby_crying", "no")
    assert r["current_state"]["id"] == "apnea_assessment", \
        "fast-forward failed, got " + r["current_state"]["id"]

failures = []

# ── CHECK 1: validate_scenario ────────────────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.scenario import load_scenario, validate_scenario
s = load_scenario(os.path.join(os.path.dirname(__file__), "..", "scenarios", "baby_birth.json"))
validate_scenario(s)
print("CHECK 1: validate_scenario() PASSED")

# ── CHECK 2: no duplicate IDs ────────────────────────────────────────────────
all_ids = [t.id for state in s.states for t in state.transitions]
dupes = [id for id in all_ids if all_ids.count(id) > 1]
if dupes:
    failures.append("duplicate transition IDs: " + str(set(dupes)))
    print("CHECK 2: FAIL - duplicates: " + str(set(dupes)))
else:
    print("CHECK 2: no duplicate IDs PASSED")

# ── CHECK 3: happy path unchanged ────────────────────────────────────────────
r = start(); sid = r["session_id"]
steps = [
    ("confirm_birth", "yes", "put_on_mothers_chest"),
    ("placed_on_chest", "yes", "initial_steps"),
    ("warm_dry_stimulate", "yes", "initial_steps"),
    ("position_airway", "yes", "initial_steps"),
    ("clear_airway_if_needed", "yes", "crying_assessment"),
    ("is_baby_crying", "no", "apnea_assessment"),
    ("is_apneic", "yes", "heart_rate_assessment"),
    ("heart_rate_category", "under_100", "ventilation_path"),
    ("start_ventilation", "yes", "ventilation_started_state"),
    ("apply_pulse_oximeter", "yes", "ventilation_in_progress"),
    ("confirm_effective_ventilation", "yes", "spo2_assessment"),
    ("spo2_category", "acceptable", "routine_observation"),
    ("continue_observation", "yes", "simulation_complete"),
]
hp_ok = True
for action, response, expected in steps:
    r = submit(sid, action, response)
    if r["current_state"]["id"] != expected:
        failures.append(f"happy path: {action}={response} expected={expected} got={r['current_state']['id']}")
        hp_ok = False
stop(sid)
print("CHECK 3: happy path " + ("PASSED" if hp_ok else "FAILED"))

# ── CHECK 4: "apnea" still works ─────────────────────────────────────────────
r = start(); sid = r["session_id"]
advance_to_apnea(sid)
r = submit(sid, "describe_breathing", "apnea")
got = r["current_state"]["id"]
ok = got == "heart_rate_assessment"
if not ok:
    failures.append("apnea text: expected heart_rate_assessment, got " + got)
stop(sid)
print("CHECK 4: apnea->heart_rate_assessment " + ("PASSED" if ok else "FAILED"))

# ── CHECK 5: "gasping" now works ─────────────────────────────────────────────
r = start(); sid = r["session_id"]
advance_to_apnea(sid)
r = submit(sid, "describe_breathing", "gasping")
got = r["current_state"]["id"]
ok = got == "heart_rate_assessment"
if not ok:
    failures.append("gasping text: expected heart_rate_assessment, got " + got)
stop(sid)
print("CHECK 5: gasping->heart_rate_assessment " + ("PASSED" if ok else "FAILED"))

# ── CHECK 6: "breathing" now works ───────────────────────────────────────────
r = start(); sid = r["session_id"]
advance_to_apnea(sid)
r = submit(sid, "describe_breathing", "breathing")
got = r["current_state"]["id"]
ok = got == "heart_rate_assessment"
if not ok:
    failures.append("breathing text: expected heart_rate_assessment, got " + got)
stop(sid)
print("CHECK 6: breathing->heart_rate_assessment " + ("PASSED" if ok else "FAILED"))

# ── TRANSITION COUNT ──────────────────────────────────────────────────────────
total = sum(len(st.transitions) for st in s.states)
ap_state = next(st for st in s.states if st.id == "apnea_assessment")
print(f"\napnea_assessment transitions: {len(ap_state.transitions)}")
for t in ap_state.transitions:
    print(f"  {t.id} ({t.trigger}) -> {t.target_state}")
print(f"Total scenario transitions: {total}")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print()
if failures:
    print("RESULT: FAILED")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
else:
    print("RESULT: ALL 6 CHECKS PASSED")
