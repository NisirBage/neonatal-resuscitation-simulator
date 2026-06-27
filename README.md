<div align="center">

# 🩺 Neonatal Resuscitation Simulator

**A voice-first, scenario-driven clinical training platform for neonatal resuscitation.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.137-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![CI](https://img.shields.io/github/actions/workflow/status/NisirBage/neonatal-resuscitation-simulator/ci.yml?label=CI&logo=github-actions&logoColor=white)](https://github.com/NisirBage/neonatal-resuscitation-simulator/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Live Demo](#demo) · [Quick Start](#quick-start--local-development) · [API Docs](#api-reference) · [Roadmap](ROADMAP.md)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Motivation & Problem Statement](#motivation--problem-statement)
- [Clinical Background](#clinical-background)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Feature Highlights](#feature-highlights)
- [Voice Workflow](#voice-workflow)
- [Instructor Dashboard](#instructor-dashboard)
- [Session Replay](#session-replay)
- [Metrics & Scoring](#metrics--scoring)
- [Reporting & Export](#reporting--export)
- [Screenshots](#screenshots)
- [Demo](#demo)
- [Quick Start — Local Development](#quick-start--local-development)
- [Docker Compose](#docker-compose)
- [Production Deployment](#production-deployment)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Overview

The Neonatal Resuscitation Simulator is a full-stack web application that enables medical educators to
guide student clinicians through the NRP (Neonatal Resuscitation Program) protocol using real-time
voice interaction. The student speaks their responses aloud; the system transcribes, normalises, and
validates each answer against the protocol definition before advancing the simulation.

The instructor observes the live FSM state, can override transitions, trigger timers manually, and
export four formats of clinical report — all in the same browser session, without any additional
software.

> **Academic context:** Built as a final-year software engineering capstone project demonstrating
> full-stack development, event sourcing, finite state machines, real-time WebSocket communication,
> and clinical workflow design.

---

## Motivation & Problem Statement

Clinical simulation training is a well-established method for developing procedural competency
without risk to real patients. Existing simulation platforms are often expensive, hardware-dependent
(requiring physical manikins), or lack structured digital record-keeping for performance review.

This simulator addresses three specific gaps:

1. **Accessibility** — runs entirely in a web browser; no proprietary hardware or software licences required.
2. **Structured protocol enforcement** — the FSM engine guarantees that every step of the NRP protocol is
   presented in order and that no transition is skipped or repeated incorrectly.
3. **Automated reporting** — every session produces an audit-quality clinical timeline automatically,
   eliminating the need for manual note-taking by the instructor during high-cognitive-load simulations.

---

## Clinical Background

The **Neonatal Resuscitation Program (NRP)** is the internationally recognised standard of care for
resuscitation of newborns. The protocol consists of a structured decision tree executed within the
first minutes after birth:

1. Confirm birth and assess initial status
2. Provide warmth, dry, and stimulate
3. Position and clear the airway if needed
4. Assess breathing, tone, and heart rate
5. Initiate positive-pressure ventilation if indicated
6. Apply pulse oximeter; confirm effective ventilation
7. Escalate to chest compressions and epinephrine if heart rate remains < 60 bpm

This simulator models steps 1–7 as a JSON-defined finite state machine, making the clinical logic
transparent, auditable, and easily extensible to additional scenarios.

> **Disclaimer:** This is a training tool. It is not validated for clinical use and must not replace
> formal NRP certification.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Browser (Student)                   │
│  React SPA + Web Speech API (TTS + STT)              │
│                     │  WebSocket (wss://)             │
└─────────────────────┼───────────────────────────────┘
                      │
┌─────────────────────┼───────────────────────────────┐
│               Browser (Instructor)                   │
│  React SPA          │  WebSocket (wss://)             │
└─────────────────────┼───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│          FastAPI Backend  (Python 3.10)              │
│                                                      │
│  REST API /api/*   WebSocket Manager   EventBus      │
│         └──────────────┬──────────────────┘          │
│              ScenarioRunner + FSMEngine              │
│         (thread-safe · serialisable · event-sourced) │
│                        │                             │
│      SQLAlchemy async ─┴─ SQLite / PostgreSQL        │
└─────────────────────────────────────────────────────┘

Deployment:
  Backend  → Railway  (Docker, /health check, auto-restart)
  Frontend → Vercel   (Vite SPA, SPA rewrite, auto-deploy)
  CI/CD    → GitHub Actions (5-job pipeline)
```

### Key Design Patterns

| Pattern | File | Why |
|---------|------|-----|
| **Finite State Machine** | `backend/app/fsm.py` | All scenario logic lives in JSON; the engine enforces valid transitions with no hardcoded clinical rules |
| **Event Sourcing** | `backend/app/models.py` | Every state change is an immutable `SimulationEvent`; replay, metrics, and all four export formats derive from this single log |
| **Pub/Sub (EventBus)** | `backend/app/events.py` | Decouples the FSM from WebSocket broadcasting; each subscriber (broadcaster, timer scheduler, persistence) operates independently |
| **Repository** | `backend/app/services/session_service.py` | Isolates database access; swapping SQLite for PostgreSQL requires one env var change |
| **Exponential Backoff** | `frontend/src/services/websocket.ts` | Automatic WebSocket reconnect — `min(1000 × 2ⁿ, 30000)` ms — survives network blips without user intervention |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend language | Python 3.10 |
| Backend framework | FastAPI 0.137 |
| Async ORM | SQLAlchemy 2.x (async) + aiosqlite |
| Database | SQLite (default) · PostgreSQL (via asyncpg) |
| Frontend framework | React 18 + TypeScript 5 |
| Build tool | Vite 5 |
| CSS | Tailwind CSS |
| Voice | Web Speech API (SpeechSynthesis + SpeechRecognition) |
| Real-time | Native WebSocket (no Socket.IO) |
| PDF generation | ReportLab |
| Excel generation | openpyxl |
| Containerisation | Docker + Docker Compose |
| Backend deployment | Railway (Docker builder, auto-deploy) |
| Frontend deployment | Vercel (Vite, SPA rewrite) |
| CI/CD | GitHub Actions |
| Testing | pytest + Starlette TestClient (httpx) |

---

## Feature Highlights

### Student View
- **Voice-first workflow** — simulator speaks each NRP prompt; student answers aloud
- **Continuous speech recognition** — microphone stays active; silence auto-restarts recognition
- **Natural language normalisation** — "yeah", "yep", "sure" → yes; "nope", "no way" → no
- **Manual YES / NO buttons** — full fallback when microphone is unavailable or denied
- **Live birth timer** — elapsed clock from session start with per-minute voice announcements
- **Ventilation countdown** — animated progress bar for time-critical ventilation steps
- **Reconnecting banner** — amber status badge and auto-sync after WebSocket reconnect
- **Friendly error messages** — contextual messages for network failures, expired sessions, server errors

### Instructor Dashboard
- **Live session list** — polls every 5 s for active sessions
- **Real-time state display** — WebSocket-pushed FSM state with active timer
- **Override panel** — force any instructor-defined state transition without student input
- **Manual timer controls** — trigger any timer immediately (useful for demonstrations)
- **Live event log** — last 40 events with type, timestamp, and payload
- **Export controls** — one-click access to all four report formats

### Infrastructure
- **Automatic session recovery** — restores all running sessions from the database on backend restart
- **Health endpoint** (`GET /health`) — checks database connectivity and scenario availability; HTTP 503 if degraded
- **Version endpoint** (`GET /version`) — git commit SHA, build timestamp, Python version
- **Structured JSON logging** — machine-readable log format throughout the backend
- **Pre-flight startup checks** — validates scenario directory and JSON integrity before accepting traffic

---

## Voice Workflow

```
Backend speaks prompt ──► Browser TTS (Web Speech API SpeechSynthesis)
                                  │
                         Student hears prompt
                                  │
                    Student responds verbally ("yes" / "no")
                                  │
                    SpeechRecognition API transcribes
                                  │
                    Normalisation: "yeah" → "yes", "nope" → "no"
                                  │
                    POST /api/sessions/{id}/input
                                  │
                    FSMEngine evaluates transition
                         ┌────────┴────────┐
                    valid transition    invalid / no match
                         │                    │
                   new state saved       same state, retry
                         │
                  WebSocket broadcast → both views update
                         │
                  Backend speaks next prompt ──► loop
```

If microphone access is unavailable, the student uses the YES / NO buttons. The simulation is
fully functional either way — voice is an enhancement, not a dependency.

---

## Instructor Dashboard

The instructor view opens at `/?role=instructor`. It connects to the same backend over a
separate WebSocket channel (`/api/ws/sessions/{id}/instructor`) and receives every FSM event
in real time.

Key capabilities:

| Action | How |
|--------|-----|
| Select a session | Dropdown polled every 5 s; shows active sessions only |
| View current FSM state | Live push from backend — no manual refresh |
| Force a state transition | Buttons generated from `instructor_transitions` in the scenario JSON |
| Fire a timer | Buttons generated from `timers` in the scenario JSON |
| Download CSV | Raw event log, one row per event |
| Download Clinical CSV | Second-by-second clinical narrative |
| Download Clinical XLSX | Colour-coded Excel workbook |
| Download PDF | ReportLab performance report |

---

## Session Replay

After a session ends, the student view switches to replay mode. The full event history is
loaded from `GET /api/sessions/{id}/replay` and rendered as a step-through timeline.

Controls:
- **← Prev** — step back one event
- **▶ Play** — auto-advance every 1.5 s
- **Next →** — step forward one event

Each event card shows:
- Event type (colour-coded badge)
- Timestamp and elapsed time from session start
- State name before and after the transition
- Student response or instructor action (where applicable)

---

## Metrics & Scoring

Performance metrics are computed in a single O(N) pass over the event log by `metrics_service.py`.

| Metric | Description |
|--------|-------------|
| Training score | Percentage of protocol steps completed correctly on the first attempt |
| Steps completed | Count of distinct FSM states reached |
| Steps correct | Steps where the student answered correctly without an instructor override |
| Total session time | Elapsed time from `session_start` to `session_end` event |
| Ventilation time | Duration spent in ventilation-related states |
| Response times | Per-step time from prompt delivery to student input |

---

## Reporting & Export

All four formats are generated on demand from the immutable event log. No data is pre-aggregated.

| Format | Endpoint | Description |
|--------|----------|-------------|
| PDF performance report | `GET /api/sessions/{id}/report/pdf` | ReportLab PDF: score, metrics table, full event timeline |
| Raw event CSV | `GET /api/sessions/{id}/export/csv` | Every FSM event with timestamps and payloads (UTF-8 BOM for Excel compatibility) |
| Clinical timeline CSV | `GET /api/sessions/{id}/export/clinical-csv` | Second-by-second, clinical language, suitable for instructor debrief |
| Clinical timeline XLSX | `GET /api/sessions/{id}/export/clinical-xlsx` | Colour-coded Excel workbook with clinical phase column and training score |

### Clinical Timeline XLSX Columns

| Column | Content |
|--------|---------|
| Time (s) | Seconds from session start |
| Timestamp | ISO 8601 wall-clock time |
| Clinical Phase | NRP phase label (Initial Assessment, Airway Management, Ventilation, etc.) |
| Event | Clinical narrative description |
| State | FSM state ID |
| Training Score | Filled in the summary row only |

---

## Screenshots

> Screenshots will be added following the first public demo. See [`docs/screenshots/README.md`](docs/screenshots/README.md) for capture instructions.

| View | Description |
|------|-------------|
| ![Student Dashboard](docs/screenshots/student-dashboard.png) | Voice prompt display, YES/NO controls, birth timer, ventilation bar |
| ![Instructor Dashboard](docs/screenshots/instructor-dashboard.png) | Live FSM state, override panel, event log, timer controls |
| ![Session Replay](docs/screenshots/session-replay.png) | Step-through timeline with colour-coded event badges |
| ![Performance Metrics](docs/screenshots/performance-metrics.png) | Training score and metric breakdown |
| ![PDF Report](docs/screenshots/pdf-report.png) | ReportLab PDF with score, metrics, and event timeline |
| ![Clinical Timeline XLSX](docs/screenshots/clinical-xlsx.png) | Colour-coded Excel workbook |

---

## Demo

> **Video demonstration:** A recorded walkthrough of the complete NRP simulation will be linked here following the first public demonstration.

### Live Demo

| URL | Description |
|-----|-------------|
| Production backend | Deployed on Railway — see environment setup |
| Production frontend | Deployed on Vercel — see environment setup |

### Running a Demo Locally

See [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) for the complete demo script including:
- Student happy path (~5 minutes)
- Instructor override demonstration (~3 minutes)
- Advanced resuscitation branch (~3 minutes)
- Persistence / crash recovery demo (~2 minutes)
- Export walkthrough (~1 minute)
- Recovery procedures for every failure mode

---

## Quick Start — Local Development

**Prerequisites:** Python 3.10+, Node.js 18+, Git

```bash
git clone https://github.com/NisirBage/neonatal-resuscitation-simulator.git
cd neonatal-resuscitation-simulator
```

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Configure environment
cp ../.env.local.example ../.env
# Edit .env — set JWT_SECRET_KEY to any random string

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify the backend is healthy:

```
GET http://127.0.0.1:8000/health  →  {"status": "healthy", ...}
```

Interactive API docs: http://127.0.0.1:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

| URL | View |
|-----|------|
| http://localhost:5173 | Student Dashboard |
| http://localhost:5173/?role=instructor | Instructor Dashboard |

> **Note:** Voice recognition requires HTTPS on non-localhost origins. Local development on
> `localhost` works without HTTPS in Chrome and Edge.

---

## Docker Compose

```bash
# One-time setup
cp .env.local.example .env
# Edit .env — set JWT_SECRET_KEY to any random string

# Build and start (~3 minutes on first build)
docker compose up --build

# Subsequent starts
docker compose up
```

| URL | Description |
|-----|-------------|
| http://localhost:5173 | Student view |
| http://localhost:5173/?role=instructor | Instructor view |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | Health check |

The SQLite database is stored in a named Docker volume (`nrs_data`) and persists across
container restarts and rebuilds. To reset: `docker compose down -v`.

---

## Production Deployment

### Railway (Backend)

1. Push the repository to GitHub.
2. **New Project → Deploy from GitHub repo** at [railway.app](https://railway.app).
3. Railway reads `railway.toml` automatically (Dockerfile builder, `/health` health check, restart policy).
4. **Settings → Volumes** — attach a volume at `/app/data` for SQLite persistence across deploys.
5. Set all required **environment variables** in the Railway dashboard (see table below).
6. Enable **auto-deploy on push to `main`**.
7. Copy the Railway HTTPS URL for the Vercel step.

### Vercel (Frontend)

1. **Import repo** at [vercel.com/new](https://vercel.com/new).
2. Set **Root Directory** = `frontend`. Framework: Vite (auto-detected).
3. **Environment Variables → Production:**
   - `VITE_API_BASE_URL` = `https://your-backend.up.railway.app`
   - `VITE_WS_BASE_URL` = `wss://your-backend.up.railway.app`
4. Deploy, then add the Vercel URL to Railway's `ALLOWED_ORIGINS`.

### GitHub Actions CI

| Job | Validates |
|-----|-----------|
| `backend-tests` | All pytest tests pass |
| `typescript-check` | Zero TypeScript errors |
| `backend-docker-build` | Production Dockerfile builds |
| `frontend-docker-build` | Multi-stage frontend Dockerfile builds |
| `frontend-build` | Vite production bundle builds without errors |

### Production Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Voice recognition not working | Requires HTTPS | Ensure the Vercel URL uses `https://` |
| WebSocket fails | `wss://` vs `ws://` mismatch | Set `VITE_WS_BASE_URL=wss://…` (not `ws://`) |
| CORS error in browser | `ALLOWED_ORIGINS` missing frontend URL | Add exact Vercel URL to `ALLOWED_ORIGINS` |
| Sessions lost after restart | No Railway volume | Attach a volume at `/app/data` in Railway settings |
| Backend health check fails on Railway | `PORT` not resolved | Do not override `PORT` — Railway injects it automatically |
| 502 Bad Gateway (Docker) | Backend still starting | Wait ~40 s; check `docker compose logs backend` |

---

## Environment Variables

### Backend (`.env`)

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `sqlite+aiosqlite:////app/data/neonatal.db` | SQLite or `postgresql+asyncpg://...` |
| `JWT_SECRET_KEY` | Yes | *(64 random hex chars)* | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ALLOWED_ORIGINS` | Yes | `["https://app.vercel.app"]` | JSON array of allowed CORS origins |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Token lifetime |
| `DEBUG` | No | `false` | Must be `false` in production |
| `SCENARIOS_DIR` | No | `/app/scenarios` | Path to scenario JSON files |
| `PORT` | Auto | — | Injected by Railway — **do not set manually** |

### Frontend (Vercel environment variables)

| Variable | Example | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `https://nrs.up.railway.app` | Backend REST base URL (baked at build time) |
| `VITE_WS_BASE_URL` | `wss://nrs.up.railway.app` | Backend WebSocket base URL (baked at build time) |

---

## API Reference

Interactive Swagger UI is available at `GET /docs`.

### Endpoints

| Method | Path | Summary |
|--------|------|---------|
| `GET` | `/health` | Database + scenario health check (200 / 503) |
| `GET` | `/version` | Build metadata: version, git commit, Python version |
| `GET` | `/` | Root — application name and version |
| `POST` | `/api/sessions/sessions/start` | Start a simulation session for a given scenario |
| `GET` | `/api/sessions/sessions` | List all active sessions |
| `GET` | `/api/sessions/sessions/{id}` | Current FSM state + full event history |
| `POST` | `/api/sessions/sessions/{id}/input` | Submit a student YES/NO response |
| `POST` | `/api/sessions/sessions/{id}/timer/{timer_id}` | Manually fire a named timer |
| `POST` | `/api/sessions/sessions/{id}/instructor` | Send an instructor override event |
| `POST` | `/api/sessions/sessions/{id}/stop` | Stop the session |
| `GET` | `/api/sessions/sessions/{id}/metrics` | Performance metrics and training score |
| `GET` | `/api/sessions/sessions/{id}/replay` | Full event history for replay |
| `GET` | `/api/sessions/sessions/{id}/report/pdf` | Download PDF performance report |
| `GET` | `/api/sessions/sessions/{id}/export/csv` | Download raw event log CSV |
| `GET` | `/api/sessions/sessions/{id}/export/clinical-csv` | Download clinical timeline CSV |
| `GET` | `/api/sessions/sessions/{id}/export/clinical-xlsx` | Download clinical timeline XLSX |
| `GET` | `/api/scenarios/scenarios` | List all available scenarios |
| `GET` | `/api/scenarios/scenarios/{id}` | Get a single scenario definition |
| `WS` | `/api/ws/sessions/{id}/student` | Student real-time event stream |
| `WS` | `/api/ws/sessions/{id}/instructor` | Instructor real-time event stream |

---

## Project Structure

```
neonatal-resuscitation-simulator/
│
├── backend/
│   ├── app/
│   │   ├── main.py                 # App factory, startup/shutdown, /health, /version
│   │   ├── config.py               # Pydantic Settings (env vars, fail-fast validation)
│   │   ├── database.py             # SQLAlchemy async engine + session factory
│   │   ├── models.py               # ORM models (Session, SimulationEvent)
│   │   ├── scenario.py             # Scenario schema + loader + validator
│   │   ├── scenario_runner.py      # Session lifecycle orchestrator + timer scheduling
│   │   ├── fsm.py                  # Finite state machine engine (thread-safe)
│   │   ├── events.py               # Pub/sub EventBus
│   │   ├── session_service.py      # In-memory SessionManager
│   │   ├── ws_manager.py           # WebSocket connection manager
│   │   ├── recovery_service.py     # Checkpoint-based session recovery
│   │   ├── audio_service.py        # Whisper transcription (future use)
│   │   ├── startup_validation.py   # Pre-flight scenario directory checks
│   │   ├── routers/
│   │   │   ├── sessions.py         # All session REST + export endpoints
│   │   │   ├── scenarios.py        # Scenario list / validate / load
│   │   │   └── ws.py               # WebSocket endpoint
│   │   └── services/
│   │       ├── session_service.py  # DB persistence layer
│   │       ├── metrics_service.py  # O(N) metrics computation
│   │       ├── report_service.py   # ReportLab PDF generation
│   │       ├── export_service.py   # Raw CSV export
│   │       └── clinical_timeline_service.py  # CSV + XLSX clinical timeline
│   ├── tests/
│   │   ├── test_clinical_timeline_service.py   # 20 tests — CSV + XLSX generation
│   │   └── test_infrastructure.py              # 21 tests — /health, /version, startup
│   ├── Dockerfile                  # Multi-stage build; non-root user (uid 1001)
│   ├── requirements.txt
│   └── requirements-dev.txt        # pytest, httpx
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # Role-based routing (?role=instructor)
│   │   ├── types.ts                # Shared TypeScript interfaces
│   │   ├── pages/
│   │   │   ├── StudentDashboard.tsx
│   │   │   └── InstructorDashboard.tsx
│   │   ├── components/
│   │   │   ├── ConnectionStatusBadge.tsx
│   │   │   ├── SessionReplay.tsx
│   │   │   ├── PerformanceReport.tsx
│   │   │   └── …
│   │   ├── services/
│   │   │   ├── api.ts              # Typed REST client
│   │   │   └── websocket.ts        # Reconnecting WebSocket (exponential backoff)
│   │   └── hooks/
│   │       ├── useSpeechRecognition.ts
│   │       ├── useSpeechSynthesis.ts
│   │       └── useTimerCountdown.ts
│   ├── Dockerfile                  # Node build → nginx serve
│   ├── nginx.conf
│   └── vercel.json                 # SPA rewrite rules
│
├── scenarios/
│   └── baby_birth.json             # NRP voice-first scenario (17 FSM states)
│
├── docs/
│   ├── index.html                  # GitHub Pages landing page
│   ├── release-v1.0.0.md           # v1.0.0 release notes
│   └── screenshots/                # UI screenshots (see screenshots/README.md)
│
├── .github/
│   ├── workflows/ci.yml            # 5-job CI pipeline
│   ├── ISSUE_TEMPLATE/             # Bug report + feature request templates
│   └── PULL_REQUEST_TEMPLATE.md
│
├── docker-compose.yml
├── railway.toml
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── ROADMAP.md
├── SECURITY.md
├── DEMO_RUNBOOK.md
├── LICENSE
├── .env.local.example
└── .env.production.example
```

---

## Testing

### Backend (41 tests)

```bash
cd backend

# Set environment variables
export DATABASE_URL="sqlite+aiosqlite:///./test.db"
export JWT_SECRET_KEY="test-secret-not-for-production"
export ALLOWED_ORIGINS='["http://localhost:5173"]'
export SCENARIOS_DIR="../scenarios"

pip install -r requirements-dev.txt
pytest tests/ -v
```

| File | Tests | Area |
|------|-------|------|
| `test_clinical_timeline_service.py` | 20 | CSV + XLSX clinical timeline generation, phase assignment, edge cases |
| `test_infrastructure.py` | 21 | `/health`, `/version`, root endpoint, `run_startup_checks()` |
| **Total** | **41** | |

### Frontend

```bash
cd frontend
npx tsc --noEmit    # 0 errors expected
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full plan.

**v1.1:** Additional NRP scenarios · Multi-language voice support · Student authentication · Session history  
**v1.2:** Competency tracking · Instructor annotations · SCORM export · PostgreSQL default  
**v2.0:** Whisper transcription · Branching scenarios · Mobile PWA

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.
Please note that this project has a [Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to abide by its terms.

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE).

---

## Acknowledgements

- NRP clinical protocol guidelines (American Academy of Pediatrics / American Heart Association)
- [FastAPI](https://fastapi.tiangolo.com/) — Sebastián Ramírez and contributors
- [ReportLab](https://www.reportlab.com/) — PDF generation
- [openpyxl](https://openpyxl.readthedocs.io/) — Excel generation
- [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) — browser-native speech recognition and synthesis
- [Tailwind CSS](https://tailwindcss.com/) — utility-first CSS framework
- [Contributor Covenant](https://www.contributor-covenant.org/) — Code of Conduct
