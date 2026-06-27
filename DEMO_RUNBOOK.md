# Demo Runbook — Neonatal Resuscitation Simulator

**Audience:** Presenter / instructor running the demo  
**Time to setup:** ~5 minutes (local) / ~10 minutes (Docker, first build)

---

## Quick Reference

| URL | What |
|-----|------|
| `http://localhost:5173` | Student view |
| `http://localhost:5173/?role=instructor` | Instructor console |
| `http://localhost:8000/health` | Backend health (should return `{"status":"healthy"}`) |
| `http://localhost:8000/docs` | Interactive API docs (Swagger UI) |

---

## 1. Startup Procedure

### Option A — Local (recommended for development)

**Prerequisites:** Python 3.10+, Node 18+, npm 9+

**Step 1 — Backend**

Open a terminal, navigate to the `backend/` directory, and start the server:

```powershell
# Windows PowerShell
cd C:\path\to\neonatal-resuscitation-simulator\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
# macOS / Linux
cd /path/to/neonatal-resuscitation-simulator/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Wait for the line: `Application startup complete.`

Verify: `http://localhost:8000/health` → `{"status":"healthy"}`

**Step 2 — Frontend**

Open a second terminal:

```powershell
cd C:\path\to\neonatal-resuscitation-simulator\frontend
npm install   # first time only
npm run dev
```

Wait for: `VITE ... ready in ... ms`

Open `http://localhost:5173` in your browser.

---

### Option B — Docker (recommended for demo/deployment)

**Prerequisites:** Docker 24+ with Compose V2

```bash
# One-time setup
cp .env.example .env
# Set JWT_SECRET_KEY in .env (any random string)

# Build and start (takes ~3 minutes on first build)
docker compose up --build

# Subsequent starts (no rebuild needed)
docker compose up
```

Both services are ready when you see:
```
backend-1   | Application startup complete.
frontend-1  | ...nginx...
```

Open `http://localhost:5173` (student) and `http://localhost:5173/?role=instructor` (instructor).

**Stop without losing data:**
```bash
docker compose down         # data preserved in nrs_data volume
docker compose down -v      # data permanently deleted
```

---

## 2. Demo Sequence

### 2A — Student Happy Path (~5 minutes)

> Show the student view to the audience first.

1. Open `http://localhost:5173`
2. Click **Select Scenario** → choose "Baby Birth Neonatal Resuscitation Workflow"
3. Click **Start Session**
4. Walk through each prompt in order, answering "yes" to each clinical action:
   - Confirm birth
   - Place on mother's chest
   - Warm, dry, stimulate (note: stays on same screen — self-loop)
   - Position airway (self-loop)
   - Clear airway if needed
   - Assess: baby not crying → describe breathing → assess heart rate → HR < 100
   - Start ventilation → apply pulse oximeter
   - Confirm effective ventilation → SPO2 acceptable
   - Continue observation → **Simulation complete**

**Talking points:**
- The simulator tracks every step in real time
- Each action is recorded with a timestamp (show CSV export at the end)
- Self-loop steps (warm/dry, position airway) confirm the student did the action — the FSM records it even without a state change

---

### 2B — Instructor Override (~3 minutes)

> Show the instructor console to the audience.

1. Open `http://localhost:5173/?role=instructor` in a separate window
2. A session started on the student view will appear in the session dropdown (auto-refreshes every 5 seconds)
3. Select the session
4. Demonstrate instructor buttons:
   - **Fast-forward**: press instructor event buttons to skip ahead
   - **Timer override**: press a timer button to fire a timer immediately (e.g. "Ventilation Timer Complete")
   - **Export CSV**: download the full event log

**Talking points:**
- Instructor can intervene at any point without the student knowing
- All instructor actions are also recorded in the event log

---

### 2C — Advanced Resuscitation Path (~3 minutes)

> Demonstrate the HR < 60 branch.

From the instructor console (or manually advance to `heart_rate_after_ventilation`):

1. Press **Heart Rate Under 60** → jumps to `advanced_resuscitation`
2. Student actions available: start chest compressions, prepare epinephrine, establish vascular access (all self-loops — keep student in the state until resolved)
3. Press **Advanced Resuscitation Complete** → `simulation_complete`

---

### 2D — Persistence Demo (~2 minutes)

