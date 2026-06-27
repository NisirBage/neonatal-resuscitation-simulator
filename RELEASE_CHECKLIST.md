# Release Checklist — v1.0.0

Use this checklist before tagging and publishing the v1.0.0 GitHub Release.
Mark each item as you complete it. Do not publish the release until all items are checked.

---

## Repository

- [ ] `main` branch is clean — `git status` shows no uncommitted changes
- [ ] `git log --oneline -10` — most recent commits are meaningful (no "wip", "temp", "debug")
- [ ] No `.env`, `*.db`, `*.pdf`, `*.xlsx`, or `*.log` files tracked by git
  - Verify: `git ls-files | grep -E '\.env$|\.db$|\.pdf$|\.xlsx$|\.log$'` — must return nothing
- [ ] `frontend/dist/` is not tracked by git
- [ ] No empty placeholder files remain (`tests/test_backend.py`, `scenarios/nrp_birth.json`, `frontend/src/pages/Login.tsx` — all deleted)
- [ ] Repository description set on GitHub: "Voice-first NRP clinical training simulator — FastAPI · React · WebSocket · Docker"
- [ ] Repository topics set on GitHub: `nrp`, `clinical-simulation`, `fastapi`, `react`, `websocket`, `finite-state-machine`, `event-sourcing`, `typescript`, `docker`
- [ ] Repository website set to the GitHub Pages URL (if Pages is enabled) or Vercel URL

---

## Documentation

- [ ] `README.md` — renders correctly on GitHub (check headings, tables, badges, image links)
- [ ] `CHANGELOG.md` — v1.0.0 entry present with correct date (2026-06-25)
- [ ] `ROADMAP.md` — reviewed, accurate
- [ ] `CONTRIBUTING.md` — setup instructions tested locally
- [ ] `CODE_OF_CONDUCT.md` — present
- [ ] `SECURITY.md` — contact email correct
- [ ] `LICENSE` — year and name correct (2026, NisirBage)
- [ ] `DEPLOYMENT.md` — reviewed, accurate for all deployment paths
- [ ] `DEMO_RUNBOOK.md` — reviewed, no references to deleted files
- [ ] `docs/release-v1.0.0.md` — reviewed, accurate
- [ ] `docs/index.html` — GitHub Pages landing page renders correctly in a browser
- [ ] `docs/screenshots/README.md` — reviewed

---

## Screenshots (capture before release)

- [ ] `docs/screenshots/student-dashboard.png` — captured (1280 × 800)
- [ ] `docs/screenshots/instructor-dashboard.png` — captured (1280 × 800)
- [ ] `docs/screenshots/session-replay.png` — captured (1280 × 800)
- [ ] `docs/screenshots/performance-metrics.png` — captured (1280 × 800)
- [ ] `docs/screenshots/pdf-report.png` — captured (1280 × 900)
- [ ] `docs/screenshots/clinical-xlsx.png` — captured (1280 × 800)
- [ ] `docs/screenshots/demo-workflow.gif` — recorded (~30 s, 15 fps, 1280 × 720)
- [ ] README image links updated and verified on GitHub

---

## Deployment

### Local Development
- [ ] Fresh clone → `cp .env.local.example backend/.env` → `pip install -r requirements.txt` → `uvicorn` starts without error
- [ ] `GET /health` returns `{"status":"healthy"}`
- [ ] `GET /version` returns version and git commit
- [ ] Frontend: `npm install` → `npm run dev` → loads in browser
- [ ] Voice recognition works (Chrome/Edge, localhost)
- [ ] Manual YES/NO buttons work

### Docker Compose
- [ ] `cp .env.local.example .env` → `docker compose up --build` succeeds
- [ ] Both containers reach healthy state within 60 s
- [ ] `GET http://localhost:8000/health` returns `{"status":"healthy"}`
- [ ] Student view loads at `http://localhost:5173`
- [ ] Instructor view loads at `http://localhost:5173/?role=instructor`
- [ ] Session started, voice prompt appears
- [ ] `docker compose down` → `docker compose up` — database persists

