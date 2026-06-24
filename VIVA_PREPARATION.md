# VIVA & DEMONSTRATION PREPARATION
## Neonatal Resuscitation Simulator — BIT Mesra MO-2026

---

## PART 1 — EXECUTIVE SUMMARY

**Project:** Neonatal Resuscitation Simulator
**Department:** Electronics & Communication Engineering, BIT Mesra, Ranchi
**Course:** MO-2026
**Supervisor:** Dr. Sanjay Kumar, Professor & Head

### Problem Statement

Neonatal resuscitation — the emergency intervention performed in the first minutes after birth — is one of the most time-critical and decision-intensive procedures in clinical medicine. Approximately 10% of newborns require some assistance to begin breathing; up to 1% require extensive resuscitation. In conventional training, students study the protocol from textbooks and static flowcharts. They do not practise making sequential decisions under time pressure, and their responses are not recorded for objective evaluation.

### Objective

Design and build a web-based interactive simulator that guides a medical student through the complete neonatal resuscitation protocol step by step, enforces clinical correctness using a formal computational model, supports real-time instructor monitoring and intervention, and produces a structured audit log of every student action for assessment.

### Solution

A full-stack event-driven web application consisting of:
- A **Python FastAPI** backend hosting a **Finite State Machine (FSM) engine** that encodes the professor's clinical flowchart as 17 states and 64 transitions in a JSON scenario file
- Automatic **asyncio-based countdown timers** (birth timer: 60 s, ventilation timer: 30 s, heart rate reassessment: 15 s) that fire state transitions without student input
- A **WebSocket event bus** that pushes every state change to all connected browsers in real time
- A **SQLite persistence layer** that saves session state on every transition, enabling full crash recovery
- A **React 19 + TypeScript frontend** with voice input (browser SpeechRecognition API), voice output (SpeechSynthesis), and a visual progress tracker
- A dedicated **instructor console** with live session monitoring, override controls, manual timer triggers, and CSV export

### Technologies Used

| Layer | Technology |
|-------|------------|
| Backend API | Python 3.10, FastAPI, uvicorn |
| Concurrency | Python asyncio |
| Data Validation | Pydantic v2 |
| Database | SQLite via SQLAlchemy + aiosqlite |
| Frontend | React 19, TypeScript, Tailwind CSS, Vite |
| Real-time Communication | WebSocket (native browser + FastAPI) |
| Voice Input | Browser Web Speech API (SpeechRecognition) |
| Voice Output | Browser SpeechSynthesis API |
| Containerisation | Docker + Docker Compose |

### Key Outcomes

- 17-state clinical workflow covering the complete neonatal resuscitation protocol
- 61 automated acceptance tests — all passing
- 15 failure scenarios injected and audited — zero P0 (demo-blocking) failures found
- Full session persistence: sessions survive backend crash and restart
- Voice normalisation layer mapping natural speech to FSM-compatible responses
- CSV export with 9-column audit trail, UTF-8 BOM for Excel compatibility
- Instructor console with real-time monitoring and override capability
- Docker deployment ready (Dockerfile + docker-compose.yml, syntax verified)

---

## PART 2 — 3-MINUTE PROJECT PITCH

> Audience: Professor seeing the project for the first time.

---

Every year, millions of babies are born who need help to begin breathing. The neonatal resuscitation protocol is the globally standardised clinical procedure for these first critical minutes — a decision tree that tells the attending team exactly what to do based on what they observe. Get it right, and the baby survives. Miss a step or make the wrong decision, and the consequences are irreversible.

Despite the stakes, most medical students learn this protocol from a piece of paper. They memorise the flowchart. They never practise the decision-making under time pressure. They never experience a timer running down. And no one records what they did so it can be reviewed later.

We built a Neonatal Resuscitation Simulator to change that. It is a web application that puts a student through the resuscitation protocol as if it were happening in real time. The student is asked: "Has the baby been born? Is the baby crying? What is the heart rate?" — and they must respond, either by typing or by speaking out loud. The system responds: it advances to the next clinical step if the answer is correct, records it if it is wrong, and keeps running in the background — because in real resuscitation, the clock does not stop.

The innovation is that the entire clinical protocol lives in a structured file on the server, interpreted by a Finite State Machine engine. The FSM is the enforcer of clinical correctness: it knows every valid state, every valid transition, every timer duration. The student cannot skip steps. Their choices are recorded with timestamps.

At the same time, an instructor console runs alongside. The instructor watches every step in real time. They can intervene, skip ahead, trigger timers manually, or export a complete log of what the student did — suitable for grading.

The system passed 61 automated acceptance tests with zero failures, has been audited against 15 real-world failure scenarios, and is containerised with Docker for easy deployment. It is built on Python, React, and WebSockets — standard, open-source technologies — and requires no special hardware beyond a laptop and a web browser.

---

## PART 3 — 5-MINUTE TECHNICAL WALKTHROUGH

> Path: Scenario JSON → FSM Engine → Scenario Runner → Session Manager → Event Bus → REST + WebSockets → React Frontend

---

### Step 1 — The Scenario JSON (30 seconds)

Everything begins with `baby_birth.json` in the `scenarios/` directory. This file encodes the professor's flowchart as a machine-readable graph: 17 states (clinical moments), 64 transitions (decision rules), and 5 automatic timers. Each state has actions the student must complete, and each transition specifies: "if action X receives response Y in state Z, move to state W." This is the only file that contains clinical content. The rest of the system is generic.

