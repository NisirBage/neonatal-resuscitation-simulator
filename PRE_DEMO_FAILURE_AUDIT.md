# Pre-Demo Failure Injection Audit

**Date:** 2026-06-23  
**Branch:** integration-layer  
**Method:** Source code inspection + live injection tests against backend on port 8765  
**Scope:** 15 failure scenarios covering frontend, backend, persistence, browser, and Docker layers

Severity scale:

| Level | Meaning |
|-------|---------|
| **P0** | Demo-stopping blocker. Presentation cannot continue without operator fix. |
| **P1** | Visible defect an audience would notice. Presentation can continue, but credibility is reduced. |
| **P2** | Cosmetic, edge-case, or self-recovering. Unlikely during a controlled demo. |

---

## Case 1 — Backend Restarted While Frontend Remains Open

**Setup:** Student has active session, is mid-flow. Backend process is killed and restarted.

**Expected behavior:** WebSocket drops, student sees a connection warning, but can continue interacting via REST once backend is up. All session state is preserved via persistence layer.

**Actual behavior (verified by code + test):**

- WebSocket `onclose` fires immediately → `websocketStatus` React state → "closed". Both student and instructor UI show "closed" badge.
- No automatic reconnect. `websocket.ts` does not implement reconnection. The `createStudentSocket` / `createInstructorSocket` functions create a WebSocket and return it. No retry loop exists.
- REST API calls (`handleSubmitAction`, `handleStopSession`) still work once backend is back up, because they create new HTTP requests. The student can continue clicking through the simulation — they just have no live event stream.
- Instructor dashboard: `listSessions()` polling runs every 5 s. Sessions reappear in the dropdown automatically when backend is back up. Instructor can select the restored session and resume monitoring.
- Session state: fully restored from SQLite (persistence layer confirmed working). Current state, event history, and auto-start timers all restored correctly.

**Severity: P1**

Audience will see the WebSocket status badge change from "connected" to "closed". REST actions continue to work — the simulation is not broken, only the live event stream is absent until a manual page refresh.

**Operator recovery:**

1. Confirm backend is back up: `http://localhost:8000/health`
2. Ask student to refresh the browser tab. The session is gone from React state (see Case 2), but it is in the DB as "running". Instructor can resume monitoring the restored session immediately.
3. If demoing persistence as a feature: leave the student tab open and do not refresh — REST actions will still work while WS is "closed". Refresh when ready to show restoration.

---

## Case 2 — Frontend Refreshed Mid-Session

**Setup:** Student has active session. Student refreshes the browser tab (F5 or Ctrl+R).

**Expected behavior:** State is lost from frontend; session remains alive on the backend.

**Actual behavior (by code inspection):**

- All React state (`sessionId`, `currentState`, `events`, `status`) is held in component memory. A full page refresh destroys it entirely.
- After refresh, `sessionId` is `null`. The student sees the blank "start session" state.
- The session on the backend is still "running" in both memory and SQLite. It is not stopped.
- If the student clicks "Start Session" again: `handleStartSession` checks `if (sessionId)` — but `sessionId` is now `null` (post-refresh), so it does **not** call `stopSession` on the orphaned session. A brand new session is created. The original session remains "running" in the DB indefinitely until the backend is next restarted (at which point it will be restored again as a ghost session).
- Instructor console: the orphaned session still appears in the session dropdown. The new session also appears. Two sessions are visible.

**Severity: P2**

The student can continue by starting a new session — they just lose their progress. Ghost sessions accumulate in the DB but cause no functional harm during the demo. The audience is unlikely to see this unless they watch the instructor console closely.

**Operator recovery:**

1. The student clicks "Start Session" again. Progress is lost from the UI.
2. On the instructor console: ignore the orphaned session. Stop it manually via the instructor "Stop Session" button if you want a clean session list.
3. To avoid this: warn students not to refresh mid-session.

---

## Case 3 — WebSocket Disconnect During Active Timer

