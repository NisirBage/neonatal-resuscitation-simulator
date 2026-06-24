# Neonatal Resuscitation Simulator

A web-based clinical training simulator for neonatal resuscitation. An instructor controls a scenario from a dedicated console; students interact with the simulation in real time through a browser interface backed by a finite-state machine (FSM) engine.

---

## Architecture

```
browser (student)      browser (instructor)
      │                        │
      └──────── HTTP + WebSocket ──────────┘
                        │
               FastAPI (Python)
                   uvicorn
                        │
               SQLite (aiosqlite)       ← session persistence
               scenarios/*.json         ← clinical scenario definitions
```

- **Backend:** FastAPI + SQLAlchemy + aiosqlite, Python 3.10+
- **Frontend:** React 19 + TypeScript + Tailwind CSS, built with Vite
- **Persistence:** SQLite by default; PostgreSQL supported via environment variable

---

## Prerequisites

| Tool | Minimum version | Check |
|------|----------------|-------|
| Python | 3.10 | `python --version` |
| pip | 22+ | `pip --version` |
| Node.js | 18 | `node --version` |
| npm | 9 | `npm --version` |

No Docker is required for local development.

---

## Docker (recommended for demo and deployment)

### Prerequisites

- Docker 24+ with Compose V2 (`docker compose` — not `docker-compose`)

### Quickstart

```bash
# 1. Create the env file
cp .env.example .env

# 2. Set a real secret key (required)
# Linux/macOS:
echo "JWT_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> .env
# Windows PowerShell:
# Add-Content .env "JWT_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')"

# 3. Build and start
docker compose up --build
```

| URL | What |
|-----|------|
| `http://localhost:5173` | Student view |
| `http://localhost:5173/?role=instructor` | Instructor console |
| `http://localhost:8000/health` | Backend health check |
| `http://localhost:8000/docs` | Interactive API docs |

### Persistence

SQLite data is stored in a Docker named volume (`nrs_data`) at `/app/data/neonatal.db` inside the backend container. Sessions survive container restarts and image rebuilds. Data is only deleted if you explicitly remove the volume:

```bash
docker compose down -v   # removes containers AND volume (data lost)
docker compose down      # removes containers only (data preserved)
```

### Custom backend host/port

If the backend is reachable from a different address (e.g. a remote server), set the frontend build args before building:

```bash
VITE_API_BASE_URL=http://myserver.example.com:8000 \
VITE_WS_BASE_URL=ws://myserver.example.com:8000 \
docker compose up --build
```

Or add them to `.env`:
```
VITE_API_BASE_URL=http://myserver.example.com:8000
VITE_WS_BASE_URL=ws://myserver.example.com:8000
```

---

## Backend Setup

### 1. Create and activate a virtual environment

```bash
cd backend
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
# From the repo root
cp .env.example backend/.env
```

Open `backend/.env` and set at minimum:

```
JWT_SECRET_KEY=<random string>   # run: python -c "import secrets; print(secrets.token_hex(32))"
ALLOWED_ORIGINS=["http://localhost:5173"]
```

The default `DATABASE_URL` uses SQLite and requires no further setup.

### 4. Start the backend

```bash
# Must be run from inside the backend/ directory
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`.
Interactive docs: `http://127.0.0.1:8000/docs`.
Health check: `http://127.0.0.1:8000/health`.

> **Important:** uvicorn must be started from the `backend/` directory. The SQLite
> database file (`neonatal.db`) and the scenario path resolution both depend on this
> working directory.

---

## Frontend Setup

### 1. Install dependencies

```bash
cd frontend
npm install
```

### 2. Start the development server

```bash
npm run dev
```

The frontend is available at `http://localhost:5173`.

