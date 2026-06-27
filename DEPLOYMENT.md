# Deployment Guide

This document covers every deployment method for the Neonatal Resuscitation Simulator.
Choose the method that matches your environment.

---

## Contents

- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Docker (single machine)](#docker-single-machine)
- [Docker Compose (recommended for demos)](#docker-compose-recommended-for-demos)
- [Railway (production backend)](#railway-production-backend)
- [Vercel (production frontend)](#vercel-production-frontend)
- [Environment Variables Reference](#environment-variables-reference)
- [Troubleshooting](#troubleshooting)
- [Recovery Procedures](#recovery-procedures)

---

## Prerequisites

| Tool | Minimum version | Required for |
|------|----------------|-------------|
| Python | 3.10 | Local backend |
| pip | 22+ | Local backend |
| Node.js | 18 | Local frontend |
| npm | 9+ | Local frontend |
| Docker | 24+ | Docker deployments |
| Docker Compose | V2 (`docker compose`) | Docker Compose |
| Git | Any | All |

---

## Local Development

Best for: development, debugging, demos without Docker.

### 1. Clone the repository

```bash
git clone https://github.com/NisirBage/neonatal-resuscitation-simulator.git
cd neonatal-resuscitation-simulator
```

### 2. Configure the backend

```bash
cp .env.local.example backend/.env
# Open backend/.env and verify JWT_SECRET_KEY — the default is fine for local use
```

### 3. Start the backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Wait for: `Application startup complete`

Verify: open `http://127.0.0.1:8000/health` — should return `{"status":"healthy"}`

### 4. Start the frontend (new terminal)

```bash
cd frontend
npm install
npm run dev
```

Wait for: `VITE ready in ... ms`

| URL | Purpose |
|-----|---------|
| http://localhost:5173 | Student view |
| http://localhost:5173/?role=instructor | Instructor view |
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000/health | Health check |

### PowerShell scripts (Windows convenience)

The repository includes helper scripts for Windows:

| Script | Purpose |
|--------|---------|
| `setup.ps1` | First-time setup (venv + pip + npm install) |
| `run_backend.ps1` | Start the backend |
| `run_frontend.ps1` | Start the frontend |
| `run_all.ps1` | Start both in separate windows |
| `reset_database.ps1` | Delete and recreate the SQLite database |

---

## Docker (single machine)

Best for: verifying the production image without Compose.

### Build and run the backend image

```bash
# From the repository root
docker build -f backend/Dockerfile -t nrs-backend .

docker run --rm -p 8000:8000 \
  -e DATABASE_URL="sqlite+aiosqlite:////tmp/neonatal.db" \
  -e JWT_SECRET_KEY="any-random-string" \
  -e ALLOWED_ORIGINS='["http://localhost:5173"]' \
  nrs-backend
```

### Build and run the frontend image

```bash
docker build -f frontend/Dockerfile \
  --build-arg VITE_API_BASE_URL=http://localhost:8000 \
  --build-arg VITE_WS_BASE_URL=ws://localhost:8000 \
  -t nrs-frontend .

docker run --rm -p 5173:80 nrs-frontend
```

---

## Docker Compose (recommended for demos)

Best for: demonstrations, local staging, one-command startup.

### First-time setup

```bash
cp .env.local.example .env
# Edit .env — set JWT_SECRET_KEY to any string
```

### Start all services

```bash
docker compose up --build
```

First build takes ~3–5 minutes. Subsequent starts are instant:

```bash
docker compose up
```

Both services are ready when you see:

```
backend-1   | {"event": "startup", "message": "Application startup complete..."}
frontend-1  | ... start worker process
```

### Stop services

```bash
docker compose down          # preserves database (nrs_data volume)
docker compose down -v       # also deletes database — full reset
```

### Verify

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy", "database":"ok", ...}
```

### Docker Compose environment variables

The Compose file reads from `.env` in the project root. All variables from `.env.local.example` apply.
The two variables required at the root `.env` level:

| Variable | Required | Default in Compose |
|----------|----------|--------------------|
| `JWT_SECRET_KEY` | **Yes** | None — must be set |
| `VITE_API_BASE_URL` | No | `http://localhost:8000` |
| `VITE_WS_BASE_URL` | No | `ws://localhost:8000` |

---

## Railway (production backend)

Best for: persistent production deployment accessible over the internet.

### Step-by-step

1. **Push the repository to GitHub.**

2. **Create a new Railway project:**
   - Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
   - Select `neonatal-resuscitation-simulator`

3. **Railway reads `railway.toml` automatically.** No additional build configuration required.
   - Builder: Dockerfile (`backend/Dockerfile`)
   - Health check: `GET /health` (30 s timeout)
   - Restart policy: On failure (max 3 retries)

4. **Attach a persistent volume (required for SQLite):**
   - Service → Settings → Volumes → Add Volume
   - Mount path: `/app/data`
   - This preserves `neonatal.db` across deploys and restarts

5. **Set environment variables** (Service → Variables):

   | Variable | Value |
   |----------|-------|
   | `DATABASE_URL` | `sqlite+aiosqlite:////app/data/neonatal.db` |
   | `JWT_SECRET_KEY` | 64-char hex string (`python -c "import secrets; print(secrets.token_hex(32))"`) |
   | `ALLOWED_ORIGINS` | `["https://your-app.vercel.app"]` |
   | `DEBUG` | `false` |
   | `APP_NAME` | `Neonatal Resuscitation Simulator` |

   > Do **not** set `PORT` — Railway injects it automatically.

6. **Enable auto-deploy:** Service → Settings → Auto-deploy on push to `main`.

7. **Verify:** open `https://your-backend.up.railway.app/health` — should return `{"status":"healthy"}`.

8. **Copy the Railway URL** for the Vercel step.

### PostgreSQL (optional — for high-load or multi-instance)

1. Add the PostgreSQL plugin to the Railway project.
2. Railway injects `DATABASE_URL` automatically — remove the SQLite variable.
3. No application code changes needed; the asyncpg driver is already in `requirements.txt`.

---

## Vercel (production frontend)

Best for: global CDN delivery of the React SPA.

### Step-by-step

1. **Import the repository** at [vercel.com/new](https://vercel.com/new).

2. **Configure the project:**
   - Framework Preset: **Vite** (auto-detected)
   - Root Directory: `frontend`
   - Build Command: `npm run build` (default)
   - Output Directory: `dist` (default)

3. **Set environment variables** (Project Settings → Environment Variables → Production):

   | Variable | Value |
   |----------|-------|
   | `VITE_API_BASE_URL` | `https://your-backend.up.railway.app` |
   | `VITE_WS_BASE_URL` | `wss://your-backend.up.railway.app` |

   > These are baked into the JavaScript bundle at build time. **Redeploy after changing them.**

4. **Deploy.** Vercel auto-deploys on every push to `main`.

5. **Update Railway CORS:** add the Vercel URL to `ALLOWED_ORIGINS` in the Railway variables.

6. **Verify:** open the Vercel URL → should load the student view.

### Vercel `vercel.json`

The `frontend/vercel.json` configures SPA routing:

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

This ensures `/?role=instructor` loads correctly on direct access.

---

## Environment Variables Reference

### Backend (all deployments)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **Yes** | — | `sqlite+aiosqlite:///./neonatal.db` (local) or `sqlite+aiosqlite:////app/data/neonatal.db` (Docker/Railway) |
| `JWT_SECRET_KEY` | **Yes** | — | Random hex string — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ALLOWED_ORIGINS` | **Yes** | — | JSON array: `["https://your-app.vercel.app"]` |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Token lifetime in minutes |
| `DEBUG` | No | `false` | Set to `true` for development only |
| `SCENARIOS_DIR` | No | `<repo_root>/scenarios` | Absolute path to scenario JSON files |
| `APP_NAME` | No | `Neonatal Resuscitation Simulator` | Display name in logs |
| `PORT` | Auto | `8000` | Injected by Railway — do not set manually |

### Frontend (Vercel / Docker build args)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_BASE_URL` | Yes (production) | `http://localhost:8000` | Backend REST base URL |
| `VITE_WS_BASE_URL` | Yes (production) | `ws://localhost:8000` | Backend WebSocket base URL |

> `VITE_*` variables are baked into the bundle at Vite build time.
> The defaults are only used when the variable is not set — appropriate for local development only.

---

## Troubleshooting

### Backend won't start

| Symptom | Cause | Fix |
|---------|-------|-----|
| `pydantic_settings.env_file_encoding` error | Missing `.env` file | `cp .env.local.example backend/.env` |
| `ValidationError: DATABASE_URL` | Required variable not set | Check `.env` or environment variables |
| `ModuleNotFoundError: app` | Not in `backend/` directory | `cd backend` before running uvicorn |
| `RuntimeError: SCENARIOS_DIR does not exist` | Wrong working directory or `SCENARIOS_DIR` | Start uvicorn from `backend/`; check `SCENARIOS_DIR` |
| `RuntimeError: No valid scenario files found` | `scenarios/` is empty or all JSON invalid | Check `scenarios/baby_birth.json` exists and is valid JSON |
| Port 8000 already in use | Previous server still running | `lsof -i :8000` (macOS/Linux) or `netstat -ano | findstr :8000` (Windows) |

### Frontend

| Symptom | Cause | Fix |
|---------|-------|-----|
| Blank page | Backend not running | Start the backend first |
| "Cannot reach the backend" | CORS or backend down | Verify backend health; check `ALLOWED_ORIGINS` |
| `/?role=instructor` returns 404 on Vercel | SPA rewrite missing | Confirm `vercel.json` is in `frontend/` |
| Voice recognition not working | Requires HTTPS or Chrome/Edge | Use `https://` URL; use Chrome or Edge |
| WebSocket fails with `wss://` | `VITE_WS_BASE_URL` wrong | Ensure `wss://` not `ws://` in production |

### Docker / Docker Compose

| Symptom | Cause | Fix |
|---------|-------|-----|
| "502 Bad Gateway" on frontend | Backend still starting | Wait ~40 s for health check to pass |
| `invalid interpolation format` | `JWT_SECRET_KEY` not in `.env` | Add `JWT_SECRET_KEY=any-string` to root `.env` |
| Sessions lost after `docker compose down` | Volume deleted | Use `docker compose down` (no `-v`) to preserve data |
| Image builds but container exits immediately | Missing required env var | Check `docker compose logs backend` |
| `COPY failed: file not found` | Build context is wrong | Build from repo root: `docker build -f backend/Dockerfile .` |

### Railway

| Symptom | Cause | Fix |
|---------|-------|-----|
| Health check fails | `PORT` is not 8000 | Do not override `PORT` — Railway sets it |
| Sessions lost after deploy | No volume attached | Attach volume at `/app/data` in Railway Settings |
| CORS errors in browser | `ALLOWED_ORIGINS` missing Vercel URL | Add exact Vercel URL (no trailing slash) |
| `DATABASE_URL` error on deploy | Variable not set | Add in Railway dashboard → Variables |

---

## Recovery Procedures

### Backend crash / restart

Sessions survive backend restarts automatically. On startup, `main.py` queries all `running`
sessions from the database and reconstructs their FSM state in memory. The student and instructor
views reconnect via WebSocket exponential backoff (1 s → 30 s) and re-sync state automatically.

No manual intervention required unless the volume is lost (see below).

### Database corruption or loss (Railway)

1. Stop the Railway service.
2. Delete the corrupted volume or attach a new empty volume at `/app/data`.
3. Redeploy — the backend creates a fresh `neonatal.db` on startup.
4. Old sessions are unrecoverable if the database file is gone; new sessions work immediately.

### Rollback a bad deployment

```bash
# Revert to the previous commit
git revert HEAD --no-edit
git push origin main
# Railway / Vercel pick up the push and auto-deploy the reverted version
```

### Reset the local database

```bash
# Windows
.\reset_database.ps1

# macOS / Linux
rm backend/neonatal.db
# The database is recreated automatically on next backend start
```

### Docker volume reset

```bash
docker compose down -v    # deletes nrs_data volume (all session data lost)
docker compose up --build
```