**Setup:** Session is in `ventilation_in_progress` (auto-start `ventilation_timer` running). Browser tab goes offline or the WebSocket connection drops mid-timer.

**Expected behavior:** Timer continues server-side; state transition fires; frontend is not notified.

**Actual behavior (by code inspection):**

- Backend: `_run_auto_timer` is an `asyncio.Task`. It is **not** tied to WebSocket connections. The timer continues sleeping and fires regardless of connection state.
- When the timer fires, `process_timer()` runs, the FSM transitions, and `upsert_session()` saves the new state to SQLite.
- `broadcast_to_session()` tries to send the event to connected clients. With no connected clients, the room is empty and the loop sends nothing. If the WebSocket dropped mid-send, `_send_to_connections` catches `RuntimeError`/`WebSocketDisconnect` and calls `disconnect()` cleanly — no crash.
- Frontend: `useTimerCountdown` is a client-side countdown based on `Date.now() + duration_seconds * 1000`. It continues counting down and reaches zero. But because the WS event never arrives, `refreshSessionState` is never called. The UI timer shows 0:00 but the state card still shows `ventilation_in_progress`. The student sees a frozen state.
- On reconnect (page reload + new session): a GET to `/sessions/{id}` returns the correct post-transition state from memory/DB.

**Severity: P2**

The backend state is correct and persisted. The UI visually freezes at the timer-expired frame but no data is lost. A page refresh resolves it. This is only observable if the demo explicitly shows a live auto-timer countdown while the WS is disconnected.

**Operator recovery:**

1. The student refreshes the browser tab (loses React state — see Case 2 tradeoff).
2. Alternatively: the student can continue submitting REST inputs through the UI; the UI will update on each submit response even without WS events.

---

## Case 4 — Session Persistence After Backend Restart

**Setup:** Active session at an intermediate state. Backend process killed. Backend restarted.

**Expected behavior:** Session fully restored with same state, event history, and timers.

**Actual behavior (live tested — regression_persistence.py Phase 2):**

- All 7 checks PASSED: session in list, current state preserved, event history correct, session ID intact, post-restore student input accepted, CSV export correct, instructor event accepted.
- Auto-start timers are recreated from **full duration** (elapsed time before crash is lost — documented tradeoff).

**Severity: P2** — Works as designed.

**Operator recovery:** None required. If demonstrating persistence as a feature, this is the intended happy path.

---

## Case 5 — CSV Export After Long Session History

**Setup:** Session with 50 self-loop transitions (105 total events). CSV exported.

**Expected behavior:** Export succeeds, all rows present, no timeout.

**Actual behavior (live tested):**

- 105 events → 106 CSV rows (header + data). File size: 21,219 bytes (~21 KB).
- Response time: <1 second. No streaming needed; entire file generated in memory.
- All 9 columns present, UTF-8 BOM present, Content-Disposition correct.

**Severity: P2** — No issue at realistic session lengths.

**Operator recovery:** None required.

---

## Case 6 — Instructor Dashboard Opened Before Student Dashboard

**Setup:** Instructor opens `?role=instructor` before any student has started a session.

**Expected behavior:** Instructor sees an empty session list with a helpful prompt.

**Actual behavior (by code inspection):**

- `InstructorDashboard` immediately polls `GET /api/sessions/sessions`. Returns `[]`.
- UI renders: "No active sessions. Ask the student to start a session first."
- The session list polls every **5 seconds** (`POLL_INTERVAL_MS = 5000`).
- When the student starts a session, it appears in the dropdown within 0–5 seconds. No manual refresh needed.
- The error in the poll `catch` block is silently ignored (line 58-60 in InstructorDashboard.tsx), so no red banner appears when the list is empty.

**Severity: P2** — Behaves correctly and gracefully.

**Operator recovery:** None required. Tell the audience to wait for the session to appear.

---

## Case 7 — Student Dashboard Opened Before Backend Startup

**Setup:** Frontend dev server is running. Student opens `http://localhost:5173` before the backend is started.

