import json
import urllib.request
import urllib.error
import sys

BASE = "http://127.0.0.1:8000"

def post(path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

# ── 1. START SESSION ──────────────────────────────────────────────────────────
code, session = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
assert code == 200, f"Start session failed: {code} {session}"
sid = session["session_id"]
print(f"[START] HTTP {code}  session_id={sid}")
print(f"[START] initial_state={session['current_state']['id']}")
print(f"[START] initial_name={session['current_state']['name']}")
print()

# ── 2. HAPPY PATH ─────────────────────────────────────────────────────────────
steps = [
    ("baby_born",                   "confirm_birth",                 "yes",        "put_on_mothers_chest"),
    ("put_on_mothers_chest",        "placed_on_chest",               "yes",        "initial_steps"),
    ("initial_steps",               "warm_dry_stimulate",            "yes",        "initial_steps"),
    ("initial_steps",               "position_airway",               "yes",        "initial_steps"),
    ("initial_steps",               "clear_airway_if_needed",        "yes",        "crying_assessment"),
    ("crying_assessment",           "is_baby_crying",                "no",         "apnea_assessment"),
    ("apnea_assessment",            "is_apneic",                     "yes",        "heart_rate_assessment"),
    ("heart_rate_assessment",       "heart_rate_category",           "under_100",  "ventilation_path"),
    ("ventilation_path",            "start_ventilation",             "yes",        "ventilation_started_state"),
    ("ventilation_started_state",   "apply_pulse_oximeter",          "yes",        "ventilation_in_progress"),
    ("ventilation_in_progress",     "confirm_effective_ventilation", "yes",        "spo2_assessment"),
    ("spo2_assessment",             "spo2_category",                 "acceptable", "routine_observation"),
    ("routine_observation",         "continue_observation",          "yes",        "simulation_complete"),
]

results = []
for i, (expected_before, action_id, response, expected_after) in enumerate(steps, 1):
    code, body = post(f"/api/sessions/sessions/{sid}/input",
                      {"action_id": action_id, "response": response})
    got_state = body.get("current_state", {}).get("id", "ERROR") if code == 200 else "HTTP_ERROR"
    ok = (code == 200) and (got_state == expected_after)
    tag = "OK  " if ok else "FAIL"
    results.append((ok, i, action_id, response, expected_after, got_state, code))
    print(f"[STEP {i:02d}] {tag}  action={action_id}  response={response}")
    print(f"         HTTP={code}  expected={expected_after}  got={got_state}")
    if code != 200:
        print(f"         ERROR={json.dumps(body)}")
    print()

# ── 3. FINAL STATE ───────────────────────────────────────────────────────────
code, raw = get(f"/api/sessions/sessions/{sid}")
final = json.loads(raw)
print(f"[FINAL] HTTP {code}")
print(f"[FINAL] state={final['current_state']['id']}")
print(f"[FINAL] status={final['status']}")
print(f"[FINAL] history_events={len(final.get('history', []))}")
print()

# ── 4. EVENT HISTORY ANALYSIS ────────────────────────────────────────────────
history = final.get("history", [])
print(f"[HISTORY] Total events: {len(history)}")
no_transitions = [e for e in history if e["type"] == "no_transition"]
state_transitions = [e for e in history if e["type"] == "state_transition"]
student_inputs = [e for e in history if e["type"] == "student_input"]
timer_events = [e for e in history if e["type"] == "timer_event"]
print(f"[HISTORY]   session_started : {sum(1 for e in history if e['type']=='session_started')}")
print(f"[HISTORY]   student_input   : {len(student_inputs)}")
print(f"[HISTORY]   state_transition: {len(state_transitions)}")
print(f"[HISTORY]   no_transition   : {len(no_transitions)}")
print(f"[HISTORY]   timer_event     : {len(timer_events)}")
print()
if no_transitions:
    print("[HISTORY] !! NO_TRANSITION EVENTS FOUND !!")
    for e in no_transitions:
        print(f"  state={e['state_id']} payload={e['payload']}")
    print()

print("[HISTORY] State transition path:")
for e in state_transitions:
    p = e.get("payload", {})
    print(f"  {p.get('from_state','?')} -> {p.get('to_state','?')}  (transition={e.get('transition_id','?')})")
print()

# ── 5. CSV EXPORT ────────────────────────────────────────────────────────────
code, csv_bytes = get(f"/api/sessions/sessions/{sid}/export/csv")
print(f"[CSV] HTTP {code}")
if code == 200:
    csv_text = csv_bytes.decode("utf-8-sig")
    lines = csv_text.splitlines()
    print(f"[CSV] Total rows (including header): {len(lines)}")
    print(f"[CSV] Header: {lines[0]}")
    print(f"[CSV] Data rows: {len(lines)-1}")
    # Count by event type
    event_types = {}
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) >= 3:
            et = parts[2]
            event_types[et] = event_types.get(et, 0) + 1
    print(f"[CSV] Event type distribution: {event_types}")
    # Save
    with open("C:/Users/BIT/neonatal-resuscitation-simulator/terminals/rehearsal_export.csv", "wb") as f:
        f.write(csv_bytes)
    print("[CSV] Saved to terminals/rehearsal_export.csv")
else:
    print(f"[CSV] FAILED: {csv_bytes[:200]}")
print()

# ── 6. STOP SESSION ──────────────────────────────────────────────────────────
code, body = post(f"/api/sessions/sessions/{sid}/stop")
print(f"[STOP] HTTP {code}  status={body.get('status','?')}")
print()

# ── 7. CONFIRM EXPORT FAILS AFTER STOP ──────────────────────────────────────
code2, raw2 = get(f"/api/sessions/sessions/{sid}/export/csv")
print(f"[POST-STOP CSV] HTTP {code2}  (expected 404)")
print()

# ── 8. SUMMARY ───────────────────────────────────────────────────────────────
passed = sum(1 for r in results if r[0])
failed = sum(1 for r in results if not r[0])
print(f"[SUMMARY] Steps passed: {passed}/{len(results)}")
print(f"[SUMMARY] Steps failed: {failed}/{len(results)}")
print(f"[SUMMARY] no_transition events: {len(no_transitions)}")
print(f"[SUMMARY] Verdict: {'GO' if failed==0 and len(no_transitions)==0 else 'NO-GO'}")
