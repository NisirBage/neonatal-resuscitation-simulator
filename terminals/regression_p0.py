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

def instructor(sid, event):
    return post(f"/api/sessions/sessions/{sid}/instructor", {"event_name": event})

def submit(sid, action, response):
    return post(f"/api/sessions/sessions/{sid}/input", {"action_id": action, "response": response})

def stop(sid):
    return post(f"/api/sessions/sessions/{sid}/stop")

failures = []

# ── HAPPY PATH ──────────────────────────────────────────────────────────────────
r = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
sid = r["session_id"]
assert r["current_state"]["id"] == "baby_born"
print("START: baby_born")

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

for action, response, expected in steps:
    r = submit(sid, action, response)
    got = r["current_state"]["id"]
    ok = got == expected
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {action}={response} -> {got}")
    if not ok:
        failures.append(f"happy path: {action}={response} expected={expected} got={got}")

print("HAPPY PATH: " + ("PASSED" if not failures else "FAILED"))
stop(sid)

# ── ADVANCED RESUSCITATION EXIT ──────────────────────────────────────────────
r = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
sid2 = r["session_id"]

# fast-forward via instructor to advanced_resuscitation
instructor(sid2, "start_birth_workflow")        # baby_born -> put_on_mothers_chest
instructor(sid2, "advance_to_crying_assessment")# put_on_mothers_chest -> initial_steps
instructor(sid2, "initial_steps_complete")      # initial_steps -> crying_assessment
instructor(sid2, "baby_not_crying")             # crying_assessment -> apnea_assessment
instructor(sid2, "assess_heart_rate")           # apnea_assessment -> heart_rate_assessment
instructor(sid2, "heart_rate_under_100")        # heart_rate_assessment -> ventilation_path
instructor(sid2, "ventilation_started")         # ventilation_path -> ventilation_started_state
instructor(sid2, "pulse_oximeter_applied")      # ventilation_started_state -> ventilation_in_progress
instructor(sid2, "ventilation_timer_complete")  # ventilation_in_progress -> heart_rate_after_ventilation
r = instructor(sid2, "heart_rate_under_60")     # heart_rate_after_ventilation -> advanced_resuscitation

got = r["current_state"]["id"]
if got == "advanced_resuscitation":
    print("ADV RESUS: entered advanced_resuscitation OK")
else:
    msg = "fast-forward to advanced_resuscitation failed, got " + got
    failures.append(msg)
    print("  [FAIL] " + msg)

# self-loops must still work
r = submit(sid2, "start_chest_compressions", "yes")
if r["current_state"]["id"] == "advanced_resuscitation":
    print("ADV RESUS: self-loop OK")
else:
    failures.append("self-loop broken, got " + r["current_state"]["id"])

# NEW exit via instructor
r = instructor(sid2, "advanced_resuscitation_complete")
got = r["current_state"]["id"]
if got == "simulation_complete":
    print("ADV RESUS: advanced_resuscitation_complete -> simulation_complete OK")
else:
    msg = "exit transition failed, got " + got
    failures.append(msg)
    print("  [FAIL] " + msg)

stop(sid2)

# ── VENTILATION PATH TIMER CHECK ─────────────────────────────────────────────
r = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
sid3 = r["session_id"]
instructor(sid3, "start_birth_workflow")
instructor(sid3, "advance_to_crying_assessment")
instructor(sid3, "initial_steps_complete")
instructor(sid3, "baby_not_crying")
instructor(sid3, "assess_heart_rate")
r = instructor(sid3, "heart_rate_under_100")  # -> ventilation_path

assert r["current_state"]["id"] == "ventilation_path"
timers = r["current_state"].get("timers", [])
timer_ids = [t["id"] for t in timers]
if timer_ids:
    failures.append("ventilation_path still has timers: " + str(timer_ids))
    print("  [FAIL] ventilation_path timers not removed: " + str(timer_ids))
else:
    print("VENTILATION PATH: no orphaned timer OK")

stop(sid3)

# ── SUMMARY ──────────────────────────────────────────────────────────────────
print()
if failures:
    print("RESULT: FAILED")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