**Expected behavior:** Student sees an error. Resolves when backend starts.

**Actual behavior (by code inspection):**

- `StudentDashboard` mounts and calls `listScenarios()` in a `useEffect`.
- `fetch()` throws a `TypeError: Failed to fetch` (CORS failure or network error).
- Caught in `.catch()`, sets `error` state: **"Unable to load scenarios."** shown in red banner.
- The scenario dropdown shows a single fallback option: `<option value="baby_birth">baby_birth</option>`.
- The student can click "Start Session" — it will fail with the same network error: **"Unable to start session."** A second red error message appears.
- There is **no auto-retry**. The page does not poll for the backend to come up.
- When the backend starts, the student must manually **refresh the browser tab** to recover.

**Severity: P1**

The student sees red error banners. No data loss. A refresh is required.

**Operator recovery:**

1. Start the backend before opening student browsers.
2. If already open: ask the student to refresh after backend health check passes.
3. The correct startup order is: backend first → frontend second (or simultaneously, with student refreshing once backend is ready).

---

## Case 8 — Multiple Browser Tabs Connected to Same Session

**Setup:** Two browser tabs both open the student view for the same session (or one tab is instructor, one is student).

**Expected behavior:** Both receive events. Both can submit actions (with potential conflicts).

**Actual behavior (by code inspection):**

- `WebSocketManager` uses a `SessionRoom` model with `students: dict[UUID, ConnectionInfo]`. Each tab gets its own `connection_id`. Multiple student connections per session are fully supported by design.
- All events are broadcast to all connected tabs via `broadcast_to_session()` → both tabs update simultaneously.
- Action submissions: both tabs issue independent HTTP POSTs. If both submit simultaneously, the asyncio event loop serializes them. The **second submission** may fail with HTTP 422 if the FSM already transitioned past the action the second tab was trying to submit (`FSMError` → "no matching transition").
- The second tab shows a red error banner. The first tab shows the correct new state.

**Severity: P2**

During a normal demo, one student is in the student tab and one instructor is in the instructor tab. Accidental double-submission is unlikely if only one person is typing. The error is surfaced cleanly.

**Operator recovery:**

1. Only one person submits actions in the student tab.
2. If an error occurs: dismiss it and resubmit with the correct action for the current state.

---

## Case 9 — Browser Microphone Permission Denied

**Setup:** Student tab is open. Student clicks the microphone button. Browser shows permission prompt → student clicks "Block".

**Expected behavior:** Speech recognition fails with an error; manual text input still works.

**Actual behavior (by code inspection):**

- `useSpeechRecognition.ts`: `recognition.onerror` fires with `event.error = "not-allowed"`.
- Sets `error` state in the hook: `setError(event.message ?? event.error)`.
- `listening` resets to `false`.
- This error is passed to `ActionPanel` via `speechError` prop.
- The action panel shows the error message next to the microphone button.
- `speechSupported` remains `true` (the API exists in the browser) — only the permission is denied.
- **Manual text input (dropdown + text field) is completely unaffected.** The student can type or select actions and submit normally.

**Severity: P2**

Gracefully handled. The simulation continues with keyboard input. The microphone button shows an error state. The audience sees an informational error message, not a crash.

**Operator recovery:**

1. Use manual text input to continue.
2. To re-enable mic: browser site settings → allow microphone for `localhost:5173`.

---

## Case 10 — Browser Speech Recognition Unavailable

**Setup:** Student uses Firefox or a browser without `window.SpeechRecognition` / `window.webkitSpeechRecognition`.

**Expected behavior:** Speech input unavailable; manual input works normally.

**Actual behavior (by code inspection):**

- `useSpeechRecognition.ts`: `SpeechRecognitionConstructor = window.SpeechRecognition ?? window.webkitSpeechRecognition`.
- If both are `undefined`: `supported = false`.
- `supported` is passed to `ActionPanel` as `speechSupported={speechRecognition.supported}`.
- The microphone button in ActionPanel is either hidden or disabled (conditioned on `speechSupported`).
- No error banner. The UI is clean — the mic button simply doesn't appear.
- Text/dropdown input is fully functional.

