"""
WebSocket end-to-end acceptance test.
Connects a real WebSocket client, runs the full clinical simulation via REST,
and captures every WS event, close code, and close reason.
"""
import asyncio
import json
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

import websockets


BASE_HTTP = "http://127.0.0.1:8000"
BASE_WS   = "ws://127.0.0.1:8000"

received_messages: list[dict] = []
ws_close_code: Optional[int] = None
ws_close_reason: Optional[str] = None
ws_state_log: list[str] = []


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def http_post(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else b""
    req = urllib.request.Request(
        f"{BASE_HTTP}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def http_get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE_HTTP}{path}")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


async def ws_listener(ws, stop_event: asyncio.Event):
    """Reads every message the server pushes; records close code on exit."""
    global ws_close_code, ws_close_reason
    try:
        async for raw in ws:
            msg = json.loads(raw)
            received_messages.append(msg)
            print(f"  [{ts()}] WS_MSG: type={msg.get('type')} seq={msg.get('sequence')}")
    except websockets.exceptions.ConnectionClosedOK as exc:
        ws_close_code   = exc.code
        ws_close_reason = exc.reason
        print(f"  [{ts()}] WS_CLOSE_OK: code={exc.code} reason={exc.reason!r}")
    except websockets.exceptions.ConnectionClosedError as exc:
        ws_close_code   = exc.code
        ws_close_reason = exc.reason
        print(f"  [{ts()}] WS_CLOSE_ERROR: code={exc.code} reason={exc.reason!r}")
    except Exception as exc:
        print(f"  [{ts()}] WS_EXCEPTION: {type(exc).__name__}: {exc}")
    finally:
        stop_event.set()


async def run_test():
    global ws_close_code, ws_close_reason

    # ── 1. Start session ────────────────────────────────────────────────────
    print(f"\n[{ts()}] Starting session …")
    session = http_post("/api/sessions/sessions/start", {"scenario_id": "baby_birth"})
    sid = session["session_id"]
    print(f"[{ts()}] Session: {sid}  initial_state={session['current_state']['id']}")

    # ── 2. Connect WebSocket ────────────────────────────────────────────────
    ws_url = f"{BASE_WS}/api/ws/sessions/{sid}/student"
    print(f"[{ts()}] Connecting WebSocket: {ws_url}")

    stop_event = asyncio.Event()

    async with websockets.connect(ws_url) as ws:
        ws_state_log.append(f"OPEN state={ws.state}")
        print(f"[{ts()}] WS OPEN  state={ws.state}")

        # Start listener task
        listener = asyncio.create_task(ws_listener(ws, stop_event))

        # Brief pause so the connection.accepted message can arrive
        await asyncio.sleep(0.3)

        # ── 3. Run full simulation via REST ──────────────────────────────────
        steps = [
            ("TIMER",  "birth_timer",       None,    None),
            ("INPUT",  "placed_on_chest",   "yes",   None),
            ("INPUT",  "is_baby_crying",    "no",    None),
            ("INPUT",  "is_apneic",         "yes",   None),
            ("INPUT",  "hr_above_100",      "no",    None),
            ("INPUT",  "start_ventilation", "yes",   None),
            ("TIMER",  "ventilation_timer", None,    None),
            ("INPUT",  "hr_increasing",     "yes",   None),
            ("TIMER",  "continue_ventilation_timer", None, None),
        ]

        for kind, name, response, _ in steps:
            await asyncio.sleep(0.3)  # give WS a moment between events
            if kind == "TIMER":
                result = http_post(f"/api/sessions/sessions/{sid}/timer/{name}")
                print(f"[{ts()}] TIMER {name} -> {result['current_state']['id']}")
            else:
                result = http_post(
                    f"/api/sessions/sessions/{sid}/input",
                    {"action_id": name, "response": response},
                )
                print(f"[{ts()}] INPUT {name}={response} -> {result['current_state']['id']}")

        # ── 4. Wait a moment, then stop the session ─────────────────────────
        await asyncio.sleep(1.0)
        print(f"[{ts()}] Stopping session …")
        http_post(f"/api/sessions/sessions/{sid}/stop")
        print(f"[{ts()}] Session stopped")

        # ── 5. Send a client-side ping (to verify socket still open) ────────
        await asyncio.sleep(0.5)
        if not stop_event.is_set():
            try:
                await ws.send(json.dumps({"type": "ping"}))
                print(f"[{ts()}] Ping sent — socket is still open")
            except Exception as exc:
                print(f"[{ts()}] Ping FAILED — socket closed before we sent: {type(exc).__name__}: {exc}")
        else:
            print(f"[{ts()}] Socket already closed before ping")

        # ── 6. Close from the client side ────────────────────────────────────
        await asyncio.sleep(0.5)
        ws_state_log.append(f"BEFORE_CLIENT_CLOSE state={ws.state}")
        print(f"[{ts()}] Client closing WebSocket …")
        await ws.close(1000, "test complete")
        ws_state_log.append(f"AFTER_CLIENT_CLOSE state={ws.state}")
        print(f"[{ts()}] Client close sent")

        # Cancel listener
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

    # ── 7. Summary ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"WebSocket state log:  {ws_state_log}")
    print(f"Messages received:    {len(received_messages)}")
    print(f"Close code:           {ws_close_code}")
    print(f"Close reason:         {ws_close_reason!r}")
    print(f"\nMessage types received:")
    for m in received_messages:
        print(f"  seq={m.get('sequence'):>4}  type={m.get('type')}")
    print("="*60)

    # ── 8. Verdict ────────────────────────────────────────────────────────────
    all_expected = {
        "connection.accepted",
        "session.started",
        "fsm.state_transition",
        "timer.expired",
        "student.input",
        "session.stopped",
    }
    received_types = {m.get("type") for m in received_messages}
    missing = all_expected - received_types
    unexpected_close = ws_close_code not in (None, 1000, 1001)

    if missing:
        print(f"\n⚠  MISSING event types: {missing}")
    if unexpected_close:
        print(f"\n✗  UNEXPECTED close code: {ws_close_code} — this causes the reconnect banner")
    if not missing and not unexpected_close:
        print("\n✓  WebSocket lifecycle: PASS")


if __name__ == "__main__":
    asyncio.run(run_test())
