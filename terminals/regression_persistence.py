"""
Persistence regression test.

Runs against a live server on port 8765.
Phases:
  --phase1  : start session, advance to initial_steps, print session_id
  --phase2  : given --session-id, verify state + history survive restart
  (no args) : run both phases; user is prompted to restart the server between them
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def _call(method, path, body=None):
    data = json.dumps(body).encode() if body else b""
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def get(path):
    return _call("GET", path)


def post(path, body=None):
    return _call("POST", path, body)


def submit(sid, action, response):
    return post(f"/api/sessions/sessions/{sid}/input", {"action_id": action, "response": response})


def instructor(sid, event):
    return post(f"/api/sessions/sessions/{sid}/instructor", {"event_name": event})


def stop(sid):
    return post(f"/api/sessions/sessions/{sid}/stop")


def wait_for_server(timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            get("/health")
            return True
        except Exception:
            time.sleep(0.4)
    return False


# ─────────────────────────────────────────────────────────────
# PHASE 1: create and advance a session
# ─────────────────────────────────────────────────────────────

def phase1():
    print("=== PHASE 1: creating session and advancing state ===")

    r = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = r["session_id"]
    assert r["current_state"]["id"] == "baby_born", f"unexpected initial state: {r['current_state']['id']}"
    print(f"  Session created: {sid}")

    r = submit(sid, "confirm_birth", "yes")
    assert r["current_state"]["id"] == "put_on_mothers_chest"
    r = submit(sid, "placed_on_chest", "yes")
    assert r["current_state"]["id"] == "initial_steps"

    print(f"  Advanced to: {r['current_state']['id']}")
    print(f"SESSION_ID={sid}")
    return sid


# ─────────────────────────────────────────────────────────────
# PHASE 2: verify restore
# ─────────────────────────────────────────────────────────────

def phase2(sid, failures):
    print(f"\n=== PHASE 2: verifying restore for session {sid} ===")

    # TEST A: session appears in session list
    sessions = get("/api/sessions/sessions")
    found = any(s["session_id"] == sid for s in sessions)
    if not found:
        failures.append(f"RESTORE: session {sid} not found in GET /sessions after restart")
    print(f"  A — session in list: {'PASSED' if found else 'FAILED'}")

    # TEST B: current state preserved
    r = get(f"/api/sessions/sessions/{sid}")
    got_state = r["current_state"]["id"]
    ok = got_state == "initial_steps"
    if not ok:
        failures.append(f"RESTORE: expected state=initial_steps, got={got_state}")
    print(f"  B — current_state preserved ({got_state}): {'PASSED' if ok else 'FAILED'}")

    # TEST C: event_history preserved (3 transitions: baby_born→put_on_mothers_chest→initial_steps)
    history = r.get("history", [])
    state_transitions = [e for e in history if e["type"] == "state_transition"]
    ok = len(state_transitions) >= 2
    if not ok:
        failures.append(f"RESTORE: expected >=2 state_transitions in history, got {len(state_transitions)}")
    print(f"  C — event_history has {len(state_transitions)} state_transition(s): {'PASSED' if ok else 'FAILED'}")

    # TEST D: session_id field matches
    ok = r["session_id"] == sid
    if not ok:
        failures.append(f"RESTORE: session_id mismatch: {r['session_id']} vs {sid}")
    print(f"  D — session_id intact: {'PASSED' if ok else 'FAILED'}")

    # TEST E: can continue advancing state after restore
    r2 = submit(sid, "warm_dry_stimulate", "yes")
    got = r2["current_state"]["id"]
    ok = got == "initial_steps"  # self-loop
    if not ok:
        failures.append(f"RESTORE: post-restore input failed, state={got}")
    print(f"  E — post-restore student input accepted: {'PASSED' if ok else 'FAILED'}")

    # TEST F: CSV export still works
    req = urllib.request.Request(BASE + f"/api/sessions/sessions/{sid}/export/csv")
    with urllib.request.urlopen(req) as resp:
        csv_text = resp.read().decode("utf-8-sig")
    rows = [row for row in csv_text.splitlines() if row.strip()]
    ok = len(rows) >= 3  # header + session_started + at least 2 transitions
    if not ok:
        failures.append(f"CSV: expected >=3 rows, got {len(rows)}")
    print(f"  F — CSV export has {len(rows)} rows (including header): {'PASSED' if ok else 'FAILED'}")

    # TEST G: instructor event works on restored session
    r3 = instructor(sid, "initial_steps_complete")
    got = r3["current_state"]["id"]
    ok = got == "crying_assessment"
    if not ok:
        failures.append(f"RESTORE: instructor event on restored session failed, state={got}")
    print(f"  G — instructor event on restored session: {'PASSED' if ok else 'FAILED'}")


# ─────────────────────────────────────────────────────────────
# PHASE 3: stopped sessions must not resurface
# ─────────────────────────────────────────────────────────────

def phase3_stopped_sessions(failures):
    print("\n=== PHASE 3: stopped sessions do not restore ===")

    r = post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid_to_stop = r["session_id"]
    stop(sid_to_stop)
    print(f"  Stopped session: {sid_to_stop}")

    # It should not appear in the session list after stop
    sessions = get("/api/sessions/sessions")
    found = any(s["session_id"] == sid_to_stop for s in sessions)
    ok = not found
    if not ok:
        failures.append(f"STOPPED: session {sid_to_stop} still listed after stop")
    print(f"  H — stopped session not in list: {'PASSED' if ok else 'FAILED'}")

    # GET should 404
    try:
        get(f"/api/sessions/sessions/{sid_to_stop}")
        failures.append(f"STOPPED: GET {sid_to_stop} returned 200, expected 404")
        ok = False
    except urllib.error.HTTPError as e:
        ok = e.code == 404
        if not ok:
            failures.append(f"STOPPED: GET {sid_to_stop} returned {e.code}, expected 404")
    print(f"  I — stopped session returns 404: {'PASSED' if ok else 'FAILED'}")

    return sid_to_stop


# ─────────────────────────────────────────────────────────────
# INTERACTIVE DRIVER (no args)
# ─────────────────────────────────────────────────────────────

def run_interactive():
    if not wait_for_server():
        print("ERROR: server not reachable on port 8765")
        sys.exit(1)

    failures = []

    sid = phase1()
    sid_stopped = phase3_stopped_sessions(failures)

    print("\n" + "=" * 60)
    print("SERVER RESTART REQUIRED")
    print("Stop uvicorn (Ctrl+C), restart it, then press Enter here.")
    print("=" * 60)
    input("Press Enter after server is back up... ")

    if not wait_for_server(timeout=20):
        print("ERROR: server did not come back up within 20s")
        sys.exit(1)

    phase2(sid, failures)

    # Verify stopped session also did not come back after restart
    print("\n=== PHASE 3b: stopped session not restored after restart ===")
    sessions = get("/api/sessions/sessions")
    found = any(s["session_id"] == sid_stopped for s in sessions)
    ok = not found
    if not ok:
        failures.append(f"STOPPED RESTORE: stopped session {sid_stopped} reappeared after restart")
    print(f"  J — stopped session absent after restart: {'PASSED' if ok else 'FAILED'}")

    print("\n" + "=" * 60)
    if failures:
        print("RESULT: FAILED")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("RESULT: ALL TESTS PASSED")


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--phase1" in args:
        if not wait_for_server():
            print("ERROR: server not reachable")
            sys.exit(1)
        phase1()

    elif "--phase2" in args:
        try:
            idx = args.index("--session-id")
            sid = args[idx + 1]
        except (ValueError, IndexError):
            print("ERROR: --phase2 requires --session-id <uuid>")
            sys.exit(1)
        if not wait_for_server():
            print("ERROR: server not reachable")
            sys.exit(1)
        failures = []
        phase2(sid, failures)
        if failures:
            for f in failures:
                print(f"FAIL: {f}")
            sys.exit(1)
        print("RESULT: ALL PHASE 2 CHECKS PASSED")

    else:
        run_interactive()