### Railway (production backend)
- [ ] Backend deployed via Railway
- [ ] Volume attached at `/app/data`
- [ ] All required environment variables set (DATABASE_URL, JWT_SECRET_KEY, ALLOWED_ORIGINS, DEBUG=false)
- [ ] `GET https://your-backend.up.railway.app/health` returns `{"status":"healthy"}`
- [ ] Auto-deploy on push to `main` enabled

### Vercel (production frontend)
- [ ] Frontend deployed via Vercel
- [ ] `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` set correctly (https:// and wss://)
- [ ] Production URL loads in browser
- [ ] `/?role=instructor` loads correctly (SPA rewrite working)
- [ ] Voice recognition works on the HTTPS production URL

---

## Testing

- [ ] `cd backend && python -m pytest tests/ -v` — all 41 tests pass, 0 failures
- [ ] `cd frontend && npx tsc --noEmit` — 0 TypeScript errors
- [ ] GitHub Actions CI — all 5 jobs green on `main` branch

---

## Live Validation

Run through this checklist against the deployed production URLs before publishing the release.

### Session lifecycle
- [ ] Select scenario → Start Session → session ID returned
- [ ] First voice prompt spoken by browser TTS
- [ ] YES / NO buttons work
- [ ] Voice recognition works (Chrome, HTTPS)
- [ ] FSM advances through at least 5 states
- [ ] Birth timer visible and incrementing
- [ ] Ventilation countdown appears during ventilation states

### Instructor dashboard
- [ ] Session appears in instructor session list
- [ ] Live FSM state updates in real time (< 1 s after student input)
- [ ] Instructor override button triggers state transition
- [ ] Manual timer fire works
- [ ] Live event log updates with each event

### WebSocket
- [ ] Student WebSocket status badge shows "Connected"
- [ ] Instructor WebSocket status badge shows "Connected"
- [ ] Disconnect and reconnect: badge transitions to "Reconnecting" then back to "Connected"
- [ ] State re-syncs after reconnect

### Session completion and exports
- [ ] Complete a session to `simulation_complete` state
- [ ] Session replay renders all events
- [ ] Performance metrics display training score
- [ ] PDF report downloads and opens correctly
- [ ] Raw event CSV downloads (check column headers and row count)
- [ ] Clinical CSV downloads (check clinical language)
- [ ] Clinical XLSX downloads and opens in Excel with colour-coding

### Persistence
- [ ] Start session → restart backend → session visible in instructor list
- [ ] State and event history preserved after restart

### Infrastructure
- [ ] `GET /health` returns `{"status":"healthy","database":"ok"}`
- [ ] `GET /version` returns `{"version":"1.0.0","git_commit":"...","environment":"production"}`

---

## Demo Preparation

- [ ] `DEMO_RUNBOOK.md` reviewed and steps verified locally
- [ ] Backup plan ready for microphone failure (YES/NO buttons tested)
- [ ] Backup plan ready for internet failure (Docker Compose running locally)
- [ ] Browser speech settings tested — TTS voice selected, volume on
- [ ] Presentation slides prepared (if required)
- [ ] Laptop plugged in, power-saving mode disabled

---

## GitHub Release

- [ ] Git tag created: `git tag v1.0.0 && git push origin v1.0.0`
- [ ] GitHub Release created:
  - Title: `v1.0.0 — Initial Release`
  - Tag: `v1.0.0`
  - Body: contents of `docs/release-v1.0.0.md`
  - Marked as **Latest release**
- [ ] Release assets attached (optional): source archive SHA-256 checksum

---

## GitHub Pages (optional)

- [ ] GitHub Pages enabled: Repository Settings → Pages → Source: `Deploy from branch` → `main` → `/docs`
- [ ] `docs/index.html` renders at `https://nisirbage.github.io/neonatal-resuscitation-simulator/`
- [ ] All buttons and links on the landing page work

---

## Post-Release

- [ ] LinkedIn project entry updated with GitHub URL and Vercel demo URL
- [ ] Portfolio website updated
- [ ] README video demo link added (once recording is available)
- [ ] Announce to supervisors / evaluators

---

## Sign-off

| Item | Status | Notes |
|------|--------|-------|
| All tests passing | | |
| All deployments verified | | |
| Screenshots captured | | |
| Release published | | |
| Date | | |