### Step 2 — The FSM Engine (60 seconds)

When a session starts, the backend instantiates an `FSMEngine` object from the scenario. This object holds the scenario definition and the current `SimulationState` — which is just two things: the current state ID and the growing list of events.

When the student submits "Is heart rate greater than 100 bpm? — No", the engine's `process_student_input()` is called. It acquires an `RLock` (for thread safety), finds the transition that matches action ID `heart_rate_greater_than_100` with response `no`, updates `current_state_id` to `ventilation_started`, appends a `state_transition` event to history, and returns a deep copy of the new state. The FSM is deterministic, thread-safe, and has no network code inside it.

### Step 3 — The Scenario Runner and Timers (60 seconds)

Above the FSM sits the `ScenarioRunner`. After every FSM transition, it checks whether the new state has any `auto_start` timers. If it does — for example, entering `ventilation_in_progress` triggers the 30-second `ventilation_timer` — it creates an `asyncio.Task` that sleeps for 30 seconds and then calls `process_timer()` on the FSM. If the session leaves the state before the timer fires (e.g., the instructor overrides), all timers for that state are cancelled. Timers are pure asyncio coroutines — no threads, no polling.

After every action, the runner publishes an event to the Event Bus and calls the Persistence Layer to write the full session state to SQLite.

### Step 4 — Session Manager and Persistence (30 seconds)

The `SessionManager` stores all active sessions in an in-memory Python dictionary, keyed by session UUID. Reads and writes are protected by `RLock`. On every successful FSM transition, `upsert_session()` serialises the full `FSMEngine` state — current state ID plus complete event history — as JSON and writes it to the `sessions` table in SQLite. On backend restart, `_restore_sessions()` reads all `running` rows from SQLite, deserialises them, rebuilds FSM engines, and reinstates them in memory. Sessions survive crashes completely.

### Step 5 — Event Bus and WebSocket Layer (60 seconds)

The `EventBus` is an in-process publish-subscribe system. Every event type — `student.input`, `timer.expired`, `fsm.state_transition` — is published after each action. The `WebSocketManager` subscribes to the wildcard `*`, receiving every event. When an event arrives, it serialises it as JSON and broadcasts it to every browser connected to that session's "room."

The WebSocket endpoint is `/api/ws/sessions/{session_id}/{role}`. A student browser connects as `student`; the instructor browser connects as `instructor`. Both receive all events in real time. Instructor-only events (analytics) are filtered to instructors only.

### Step 6 — The React Frontend and State Synchronisation (60 seconds)

The frontend is `StudentDashboard.tsx`. It maintains local state for the session ID, current state, and event log. When the student submits an action, it calls `POST /api/sessions/sessions/{id}/input` — a REST call that returns the new state directly. The frontend updates from the response.

When a **timer fires** on the server, the frontend receives a `timer.expired` WebSocket event. Instead of trying to update its own state from the event payload, it calls `GET /api/sessions/{id}` — fetching the authoritative state from the backend. The same happens for `fsm.state_transition` events. The frontend never maintains its own copy of the FSM state; it always re-reads from the backend. This is enforced by two concurrency guards: `activeSessionIdRef` (discards responses for the wrong session) and `refreshSequenceRef` (discards stale responses when two fetches race).

This architecture — backend owns state, frontend renders state — eliminates the entire class of frontend/backend divergence bugs.

---

## PART 4 — ARCHITECTURE DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BROWSER LAYER                               │
│                                                                     │
│  ┌──────────────────────────┐   ┌──────────────────────────────┐   │
│  │   Student Browser        │   │   Instructor Browser         │   │
│  │   localhost:5173         │   │   localhost:5173/?role=instr  │   │
│  │                          │   │                              │   │
│  │  StudentDashboard.tsx    │   │  InstructorDashboard.tsx     │   │
│  │  ├── StateCard           │   │  ├── Session selector        │   │
│  │  ├── ActionPanel         │   │  ├── Instructor buttons      │   │
│  │  ├── ProgressPanel       │   │  ├── Timer triggers          │   │
│  │  ├── EventPanel          │   │  ├── CSV export              │   │
│  │  └── DemoModePanel       │   │  └── EventPanel              │   │
│  │                          │   │                              │   │
│  │  useSpeechRecognition    │   │  Polls GET /sessions (5s)    │   │
│  │  useSpeechSynthesis      │   │                              │   │
│  │  normalizeSpokenResponse │   │                              │   │
│  └───────────┬──────────────┘   └──────────────┬───────────────┘  │
└──────────────┼───────────────────────────────────┼─────────────────┘
               │  HTTP REST (api.ts)               │  HTTP REST
               │  WebSocket (websocket.ts)         │  WebSocket
               ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND  (port 8000)                     │