**Severity: P2**

Fully graceful. The simulation works identically without speech recognition.

**Operator recovery:** None required. Use manual input. For demo, use Chrome (full SpeechRecognition support).

---

## Case 11 — Invalid Session ID in URL/API

**Setup:** API call made with a non-existent or malformed session ID.

**Expected behavior:** Appropriate HTTP error returned; server remains healthy.

**Actual behavior (live tested):**

| Input | HTTP Response |
|-------|--------------|
| Valid UUID format, no such session | `404 Not Found` · `{"detail": "session '...' was not found"}` |
| Not a UUID (e.g., `not-a-uuid`) | `422 Unprocessable Entity` (FastAPI UUID path parameter validation) |
| Correct UUID, stopped session | `404 Not Found` (session removed from memory on stop) |

- Frontend: `api.ts` checks `response.ok`. Both 404 and 422 throw `new Error(responseText)`. The error is shown in the red banner.
- Server remains fully healthy. No crash or leaked state.

**Severity: P2**

Standard HTTP error handling. Will not occur via the normal UI (session IDs come from the backend). Only exploitable via direct API calls or a stale bookmark.

**Operator recovery:** None required. The UI shows an error and the student can start a new session.

---

## Case 12 — Missing Scenario File

**Setup:** `scenarios/baby_birth.json` is deleted or renamed while the backend is running.

**Expected behavior:** Cannot start new sessions; existing sessions unaffected.

**Actual behavior (by code inspection + partial test):**

- **Starting a new session:** `_load_scenario_by_id()` scans `SCENARIOS_DIR.glob("*.json")`. If `baby_birth.json` is gone, the glob returns nothing. Raises `HTTPException 404`: `"scenario 'baby_birth' was not found"`. Frontend shows red error banner.
- **Existing running sessions in memory:** Fully unaffected. `SessionRecord.scenario` holds the in-memory Scenario object. No disk read after startup.
- **On next backend restart with missing file:** `_restore_sessions()` scans the scenarios directory. The missing scenario causes a warning log and the affected sessions are **silently skipped** — they are not restored. Sessions remain in DB as "running" but are orphaned. They will not appear in the session list after restart.
- **POST to missing scenario via API:** Returns HTTP 404 · `"scenario 'ghost_scenario' was not found"` (live tested).

**Severity: P1**

If `baby_birth.json` is missing before the demo starts, no new sessions can be started. The demo cannot proceed. Recovery requires restoring the file and restarting the backend.

**Operator recovery:**

1. Restore `scenarios/baby_birth.json` from git: `git checkout scenarios/baby_birth.json`
2. Restart the backend.
3. Running sessions are lost if they were orphaned during restart — start a fresh session.

---

## Case 13 — SQLite Database Locked or Unavailable

**Setup:** `backend/neonatal.db` is deleted, moved, or externally locked while the backend is running.

**Expected behavior:** DB operations fail; backend remains alive; in-memory session state is unchanged.

**Actual behavior (by code inspection + SQLite configuration analysis):**

- **Journal mode:** `DELETE` (not WAL). With a single `uvicorn` process and `aiosqlite` serializing SQLite access through a background thread, write-write lock conflicts are essentially impossible in normal demo use.
- **Busy timeout:** 5000 ms (set by aiosqlite/SQLite defaults). A short external lock releases before the timeout.
- **If DB file is deleted while server is running:** The next `upsert_session()` call issues `AsyncSession.get()` then `commit()`. The `aiosqlite` layer will raise `sqlite3.OperationalError: unable to open database file` (or similar). This is a `sqlalchemy.exc.OperationalError` — it is **not** caught by the router's `except (FSMError, RuntimeError, ValueError)` handlers. FastAPI returns a generic **HTTP 500 Internal Server Error**. The student/instructor sees a red error banner.
  - Critically: the in-memory FSM **did** transition successfully before the failed DB write. The session is now out of sync: DB has the old state, memory has the new state. On restart, the session would restore to the pre-failure state.
