# Release Notes — v1.0.0

**Release date:** 2026-06-25  
**Tag:** `v1.0.0`  
**Branch:** `main`

---

## Overview

This is the first stable release of the Neonatal Resuscitation Simulator — a voice-first,
scenario-driven clinical training platform for neonatal resuscitation protocol (NRP) education.

The simulator is feature-complete for its v1.0 scope: a single NRP scenario, full voice
interaction, real-time instructor oversight, session persistence, four export formats, and
a production-ready deployment pipeline.

---

## Major Features

### Core Simulation Engine
- **Voice-first NRP workflow** — the simulator speaks each protocol prompt; students respond verbally ("yes" / "no") via the Web Speech API
- **Finite State Machine engine** (`fsm.py`) — all clinical logic lives in a JSON scenario file; the engine enforces valid transitions and records every self-loop
- **17-state NRP scenario** (`scenarios/baby_birth.json`) covering: birth confirmation, initial assessment, airway management, ventilation, heart rate evaluation, advanced resuscitation, and completion
- **Event sourcing** — every state change is an immutable `SimulationEvent` appended to the database; replay, metrics, and all exports derive from this log
- **Pub/Sub EventBus** — decouples the FSM from WebSocket broadcasting and timer scheduling

### Student Dashboard
- Live voice prompt display with speech synthesis
- Continuous speech recognition with auto-restart on silence
- Manual YES / NO button fallback
- Birth elapsed clock (starts at session creation)
- Ventilation countdown progress bar
- Session replay and performance metrics on completion

### Instructor Dashboard
- Live session list (polled every 5 s)
- Real-time FSM state display via WebSocket
- Override panel: force any instructor-defined state transition
- Manual timer controls: fire any timer immediately
- Live event log (last 40 events, colour-coded by type)

### Reporting & Export
- **PDF performance report** (ReportLab): training score, metrics table, full event timeline
- **Raw event CSV** (UTF-8 BOM): every FSM event with timestamps and payloads
- **Clinical timeline CSV**: second-by-second, clinical language, for instructor review
- **Clinical timeline XLSX**: colour-coded Excel workbook with clinical phase column, training score, and summary section

### Infrastructure
- SQLite database persistence; PostgreSQL-ready via asyncpg
- Automatic session restore on backend restart from persisted FSM state
- `GET /health` — database + scenario check; HTTP 503 if degraded
- `GET /version` — git commit SHA, build timestamp, Python version
- Structured JSON logging throughout the backend
- WebSocket auto-reconnect with exponential backoff (1 s → 30 s)
- User-friendly frontend error messages for network failures and session expiry
- Docker Compose for full local development
- Railway (backend) + Vercel (frontend) production deployment
- GitHub Actions CI: 5-job pipeline (backend tests, TypeScript check, backend Docker, frontend Docker, frontend bundle)

---

## Technical Highlights

| Aspect | Detail |
|--------|--------|
| Architecture | Event-sourced FSM; all state is derivable from the event log |
| Backend | FastAPI 0.137, Python 3.10, async SQLAlchemy, uvicorn |
| Frontend | React 18, TypeScript 5, Vite 5, Tailwind CSS |
| Real-time | Native WebSocket with server-side connection manager |
| Persistence | SQLite (aiosqlite driver); swap to PostgreSQL via one env var |
| Testing | 41 pytest tests (infrastructure + clinical timeline service) |
| TypeScript | 0 errors on `tsc --noEmit` |
| Docker | Multi-stage builds; non-root user (uid 1001) in backend image |
| CI | 5 jobs; blocks merge on test failure or TypeScript error |

---

## Known Limitations

- **Single scenario** — only one NRP pathway (`baby_birth.json`) is included. Additional scenarios (meconium, premature infant, APGAR) are planned for v1.1.
- **No student authentication** — any user can start a session on the student view. JWT-gated student endpoints are planned for v1.1.
- **Timers reset on restart** — auto-start timers restart from their full duration after a backend restart (the FSM state is preserved, but elapsed timer time is not).
- **SQLite only in production by default** — PostgreSQL support is present but requires manual env var configuration and a separate database service.
- **Voice recognition browser support** — Web Speech API is supported in Chrome and Edge; Firefox requires a fallback to manual buttons.
- **No session history for students** — students cannot browse their past sessions; this is an instructor-only capability via the database.

---

## Future Roadmap

See [ROADMAP.md](../ROADMAP.md) for the full plan. Highlights:

**v1.1 (near-term)**
- Additional NRP scenarios
- Multi-language voice support (Welsh, French, Spanish)
- Student authentication
- Session history list

**v1.2 (medium-term)**
- Competency tracking across sessions
- Instructor annotations on replay events
- SCORM export for LMS integration

**v2.0 (long-term)**
- Whisper audio transcription (broader browser support)
- Branching scenarios
- Mobile PWA

---

## Installation

### Local Development

```bash
git clone https://github.com/NisirBage/neonatal-resuscitation-simulator.git
cd neonatal-resuscitation-simulator

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.local.example ../.env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend (new terminal)
cd frontend
npm install && npm run dev
```

### Docker

```bash
cp .env.local.example .env
# Edit .env — set JWT_SECRET_KEY to any random string
docker compose up --build
```

---

## Deployment

See the [README — Production Deployment](../README.md#production-deployment) section for step-by-step Railway + Vercel deployment instructions.

---

## Checksums

SHA-256 checksums for the source archive will be published alongside the GitHub Release asset.

---

## Credits

Built by [NisirBage](https://github.com/NisirBage) as a final-year software engineering project.

Dependencies: FastAPI, SQLAlchemy, uvicorn, ReportLab, openpyxl, React, Vite, Tailwind CSS, Web Speech API.

Clinical protocol based on the Neonatal Resuscitation Program (NRP) guidelines.