│                         uvicorn ASGI                                │
│                                                                     │
│  ┌──────────────┐  ┌─────────────────┐  ┌────────────────────┐    │
│  │ REST Routers │  │  WebSocket      │  │  CORSMiddleware     │    │
│  │              │  │  Router         │  │                    │    │
│  │ /sessions/*  │  │ /ws/sessions/   │  │  ALLOWED_ORIGINS   │    │
│  │ /scenarios/* │  │  {id}/{role}    │  │                    │    │
│  └──────┬───────┘  └──────┬──────────┘  └────────────────────┘    │
│         │                 │                                         │
│         ▼                 ▼                                         │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │                   ScenarioRunner                          │     │
│  │  ┌────────────────────────────────────────────────────┐  │     │
│  │  │              FSMEngine (per session)               │  │     │
│  │  │  scenario: Scenario (17 states, 64 transitions)    │  │     │
│  │  │  state: SimulationState (current_state_id +        │  │     │
│  │  │                          event_history)            │  │     │
│  │  │  _lock: RLock                                      │  │     │
│  │  │                                                    │  │     │
│  │  │  process_student_input()                           │  │     │
│  │  │  process_timer_event()                             │  │     │
│  │  │  process_instructor_event()                        │  │     │
│  │  └────────────────────────────────────────────────────┘  │     │
│  │                                                           │     │
│  │  asyncio.Task per auto_start timer                        │     │
│  │  ┌─ birth_timer (60s)                                     │     │
│  │  ├─ ventilation_timer (30s)                               │     │
│  │  ├─ corrective_ventilation_timer (30s)                    │     │
│  │  ├─ heart_rate_reassessment_timer (15s)                   │     │
│  │  └─ continue_ventilation_timer (15s)                      │     │
│  └───────────────────────────────────────────────────────────┘     │
│         │                 │                                         │
│         ▼                 ▼                                         │
│  ┌──────────────┐  ┌──────────────────────────────────────────┐   │
│  │ SessionMgr   │  │  EventBus (pub/sub)                      │   │
│  │              │  │  subscribers: { "*": WebSocketManager }  │   │
│  │ _sessions:   │  │                                          │   │
│  │  dict[UUID,  │  │  Events published:                       │   │
│  │  SessionRec] │  │  session.started / session.stopped       │   │
│  │  _lock:RLock │  │  student.input / audio.input             │   │
│  └──────┬───────┘  │  timer.expired / instructor.action       │   │
│         │          │  fsm.state_transition / fsm.no_transition│   │
│         │          └──────────────────┬───────────────────────┘   │
│         │                             │                            │
│         ▼                             ▼                            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │             WebSocketManager                                 │  │
│  │  _rooms: dict[UUID, SessionRoom]                             │  │
│  │  SessionRoom: { students: dict, instructors: dict }          │  │
│  │  broadcast_to_session() / broadcast_to_instructors()         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │             Persistence Layer (SQLAlchemy + aiosqlite)        │  │
│  │  upsert_session()  → writes on every transition              │  │
│  │  _restore_sessions() → reads on startup                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐   ┌────────────────────────────────┐
│  SQLite: backend/neonatal.db  │   │  scenarios/baby_birth.json     │
│  Table: sessions              │   │  17 states, 64 transitions     │
│  Columns:                     │   │  5 auto-start timers           │
│  id, scenario_id, fsm_state,  │   │  Loaded from disk on demand    │
│  status, created_at,          │   │  No restart needed to update   │
│  updated_at                   │   │                                │
└──────────────────────────────┘   └────────────────────────────────┘
```

---

## PART 5 — 30 VIVA QUESTIONS WITH MODEL ANSWERS

---

### FSM

**Q1. What is a Finite State Machine and why is it appropriate for this project?**

A Finite State Machine (FSM) is a mathematical model of computation that exists in exactly one state at any time and transitions between states based on defined inputs. It is appropriate here because the neonatal resuscitation protocol is itself a formal flowchart — a sequence of clinical decision points where each outcome determines the next step. The FSM maps this structure directly: each clinical moment is a state, each decision is a transition, and the protocol rules become the transition conditions. FSMs are deterministic (same input always gives same output), auditable (every transition is an event), and provably correct (the scenario file can be formally validated).

**Q2. How does the FSM handle an invalid student input?**

The FSM's `_find_transition()` iterates all transitions in the current state searching for one whose trigger, action ID, and expected response all match. If no match is found, `_process_transition()` is called with `transition=None`. This appends a `no_transition` event to the history without changing `current_state_id`. The student remains in the same state. The event is broadcast via WebSocket and appears in the CSV export.

**Q3. How does the FSM handle self-loop transitions (same source and target state)?**

Self-loops are handled identically to normal transitions. The engine updates `current_state_id` to the same value (no change) and appends a `state_transition` event to history. The event contains `from_state` and `to_state` with the same value. This is by design — the audit trail must record that the student confirmed "warm, dry, stimulate = yes" even if the state did not change, because that confirmation may be required for assessment.

**Q4. How is thread safety guaranteed in the FSM?**

Every public method of `FSMEngine` that reads or modifies state is wrapped in `with self._lock:` where `_lock` is a `threading.RLock` (reentrant lock). This ensures only one thread can execute FSM logic at a time. Methods that return state return `deepcopy(self._state)` — a completely independent copy — so callers cannot modify the engine's internal state through a shared reference. The combination of locking and deep copying eliminates all data races.

**Q5. Can the FSM be restored after a crash?**

Yes. `FSMEngine.serialize()` converts the `SimulationState` to a JSON-serialisable dictionary. `FSMEngine.deserialize(scenario, data)` reconstructs an engine from a saved dictionary and a scenario object. The `SimulationState` contains `current_state_id` and `event_history` — everything needed to resume exactly where the session stopped.

---

### WebSockets

**Q6. Why use WebSockets instead of polling?**

Polling requires the browser to repeatedly ask the server "has anything changed?" — typically every 1–5 seconds. For a training simulator where timers fire automatically and events can happen any second, polling introduces unacceptable latency (up to the poll interval) and unnecessary server load. WebSockets maintain a persistent bidirectional connection. The server pushes events to the browser instantly when they occur, with no polling overhead and no latency.

**Q7. What happens when a WebSocket connection drops?**

The browser's `WebSocket.onclose` event fires, and the frontend sets `websocketStatus` to `"closed"`. A closed badge appears in the UI. The backend's `WebSocketManager` catches the `WebSocketDisconnect` exception in its `_send_to_connections` method and calls `disconnect()` to remove the connection from the session room. The session on the backend is completely unaffected — timers continue running, the FSM continues accepting REST inputs. The student can continue submitting answers via HTTP, they just lose the live event stream until they refresh.

**Q8. How are student and instructor events separated?**

The `WebSocketManager` maintains a `SessionRoom` with two separate dictionaries: `students` and `instructors`. `broadcast_to_session()` sends to both. `broadcast_to_instructors()` sends only to instructors. Events prefixed with `analytics.` are sent only to instructors. All other events go to everyone in the room. The role is determined at WebSocket connection time via the URL path: `/ws/sessions/{id}/student` or `/ws/sessions/{id}/instructor`.

**Q9. Can multiple students connect to the same session simultaneously?**

Yes. The `SessionRoom.students` dictionary holds one `ConnectionInfo` per connection, keyed by a unique `connection_id` UUID. Multiple student connections are fully supported. All receive all events. If two students submit actions simultaneously, asyncio serialises the requests. The second submission may fail with HTTP 422 if the FSM already transitioned past the action. This is handled gracefully — an error banner appears for the second student.

---

### Persistence

**Q10. What exactly is saved to SQLite on every transition?**

The full serialised `FSMEngine` state: `current_state_id` and the complete `event_history` list (every `SimulationEvent` ever recorded for the session), plus the full `Scenario` definition, `status`, `created_at`, and `updated_at`. This is serialised as JSON and stored in the `fsm_state` column of the `sessions` table. On restore, this JSON is deserialised into a `SimulationState` object and used to reconstruct the engine via `FSMEngine.deserialize()`.

**Q11. What sessions are restored after a backend restart?**

Only sessions with `status = 'running'`. Sessions that were explicitly stopped (`stop_session()` sets status to `'stopped'`) are not restored — this is correct behaviour. If a running session's row has corrupted JSON in `fsm_state`, the row is silently skipped and the server continues starting. The corrupted session does not appear in the session list.

**Q12. What is the tradeoff with timer restoration after a crash?**

Auto-start timers restart from their full configured duration after a crash. If the ventilation timer had 10 seconds remaining when the backend died, after recovery it will run for a full 30 seconds again. This is because we do not store the timer start timestamp — only the session state at the time of the last persisted transition. To fix this properly, we would need to record `started_at` for each active timer and compute the remaining time on restore. This tradeoff is documented and accepted for a training demo context.

---

### React Frontend

**Q13. Why does the frontend refetch from the backend after receiving a WebSocket event instead of updating from the event payload?**

Because the event payload contains only the event data — not the full current state. More importantly, this architectural decision eliminates frontend/backend state divergence. If the frontend maintained its own state copy and updated it from events, timer-driven transitions (which happen on the backend with no student action) might not synchronise correctly. By always fetching from `GET /sessions/{id}` after state-change events, the frontend always shows exactly what the backend FSM holds. The backend is the source of truth; the frontend is a render layer.

**Q14. What are `activeSessionIdRef` and `refreshSequenceRef`?**

Two concurrency guards in `StudentDashboard.tsx` that prevent stale API responses from corrupting the UI. `activeSessionIdRef` holds the current session ID as a React ref. If a `getSession()` call returns after the user has already started a new session, the response is discarded because `activeSessionIdRef.current` no longer matches the session ID the call was made for. `refreshSequenceRef` is a monotonically increasing counter. If two refresh calls are in flight simultaneously and the first one returns after the second, the first is discarded because its sequence number is older. Together they prevent race conditions.

**Q15. How does voice recognition work in the frontend?**

`useSpeechRecognition.ts` uses the browser's `window.SpeechRecognition` (or `window.webkitSpeechRecognition` for Chrome). `startListening()` creates a recognition instance, configures it for English (`en-US`), non-continuous mode, and starts it. The `onresult` callback accumulates transcript segments. When the student speaks "under one hundred", the transcript is passed to `normalizeSpokenResponse()` which uses regex patterns to map it to `"under_100"`. This normalised string is then placed in the response field. Manual text input is always available as a fallback if speech is unavailable or inaccurate.

---

### FastAPI

**Q16. Why FastAPI over Django or Flask?**

Three specific reasons. First, FastAPI is built on Starlette and has native `async/await` support throughout — essential for WebSocket handling and asyncio timer tasks. Django is synchronous by default; Flask requires the Quart extension for async. Second, FastAPI generates interactive Swagger UI documentation at `/docs` automatically from route and schema definitions — invaluable for development and demonstration. Third, FastAPI uses Pydantic for request/response validation, providing runtime type safety at API boundaries.

**Q17. How does FastAPI handle concurrent requests?**

FastAPI runs under uvicorn, an ASGI server. Uvicorn runs a single Python process with an asyncio event loop. Async route handlers (defined with `async def`) yield the event loop while waiting for I/O (database writes, etc.), allowing other requests to be processed concurrently. CPU-bound synchronous work (FSM state transitions) is fast enough to not block meaningfully. For production scale, multiple uvicorn workers would be used.

**Q18. What does the CORSMiddleware do and when does it matter?**

CORS (Cross-Origin Resource Sharing) is a browser security mechanism that blocks HTTP requests from one origin to another unless the server explicitly permits it. When the frontend at `localhost:5173` calls the backend at `localhost:8000`, they are different origins (different ports). `CORSMiddleware` adds `Access-Control-Allow-Origin` headers to all responses, telling the browser the request is permitted. If `ALLOWED_ORIGINS` does not include the frontend URL, all API calls fail silently in the browser. This is configured in `backend/.env`.

---

### SQLite

**Q19. Why SQLite instead of PostgreSQL for the demo?**

SQLite requires no separate server process, no installation, no credentials, and no network configuration. The database is a single file created automatically on first run. For a single-machine demo with one active session, SQLite handles the write throughput trivially. PostgreSQL is appropriate for production (multiple concurrent users, concurrent writes, network accessibility) and is supported via an environment variable. The choice is documented with the explicit understanding that it would be changed for production deployment.

**Q20. How does async SQLite work in Python?**

SQLite's standard `sqlite3` library is synchronous — it would block the asyncio event loop during database writes. `aiosqlite` wraps the synchronous SQLite driver in a background thread, exposing an async interface. When `await session.commit()` is called, aiosqlite offloads the actual disk write to the background thread and yields control back to the event loop. This allows the server to continue handling other requests while the database write completes, without blocking.

---

### Docker

**Q21. How is the application containerised?**

Two Dockerfiles: `backend/Dockerfile` and `frontend/Dockerfile`. The backend Dockerfile uses a Python 3.10 slim image, installs dependencies from `requirements.txt`, copies the application code and scenario files, and runs uvicorn. The frontend Dockerfile uses a Node 20 image to build the Vite bundle, then serves the static output from an nginx image. `docker-compose.yml` orchestrates both containers, sets environment variables, maps ports (8000 for backend, 5173 mapped from nginx's port 80), and mounts the `nrs_data` named volume for SQLite persistence. A `depends_on` health check ensures the frontend nginx only starts after the backend passes its health check.

**Q22. What is a Docker named volume and why is it used?**

A Docker named volume (`nrs_data`) is a persistent storage area managed by Docker, independent of any container's filesystem. The SQLite database is stored in this volume at `/app/data/neonatal.db`. When a container is stopped and removed (`docker compose down`), the volume persists — the database is not deleted. Only `docker compose down -v` (explicit volume removal) deletes the data. This ensures session data survives normal container lifecycle operations.

---

### CSV Export

**Q23. What does the CSV export contain and why is it structured that way?**

The CSV contains one row per FSM event with 9 columns: `timestamp`, `session_id`, `event_type`, `state_id`, `action_id`, `response`, `transition_id`, `target_state_id`, `details`. This structure was designed to be both human-readable in Excel and machine-parseable for analysis. The `event_type` column distinguishes between student inputs, timer events, instructor actions, state transitions, and no-transitions. The `transition_id` and `target_state_id` columns are populated only for actual state changes, making it easy to filter to just the clinical path. The UTF-8 BOM (`\xef\xbb\xbf`) is prepended so Excel on Windows opens the file with correct encoding automatically.

**Q24. How is the CSV generated — is it streamed or generated in memory?**

Generated entirely in memory using Python's `io.StringIO` buffer and `csv.DictWriter`. The complete event history is fetched from the FSM engine (already in memory), iterated once, and the resulting string is returned as a FastAPI `Response` with `media_type="text/csv"`. For a typical training session with hundreds of events, the CSV is a few kilobytes — well within memory limits. Streaming (using `StreamingResponse`) would be appropriate if session histories could grow to megabytes, which is not realistic for this use case.

---

### Timers

**Q25. How are multiple concurrent timers managed? What prevents them from interfering?**

The `ScenarioRunner` maintains `_timer_tasks: dict[UUID, dict[str, asyncio.Task]]` — a two-level dictionary keyed first by session ID, then by timer ID. When entering a new state, `_schedule_auto_start_timers()` first calls `_cancel_session_timers()` — which cancels all existing tasks for that session — before scheduling new ones. This ensures no leftover timer from a previous state can fire in a new state. The `_timer_lock: RLock` protects the dictionary from concurrent modification. When a timer's task completes, it removes itself from the dictionary.

---

### Testing

**Q26. How were the 61 acceptance tests structured?**

Tests are organised into 10 suites, each covering a specific capability: AT-01 (student happy path, 14 steps), AT-02 (instructor override, 10 steps), AT-03 (advanced resuscitation, 6 steps), AT-04 (timer-driven path, 4 steps), AT-05 (persistence recovery, 7 checks), AT-06 (CSV export, 6 checks), AT-07 (session lifecycle, 4 checks), AT-08 (scenario directory fix, 3 checks), AT-09 (self-loop persistence, 4 checks), AT-10 (text input variants, 3 checks). Each test makes REST API calls to a live backend instance and asserts on the response. All 61 tests passed.

**Q27. What is failure injection testing and what did it reveal?**

Failure injection is the deliberate simulation of failure scenarios to verify the system degrades gracefully. We tested 15 scenarios: backend restart with open frontend, browser refresh mid-session, WebSocket drop during timer, persistence recovery, CSV export at high event count, instructor before student, multiple concurrent tabs, microphone permission denial, speech API unavailability, invalid session IDs, missing scenario file, SQLite unavailability, corrupted database row, and two Docker restart scenarios. The audit found zero P0 (demo-blocking) failures. The most notable P1 (visible but survivable) findings were: the frontend shows "closed" badge when WebSocket drops (recovers on REST calls), and the student sees an error if they open the page before the backend starts (recovers on refresh).

---

### Design Decisions

**Q28. Why is clinical content in JSON rather than in the application code?**

Separation of concerns. The FSM engine is a general-purpose interpreter; the clinical workflow is data. Encoding the workflow in code would require a developer to modify and redeploy the application every time a professor changes the protocol. With JSON, the scenario can be changed without touching application code — in principle, a clinician could edit the file directly. The `validate_scenario()` function provides immediate feedback if the JSON is malformed. This design also makes it trivial to add new scenarios: drop a new JSON file into `scenarios/` and it immediately appears in the scenario list.

**Q29. Why is the instructor interface a separate URL path rather than a separate application?**

Sharing the same React application with role-based rendering (via `?role=instructor` query parameter) avoids code duplication. Authentication, session management, WebSocket setup, and API calls are shared. The `App.tsx` router checks the query parameter and renders either `StudentDashboard` or `InstructorDashboard`. This simplifies deployment (one build, one nginx server) and development (shared TypeScript types, shared API client). The tradeoff is that the student URL technically exposes the instructor URL if someone knows to add `?role=instructor` — acceptable for a demo with no authentication.

**Q30. How do you guarantee clinical correctness in the simulator?**

Four layers. First, the scenario JSON is validated by `validate_scenario()` before any session can start — no broken state references, no duplicate IDs. Second, the FSM engine enforces that only transitions defined in the scenario can occur — there is no way to skip a state or reach an undefined state. Third, the `event_history` is an immutable append-only log — every action is recorded and cannot be modified. Fourth, the 61 acceptance tests verify that the complete professor demo path (13 steps from `baby_born` to `simulation_complete`) executes correctly in the order and with the outcomes specified by the professor. Clinical correctness is enforced computationally, not by convention.

---

## PART 6 — ENGINEERING CHALLENGES

---

### Challenge 1 — Frontend/Backend State Divergence

**The Problem.** In the initial architecture, the frontend maintained its own copy of the FSM state. When the student submitted an action, the frontend updated its local state from the REST API response. When a timer fired on the backend, a WebSocket event was broadcast to the frontend. The frontend received the event and displayed it in the event log — but it did not update its local state. Result: after a timer-triggered transition, the backend was in state `heart_rate_after_ventilation` but the frontend still showed `ventilation_in_progress`. The student was answering questions about a state the backend had already moved past.

**The Solution.** We changed the frontend's contract: WebSocket events are not state updates — they are invalidation signals. When `fsm.state_transition` or `timer.expired` arrives, the frontend discards its current state and fetches the authoritative state from `GET /sessions/{id}`. We added `REFRESH_EVENT_TYPES = new Set(["fsm.state_transition", "timer.expired"])` and call `refreshSessionState()` whenever one of those events arrives. The backend FSM became the single and only source of truth.

**The Lesson.** In event-driven systems with multiple sources of state changes (user input, timers, external events), the client should not attempt to maintain a local replica of server state. The server is the authority; the client is a renderer. Any architecture that duplicates state in the client will eventually diverge.

---

### Challenge 2 — Timer Synchronisation

**The Problem.** asyncio tasks in Python run in an event loop. If the event loop is blocked (e.g., by a slow synchronous database call), timers do not fire at exactly their configured duration. Additionally, when timers need to be cancelled (because the session left the state), a naive implementation might cancel the currently executing timer task from within itself — causing a `CancelledError` to propagate incorrectly.

**The Solution.** `_cancel_session_timers()` checks `if task is not current_task` before cancelling — it never cancels the task that is currently running. The `_run_auto_timer()` coroutine handles `CancelledError` with `raise` (allowing asyncio to propagate it correctly) and catches `KeyError` and `RuntimeError` silently (which occur when the session is removed before the timer fires). The timer lock (`_timer_lock: RLock`) prevents concurrent modification of the tasks dictionary.

**The Lesson.** asyncio task management is subtle. Tasks that need to cancel themselves or that outlive the data structures they reference must be written defensively, with explicit handling of the case where the data they are acting on has been removed.

---

### Challenge 3 — Voice Normalisation

**The Problem.** The browser's SpeechRecognition API returns natural language. The FSM expects exact string values: `yes`, `no`, `under_100`, `100_or_more`, `under_60`. A student saying "yeah" would not match `yes`. A student saying "less than a hundred" would not match `under_100`. Every mismatch produces a `no_transition` event and the student is stuck.

**The Solution.** A `normalizeSpokenResponse()` function using regular expressions maps spoken variants to expected values. For example, `/\b(yes|yeah|yep|correct|affirmative)\b/` maps to `"yes"`; `/\b(under|below|less than)\s+(one\s+)?hundred\b/` maps to `"under_100"`. The fallback replaces whitespace with underscores, which handles any new response values added in the future. The function is applied immediately after the SpeechRecognition result is received, before the value is placed in the input field.

**The Lesson.** Natural language interfaces require a translation layer between what humans say and what formal systems expect. The translation layer should be as permissive as reasonable (accepting many phrasings) while never creating ambiguity between two different valid responses.

---

### Challenge 4 — Session Persistence

**The Problem.** In-memory sessions are lost when the backend process stops. For a training session that might take 20-30 minutes, a crash or accidental restart would lose all student progress and require starting over. The challenge was not just saving sessions — it was ensuring the FSM state (current state + full history) could be perfectly reconstructed, and that auto-start timers would restart correctly after recovery.

**The Solution.** `FSMEngine.serialize()` converts the full `SimulationState` (including the complete `event_history` list as Pydantic models) to JSON. This is written to the `sessions` table via `upsert_session()` on every transition. On startup, `_restore_sessions()` reads all running sessions, calls `FSMEngine.deserialize(scenario, data)` to reconstruct the engine, then reinvokes `_schedule_auto_start_timers()` for the restored state so timers restart. The only documented tradeoff is that timers restart from full duration — elapsed time is not tracked.

**The Lesson.** Persistence for stateful systems requires that the state be fully serialisable and deserialisable. All state — including history — must be captured, not just the current value. And recovery must be tested explicitly, not assumed to work.

---

### Challenge 5 — Self-Transition Persistence Bug

**The Problem.** In `initial_steps`, the student confirms three sequential steps (warm/dry/stimulate, position airway, clear airway). The first two are self-loop transitions — the state ID does not change. The original persistence layer used SQLAlchemy's change-detection: it only wrote to the database when a tracked field changed. Because `current_state_id` did not change on self-loops, the persistence layer detected "no change" and skipped the write. After a crash mid-way through the initial steps, those confirmations were lost — the student had to redo them.

**The Solution.** We changed the persistence layer to call `upsert_session()` unconditionally after every FSM processing call — whether or not the state changed. The key insight was that even though `current_state_id` is the same, `event_history` is always growing (a new event is appended). The complete event history (including self-loop events) must be persisted, not just the current state ID. This required updating the test suite (AT-09, 4 new checks) to verify self-loop persistence explicitly.

**The Lesson.** Change-detection-based persistence is fragile for event-sourced systems. In a system where the authoritative record is the event history (not just the current state), the persistence trigger must be "any new event was recorded" — not "the current state field changed."

---

## PART 7 — FUTURE SCOPE

---

**1. Authentication and Role-Based Access Control**
The JWT infrastructure is scaffolded (secret key, algorithm, token expiry in config) but all routes are currently unprotected. The next step is a `/auth/login` endpoint issuing signed JWT tokens, with FastAPI `Depends` guards on all other routes. Instructors and students would have distinct roles; instructors would be restricted to their assigned sessions only. This is essential before any multi-user deployment.

**2. Multi-User Deployment with Horizontal Scaling**
The current in-memory `SessionManager` is limited to a single backend process. Replacing it with a Redis-backed session store would allow multiple uvicorn worker processes to share session state. Any worker could handle any request for any session. Combined with a load balancer (nginx upstream), the system could serve an entire classroom simultaneously. The FSM engine and persistence layer are already fully serialisable — the main change is the session store backend.

**3. Student Analytics Dashboard**
The CSV export is a raw event log. A structured analytics layer would automatically compute per-student performance metrics: time-to-first-action per state, decision accuracy (correct responses / total responses), number of corrective ventilation cycles triggered, total session duration, and comparison against benchmark times. An instructor dashboard would display these metrics per student and per scenario, enabling objective assessment without manual CSV analysis.

**4. Additional Clinical Scenarios**
The FSM engine is scenario-agnostic — it interprets any valid JSON scenario file. Additional neonatal scenarios can be added without code changes: post-resuscitation stabilisation, oxygen therapy adjustment, preterm infant management. Beyond neonatal care, the engine could support adult CPR (ACLS protocol), paediatric advanced life support (PALS), or other structured emergency protocols. The only requirement is a well-formed scenario JSON.

**5. Elapsed Timer Tracking on Crash Recovery**
Auto-start timers currently restart from full duration after a crash. The fix: record `started_at` timestamp in the persisted session state for each active timer. On restore, compute `remaining = max(0, duration - (now - started_at))` and start the timer from `remaining`. This makes crash recovery transparent to the student — they resume from exactly where they were.

**6. WebSocket Auto-Reconnect**
The current WebSocket client drops silently on disconnect. Adding an exponential backoff reconnection loop in `websocket.ts` (~20 lines) would automatically restore the live event stream after a network interruption — without requiring a browser refresh. This would be invisible to the student and significantly improve demo robustness.

**7. Simulation Replay and Debrief Mode**
The complete event history is stored in SQLite and exportable as CSV. A replay interface would allow an instructor to step through a completed session event by event — showing each student decision, the correct alternative, and the time taken. This post-simulation debrief is where much of the learning in simulation-based training occurs.

**8. Cloud Deployment**
The Docker Compose setup is ready for deployment to any container hosting platform. A production deployment would add HTTPS (TLS via nginx + Let's Encrypt or a cloud load balancer), a managed PostgreSQL instance (replacing SQLite), Redis for session sharing, a CDN for frontend static assets, and a monitoring stack (Prometheus + Grafana) for uptime and performance visibility.

**9. Offline / PWA Mode**
A Progressive Web App service worker could cache the application shell and the current scenario definition locally. The student could continue interacting during brief network outages, with actions queued and synchronised when connectivity restored. This would make the simulator usable in low-connectivity clinical training environments.

**10. Instructor Scenario Builder**
A browser-based scenario editor would allow instructors to create, edit, and validate scenario JSON files without manual text editing. A drag-and-drop state machine editor with form fields for each state's actions, timers, and transitions would make the tool accessible to faculty with no programming background.

---

## PART 8 — FACULTY Q&A DEFENCE

---

**"Why not use a database workflow engine instead of an FSM?"**

Database workflow engines (like Apache Airflow, Camunda, or AWS Step Functions) are designed for long-running, asynchronous business processes — document approval chains, batch jobs, multi-day workflows. They introduce significant operational overhead: a separate service to deploy, a proprietary workflow definition language to learn, and network latency on every state transition.

Our use case is fundamentally different: a synchronous, real-time, sub-second interaction loop where a student inputs a response and the system must react immediately. A custom FSM in Python is six source files, requires no external services, has zero network latency (it runs in the same process as the API server), and can be completely understood and modified by the development team. The clinical workflow is also structurally simple — a directed graph with finite states and explicit transitions — which maps directly and cleanly to an FSM without any of the complexity a workflow engine would add. Simplicity and correctness were the deciding factors.

---

**"Why WebSockets instead of Server-Sent Events (SSE) or long polling?"**

Server-Sent Events (SSE) are unidirectional — server to client only — and over HTTP/1.1 they each consume a separate connection. For our architecture, where multiple clients (student and instructor) connect to the same session room and receive the same broadcast events, WebSockets are more appropriate: one persistent connection per client, bidirectional, and natively supported by FastAPI's Starlette layer. Long polling — where the client makes an HTTP request that the server holds open until an event occurs — adds latency (the time to establish a new connection after each event) and cannot broadcast to multiple clients efficiently. WebSockets provide the lowest latency and the simplest broadcasting model for our multi-client, real-time scenario.

---

**"Why SQLite? Is it reliable enough?"**

SQLite is the most widely deployed database engine in the world, used in browsers, operating systems, mobile applications, and embedded devices. It is not a toy. For our specific use case — a single backend process, one active session at a time during a demo, writes of a few kilobytes every 10-30 seconds — SQLite is not just adequate, it is the optimal choice. Write throughput concerns arise with hundreds of concurrent writers; we have one. Reliability concerns arise in network-exposed, shared-access scenarios; our database is a local file accessed by one process. We explicitly designed the system to switch to PostgreSQL by changing one environment variable for any deployment that requires scale, and we tested with PostgreSQL-compatible SQL throughout. The choice of SQLite for the demo is an engineering decision, not a limitation.

---

**"Why React? Why not a simpler frontend?"**

React was chosen because the student interface has complex real-time state requirements: the current state, selected action, active timer countdown, event log, WebSocket status, and speech recognition state all update independently and must render without full page reloads. A plain HTML + JavaScript implementation would require manual DOM manipulation for each update, increasing the risk of bugs. React's component model and re-render system handle this declaratively. The TypeScript layer adds compile-time type checking — errors like passing the wrong prop type are caught at build time, not during a live demo. Tailwind CSS accelerates UI development. The combination is the industry-standard choice for exactly this type of real-time, stateful browser application.

---

**"How do you guarantee the system behaves correctly during a live demo?"**

Four layers of assurance. First, the 61 automated acceptance tests run against a live backend instance — not mocks — and verify the exact API responses for every step of every major workflow. Second, the failure injection audit tested 15 real-world failure scenarios and found no P0 blockers. Third, the FSM engine's `validate_scenario()` function verifies the scenario file's structural integrity before any session can start — no broken references can reach the running engine. Fourth, the instructor console provides a real-time override capability: if anything unexpected happens during the demo, the instructor can manually advance or override the simulation state without stopping the session. The combination of automated correctness verification plus live human override capability is the appropriate reliability model for a demonstration context.

---

**"How is reliability achieved in a system with so many moving parts?"**

Reliability comes from clear separation of concerns and well-defined failure modes. The FSM engine is pure in-memory logic with no I/O — it cannot fail due to network or database issues, and its logic is fully tested. The persistence layer is asynchronous — a database write failure does not prevent the FSM from operating; it is logged and the in-memory state continues. The WebSocket layer catches all `RuntimeError` and `WebSocketDisconnect` exceptions in `_send_to_connections`, ensuring that a dropped client cannot crash the broadcast to other clients. Every error in the frontend shows a localised error banner — there are no silent failures in the user-visible path. The failure injection audit verified that every identified failure mode either self-recovers, degrades gracefully, or requires a single operator action (refresh, restart) to resolve. No combination of tested failures requires re-deploying or modifying the application.

---

*Document complete.*
*Neonatal Resuscitation Simulator — BIT Mesra MO-2026*
*61/61 acceptance tests passing. Zero P0 failures. Code freeze active.*
