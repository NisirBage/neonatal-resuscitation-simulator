# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-06-25

### Added

**Core Simulation**
- Voice-first NRP (Neonatal Resuscitation Protocol) workflow driven by a JSON-defined finite state machine
- Real-time WebSocket synchronisation between student view and instructor dashboard
- Web Speech API integration: text-to-speech prompts + continuous speech recognition
- Automatic Yes/No recognition from natural language ("yes", "yeah", "yep" → yes; "no", "nope" → no)
- Manual Yes/No buttons as fallback when microphone is unavailable
- Birth elapsed clock and ventilation countdown timer with UI progress bar

**Instructor Dashboard**
- Live session list with polling
- Real-time FSM state display
- Instructor override panel: force any state transition
- Manual timer trigger controls
- Live event log (last 40 events)

**Session Replay**
- Step-through event timeline with playback controls (Prev / Play / Next)
- Colour-coded event badges per event type
- Elapsed time display per event

**Reporting**
- PDF performance report (ReportLab): training score, metrics table, event timeline
- Raw event log CSV export (UTF-8 BOM)
- Clinical timeline CSV: second-by-second, clinical language, for instructor review
- Clinical timeline XLSX: colour-coded Excel workbook with clinical phase column, training score, summary section

**Persistence & Recovery**
- SQLite database persistence (PostgreSQL-ready via asyncpg)
- Automatic session restore on backend restart from persisted FSM state

**Infrastructure**
- FastAPI backend with async SQLAlchemy
- React 18 + TypeScript + Vite frontend
- Docker Compose for local full-stack development
- Multi-stage frontend Docker image (Node build → nginx serve)
- Railway deployment (backend) + Vercel deployment (frontend)
- GitHub Actions CI: backend tests, TypeScript check, backend Docker build, frontend Docker build, frontend bundle build
- `GET /health` with database and scenario checks; HTTP 503 on degraded
- `GET /version` with git commit, build timestamp, Python version
- Structured JSON logging throughout the backend
- Automatic WebSocket reconnection with exponential backoff (1s → 30s)
- User-friendly frontend error messages for network failures and session expiry

---

## [Unreleased]

Nothing pending.