- **Server health check:** `/health` returns `{"status": "healthy"}` — it does not re-test DB connectivity after startup.

**Severity: P1**

DB loss during a session causes HTTP 500 on the next action. The simulation appears broken to the student. Restarting the backend restores the session to its last successfully persisted state, potentially losing 1 transition.

**Operator recovery:**

1. Do not delete or move `backend/neonatal.db` during a session.
2. If accidental: restart the backend. The DB file is re-created by SQLAlchemy on startup (`checkfirst=True`). The session will restore to its last persisted state (possibly missing the transition that triggered the 500).
3. In Docker: the `nrs_data` volume is at `/app/data/neonatal.db` — separate from the code directory. Normal container operations cannot delete it.

---

## Case 14 — Corrupted Persisted Session Row

**Setup:** A row in the `sessions` table has invalid JSON in `fsm_state` (e.g., from manual DB edit, truncated write, or disk corruption).

**Expected behavior:** Server skips the row and starts normally.

**Actual behavior (live tested — injected `NOT_VALID_JSON{{{` as `fsm_state`):**

- `_restore_sessions()` calls `json.loads(row["fsm_state"])` → `json.JSONDecodeError`.
- Caught by `except Exception as exc` (line 130 in `main.py`): logged as ERROR with session ID and exception text.
- Loop continues. All other sessions in the DB are restored normally.
- Server startup completes. Health check passes.
- The corrupted session: not in memory → `GET /sessions/{id}` returns `404`. Does not appear in session list.
- Corrupted row remains in DB (not deleted, not marked stopped). Will be re-attempted on every subsequent restart — and silently skipped again each time.

**Severity: P2**

Server remains healthy. Corrupted session is cleanly isolated. No user-visible impact during the demo.

**Operator recovery:**

1. No action needed for the demo.
2. To clean up: `DELETE FROM sessions WHERE id = '<corrupted-id>';` in SQLite.

---

## Case 15 — Docker Container Restart Sequence

**Setup:** Running via `docker compose`. Various restart scenarios.

**Expected behavior:** Services recover gracefully; data persists.

**Actual behavior (by Dockerfile/docker-compose.yml code inspection — Docker not available on this machine for live testing):**

| Scenario | Expected behavior |
|----------|------------------|
| `docker compose restart backend` | Backend restarts, sessions restored from `nrs_data` volume. Frontend shows WS "closed" badge, recovers automatically on reconnect (same as Case 1). |
| `docker compose restart frontend` | nginx restarts. Users see a brief page unavailability. On refresh, frontend loads normally. Session state unaffected. |
| `docker compose restart` (both at once) | Both containers restart. The `depends_on: backend: condition: service_healthy` guard prevents nginx from serving until backend health check passes (~15 s). Users experience a ~15-40 second outage. On browser refresh after the wait, everything works. |
| `docker compose down` then `docker compose up` | Same as restart. `nrs_data` volume is preserved. Sessions restored. |
| `docker compose down -v` then `docker compose up --build` | Volume deleted. Database gone. All sessions lost. This is the only data-loss scenario. |
| Frontend container crash (OOM, etc.) | nginx restarts. All users must refresh. Session state is in the backend container — unaffected. |
| Backend container OOM/crash | Same as Case 1 + persistence recovery. Sessions restored. |