> The frontend connects to the backend at `http://localhost:8000` by default.
> If your backend runs on a different address, set `VITE_API_BASE_URL` and
> `VITE_WS_BASE_URL` before running `npm run dev` or `npm run build` (see
> [Environment Variables](#environment-variables) below).

---

## Interfaces

### Student view

Open `http://localhost:5173` in a browser. Select a scenario, start a session, and work through the clinical steps.

### Instructor console

Open `http://localhost:5173/?role=instructor` in a separate browser window or tab.

The instructor console provides:
- Live session selector (polls every 5 seconds)
- Current FSM state display with all available instructor override buttons
- Real-time event feed via WebSocket
- Manual timer triggers
- CSV export of the full session event log
- Stop session control

---

## CSV Export

A session's complete event history can be exported to CSV at any time while the session is running.

**Via the instructor console:** click **Export CSV** in the header.

**Via the API directly:**
```
GET /api/sessions/sessions/{session_id}/export/csv
```

The CSV contains 9 columns: `timestamp`, `session_id`, `event_type`, `state_id`, `action_id`, `response`, `transition_id`, `target_state_id`, `details`.

The file is UTF-8 with BOM for Excel compatibility.

---

## Persistence

Sessions survive backend restarts. When the backend starts, it automatically restores all sessions that were in `running` status at shutdown or crash time.

- FSM state (current state, full event history) is saved to SQLite on every successful transition.
- Self-loop transitions (e.g. warm/dry/stimulate in `initial_steps`) are also persisted.
- Auto-start timers are recreated from their full duration on restore — elapsed time before a crash is not tracked.
- Stopped sessions are not restored.

The SQLite database file is created automatically at `backend/neonatal.db` on first startup. No migration commands are needed.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | SQLite: `sqlite+aiosqlite:///./neonatal.db` · PostgreSQL: `postgresql+asyncpg://user:pass@host/db` |
| `JWT_SECRET_KEY` | Yes | — | Random secret string. Not currently enforced on routes but must be set. |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | JWT token lifetime in minutes. |
| `DEBUG` | No | `false` | Enables FastAPI debug mode and verbose errors. Set `true` for development only. |
| `ALLOWED_ORIGINS` | Yes | — | JSON array or comma-separated list of frontend origins. Must include the address where the frontend runs. |
| `APP_NAME` | No | `Neonatal Resuscitation Simulator` | Application name shown in logs. |

### Frontend (set before `npm run build` or `npm run dev`)

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Base URL for all REST API calls. |
| `VITE_WS_BASE_URL` | `ws://localhost:8000` | Base URL for WebSocket connections. |

> These are Vite **build-time** variables. They are baked into the compiled JS bundle.
> Changing them after a build has no effect — rebuild the frontend after changing them.

---

## Scenarios

Scenario definitions live in `scenarios/*.json`. The backend loads them from disk on every request — no restart is needed to pick up a new or edited scenario file.

The active scenario is `baby_birth.json`, which models a 17-state neonatal resuscitation workflow.

To add a new scenario: drop a valid JSON file into `scenarios/` and restart the backend (or just make a request — scenarios are loaded on demand).

---

## Troubleshooting

### Backend fails to start — `pydantic_settings` error or missing `.env`

`backend/.env` must exist. Copy it from the example:
```bash
cp .env.example backend/.env
```

### Backend fails to start — `ModuleNotFoundError`

The virtual environment is not activated, or dependencies were not installed:
```bash
cd backend
pip install -r requirements.txt
```

### Backend fails to start — `DATABASE_URL` missing

`backend/.env` must contain a `DATABASE_URL` line. The file must be read from inside `backend/` — if uvicorn is started from the repo root, it reads the root `.env` (which targets PostgreSQL and requires a running PostgreSQL server).

Always start uvicorn from inside `backend/`:
```bash
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend shows no scenarios or sessions

Confirm the backend is running and `ALLOWED_ORIGINS` in `backend/.env` includes `http://localhost:5173`. CORS errors appear in the browser console.

### Session list is empty after backend restart

Sessions in `stopped` state are not restored — this is correct. Only `running` sessions are restored on startup.

If the SQLite database file was deleted (or the backend was started from a different directory), no sessions exist to restore.

### CSV export file opens with garbled characters in Excel

The file is UTF-8 with BOM. Open via **Data → From Text/CSV** in Excel and select UTF-8 encoding, or use the file directly — Excel should detect the BOM automatically on Windows.

### `VITE_WS_BASE_URL` not taking effect

Vite environment variables are baked in at build time. After changing them, run:
```bash
npm run build   # for production
# or restart dev server:
npm run dev
```

### `warm_dry_stimulate` step lost after backend crash

This was fixed — all self-loop transitions (including warm/dry/stimulate, position airway, reposition mask, chest compressions) are now persisted on every successful transition, not only on state changes.

---

## Project Structure

```
neonatal-resuscitation-simulator/
├── backend/
│   ├── app/
│   │   ├── fsm.py               FSM engine (state machine core)
│   │   ├── scenario.py          Scenario schema and loader
│   │   ├── scenario_runner.py   Orchestrates FSM + timers + events
│   │   ├── session_service.py   In-memory session store
│   │   ├── events.py            EventBus (pub/sub)
│   │   ├── ws_manager.py        WebSocket session rooms
│   │   ├── database.py          SQLAlchemy async engine
│   │   ├── config.py            pydantic-settings config
│   │   ├── main.py              FastAPI app, startup/shutdown
│   │   ├── models/              ORM models (PersistedSession)
│   │   ├── routers/
│   │   │   ├── sessions.py      Session CRUD + input endpoints
│   │   │   ├── scenarios.py     Scenario list/validate endpoints
│   │   │   └── ws.py            WebSocket endpoint
│   │   └── services/
│   │       ├── session_service.py   DB persistence (upsert/load/stop)
│   │       └── export_service.py   CSV export
│   ├── requirements.txt
│   └── neonatal.db              Created automatically on first run
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── StudentDashboard.tsx
│   │   │   └── InstructorDashboard.tsx
│   │   ├── components/          Shared UI components
│   │   ├── services/
│   │   │   ├── api.ts           REST API client
│   │   │   └── websocket.ts     WebSocket factory
│   │   └── App.tsx              Role-based routing (?role=instructor)
│   └── package.json
├── scenarios/
│   └── baby_birth.json          Clinical scenario definition (17 states)
├── terminals/                   Manual regression test scripts
├── .env.example                 Environment variable template
└── README.md
```