> Show crash recovery.

1. Start a new session, advance 3-4 steps
2. Kill the backend (`Ctrl+C` in the backend terminal, or `docker compose restart backend`)
3. Restart the backend
4. Reload `http://localhost:5173/?role=instructor`
5. The session is back — same state, full history

**Talking points:**
- Sessions survive crashes because every transition is saved to SQLite
- The FSM state (current state + full event history) is serialized as JSON in the database

---

### 2E — CSV Export (~1 minute)

From the instructor console, click **Export CSV**. Open in Excel or a text editor.

Columns: `timestamp`, `session_id`, `event_type`, `state_id`, `action_id`, `response`, `transition_id`, `target_state_id`, `details`

Each row is one event: session start, student input, timer fire, instructor action, or state transition.

---

## 3. Recovery Procedures

### Backend fails to start

**Symptom:** `pydantic_settings` error, missing `.env`, or `MODULE_NOT_FOUND`

```bash
# 1. Ensure backend/.env exists
cp .env.example backend/.env

# 2. Ensure you are starting from inside backend/
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Symptom:** `DATABASE_URL` not set — you are in the wrong directory. The `.env` file must be read from `backend/`.

---

### Frontend shows blank page or "Cannot connect to backend"

1. Confirm backend is running: `http://localhost:8000/health`
2. Check browser console for CORS errors
3. Confirm `ALLOWED_ORIGINS` in `backend/.env` includes `http://localhost:5173`

---

### Session list is empty

- Sessions in `stopped` status are not shown or restored — this is correct behaviour
- If the database was deleted or the backend restarted from a different directory, old sessions are gone
- Start a new session from the student view

---

### Timer does not fire automatically

Auto-start timers run in the background. In development, timers may be very long (e.g. 30 seconds for ventilation). You can fire them immediately from the instructor console using the timer buttons.

---

### Docker: frontend shows "502 Bad Gateway"

The backend container is still starting up. The frontend waits for the backend health check to pass (up to ~40 seconds). If it persists:

```bash
docker compose logs backend
```

Look for errors in the backend log. The most common cause is a missing `JWT_SECRET_KEY` in `.env`.

---

### Docker: "invalid interpolation format" error on docker compose up

You have not set `JWT_SECRET_KEY` in `.env`. Edit `.env` and add:
```
JWT_SECRET_KEY=any-random-string-here
```

---

## 4. Troubleshooting Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| `uvicorn: command not found` | venv not activated or wrong Python | `pip install -r requirements.txt` in `backend/` |
| `ModuleNotFoundError: app` | Not in `backend/` directory | `cd backend` before running uvicorn |
| Scenarios not loading | Wrong `SCENARIOS_DIR` or wrong CWD | Start uvicorn from `backend/` directory |
| CSV opens garbled in Excel | Encoding issue | Use Data → From Text/CSV in Excel, select UTF-8 |
| Sessions not restoring after restart | Stopped sessions are not restored | Only `running` sessions are restored |
| Port already in use | Previous server still running | Kill the process: `lsof -i :8000` (macOS/Linux) or `netstat -ano` (Windows) |

---

## 5. Architecture at a Glance

```
Student browser                     Instructor browser
      |                                      |
      |  HTTP + WebSocket                    |  HTTP + WebSocket
      |                                      |
      +----------------+  FastAPI  +---------+
                       |           |
                  uvicorn (port 8000)
                       |
                  FSMEngine (in-memory)
                  SQLite (neonatal.db)     <- sessions persisted here
                  scenarios/*.json         <- clinical scenario definitions
```

- **FSM state** is saved on every successful transition (including self-loops)
- **Event history** is the complete audit trail, exported as CSV
- **WebSocket** pushes every state change to both views in real time
- **Timers** are asyncio tasks — recreated from full duration on server restart

---

## 6. File Locations

| File | Purpose |
|------|---------|
| `backend/neonatal.db` | SQLite database (created automatically on first run) |
| `scenarios/baby_birth.json` | Clinical scenario definition (17 states) |
| `backend/.env` | Local environment variables |
| `.env` | Docker environment variables |
| `backend/tests/` | Automated test suite (41 tests) |
| `DEMO_RUNBOOK.md` | This file — demo procedures and recovery scripts |