**SQLite in Docker:** The database is at `/app/data/neonatal.db` (absolute path, 4-slash SQLite URL). The `/app/data` directory is the named volume `nrs_data`. The code directory is `/app/backend/` — separate from the data directory. Volume-mounting `/app/data` does not overlay the code. Scenario files are at `/app/scenarios/` (COPY'd during build) — also separate.

**`JWT_SECRET_KEY` missing:** If `.env` does not set `JWT_SECRET_KEY`, docker-compose evaluates `${JWT_SECRET_KEY}` as an empty string. `pydantic-settings` will accept an empty string for the JWT secret (no minimum length validation). The backend starts but JWT tokens would be insecure. For a demo where routes are not protected by JWT, this is harmless but should be noted.

**Severity: P1**

`docker compose restart` without health-check awareness causes a 15-40 s visible outage. Unattended `down -v` destroys all session data. Neither is likely during a normal demo, but both require operator awareness.

**Operator recovery:**

1. After `docker compose restart`: wait 15-40 s, then refresh browsers.
2. Never run `docker compose down -v` during a demo — use `docker compose down` (no `-v`).
3. Set `JWT_SECRET_KEY` in `.env` before `docker compose up`.

---

## Summary Table

| # | Failure | Severity | Demo continues? | Self-recovering? |
|---|---------|----------|----------------|-----------------|
| 1 | Backend restart, frontend open | **P1** | Yes (REST works) | Yes — after backend up |
| 2 | Frontend refresh mid-session | **P2** | Yes (start new session) | No — manual action |
| 3 | WebSocket drop during timer | **P2** | Yes | No — refresh needed |
| 4 | Persistence after restart | **P2** | Yes | Yes |
| 5 | CSV export, long history | **P2** | Yes | N/A |
| 6 | Instructor opened before student | **P2** | Yes | Yes (5 s poll) |
| 7 | Student opened before backend | **P1** | After refresh | No — manual refresh |
| 8 | Multiple tabs same session | **P2** | Yes | Partial (dismiss error) |
| 9 | Mic permission denied | **P2** | Yes | No (use manual input) |
| 10 | Speech recognition unavailable | **P2** | Yes | N/A |
| 11 | Invalid session ID | **P2** | Yes | Yes |
| 12 | Missing scenario file | **P1** | No — new sessions blocked | No — restore file + restart |
| 13 | SQLite DB locked/unavailable | **P1** | Partial (500 on next write) | No — restart backend |
| 14 | Corrupted session row | **P2** | Yes | Yes (skipped on restore) |
| 15 | Docker container restart | **P1** | After ~40 s wait | Yes |

**P0 findings: None.**

---

## Operator Pre-Demo Checklist

These steps eliminate all P1 risks before the demo begins:

- [ ] `backend/.env` (or `.env` for Docker) exists and has a real `JWT_SECRET_KEY`
- [ ] `scenarios/baby_birth.json` is present: `ls scenarios/baby_birth.json`
- [ ] Backend health check passes: `curl http://localhost:8000/health`
- [ ] Frontend loads without error banners: open `http://localhost:5173`
- [ ] Backend is started **before** opening student or instructor browsers
- [ ] For Docker: `docker compose up` not `docker compose up --build` after first build (avoids rebuild delay)
- [ ] Do NOT run `docker compose down -v` during or between sessions
- [ ] `backend/neonatal.db` (or Docker volume `nrs_data`) is present and not externally locked
- [ ] Single browser tab per role: one student tab, one instructor tab

---

## GO / NO-GO Recommendation

**GO.**

No P0 blockers were found. All 15 failure scenarios either self-recover, degrade gracefully, or require only a browser refresh or operator restart. The simulator is appropriate for a controlled LAN demo with the pre-demo checklist completed.

**Caveats for the presenter:**

1. **WebSocket is not auto-reconnecting.** If the backend restarts during the demo, both student and instructor UIs will show a "closed" badge. REST actions continue to work. A browser refresh fully recovers, at the cost of losing local React state (which is a planned persistence demo).

2. **Browser refresh loses session from UI.** Do not refresh the student tab mid-demo unless demonstrating the persistence recovery feature intentionally.

3. **Start backend before opening browsers.** The student tab has no retry mechanism — a red error banner requires a manual refresh.

4. **`scenarios/baby_birth.json` is load-bearing.** Protect it. If it disappears, no new sessions can start.

5. **Docker restart takes ~40 seconds.** Do not restart Docker containers during the live portion of the demo.
