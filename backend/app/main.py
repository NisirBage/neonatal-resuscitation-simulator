import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import scenarios, sessions, ws
from app.startup_validation import run_startup_checks

# Captured once at import time so /health and /version can report it.
_STARTUP_TIMESTAMP = datetime.now(tz=timezone.utc).isoformat()
_VERSION = "1.0.0"


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, str] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        app_name = getattr(record, "app", None)
        if isinstance(app_name, str):
            log_record["app"] = app_name

        event = getattr(record, "event", None)
        if isinstance(event, str):
            log_record["event"] = event

        if record.exc_info is not None:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger.handlers.clear()
logger.addHandler(handler)
logger.propagate = False

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Voice-first, scenario-driven clinical training simulator for neonatal resuscitation. "
        "Guides student clinicians through the NRP protocol via real-time voice interaction, "
        "WebSocket state synchronisation, and a comprehensive instructor dashboard."
    ),
    version=_VERSION,
    debug=settings.DEBUG,
    contact={
        "name": "NRS Project",
        "url": "https://github.com/NisirBage/neonatal-resuscitation-simulator",
    },
    license_info={"name": "MIT", "identifier": "MIT"},
    openapi_tags=[
        {
            "name": "Sessions",
            "description": "Start, control, and export simulation sessions.",
        },
        {
            "name": "Scenarios",
            "description": "List, inspect, and validate scenario definitions.",
        },
        {
            "name": "WebSocket",
            "description": "Real-time session event stream for students and instructors.",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(scenarios.router, prefix="/api/scenarios", tags=["Scenarios"])
app.include_router(ws.router, prefix="/api/ws", tags=["WebSocket"])


@app.on_event("startup")
async def startup() -> None:
    logger.info(
        f"Starting {settings.APP_NAME} v{_VERSION}",
        extra={"app": settings.APP_NAME, "event": "startup_begin"},
    )
    # Log deployment config (no secrets).
    db_scheme = settings.DATABASE_URL.split("://")[0]
    logger.info(
        f"Configuration: DEBUG={settings.DEBUG}, DB={db_scheme}://..., "
        f"SCENARIOS_DIR={settings.SCENARIOS_DIR}",
        extra={"app": settings.APP_NAME, "event": "startup_config"},
    )

    # Initialise database table and verify connectivity.
    from app.models import PersistedSession

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: PersistedSession.__table__.create(sync_conn, checkfirst=True)
        )

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    logger.info(
        "Database connectivity verified",
        extra={"app": settings.APP_NAME, "event": "db_ready"},
    )

    # Fail fast if scenarios directory or files are missing/corrupt.
    run_startup_checks(
        scenarios_dir=Path(settings.SCENARIOS_DIR),
        app_name=settings.APP_NAME,
    )

    await _restore_sessions()

    logger.info(
        f"Application startup complete — listening for connections",
        extra={"app": settings.APP_NAME, "event": "startup"},
    )


async def _restore_sessions() -> None:
    from app.fsm import FSMEngine
    from app.scenario import load_scenario, Scenario
    from app.services.session_service import load_running_sessions
    from app.session_service import SessionRecord
    from app.routers.sessions import scenario_runner, SCENARIOS_DIR

    rows = await load_running_sessions()
    if not rows:
        return

    scenario_cache: dict[str, Scenario] = {}
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            s = load_scenario(str(path))
            scenario_cache[s.id] = s
        except Exception:
            pass

    restored = 0
    for row in rows:
        try:
            scenario = scenario_cache.get(row["scenario_id"])
            if scenario is None:
                logger.warning(
                    f"Cannot restore session {row['id']}: scenario '{row['scenario_id']}' not found",
                    extra={"app": settings.APP_NAME, "event": "restore_session_skipped"},
                )
                continue

            fsm_data = json.loads(row["fsm_state"])
            engine_obj = FSMEngine.deserialize(scenario, fsm_data)
            record = SessionRecord(
                session_id=UUID(row["id"]),
                scenario=scenario,
                engine=engine_obj,
                status=row["status"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            await scenario_runner.restore_session(record)
            restored += 1
        except Exception as exc:
            logger.error(
                f"Failed to restore session {row['id']}: {exc}",
                extra={"app": settings.APP_NAME, "event": "restore_session_failed"},
            )

    if restored:
        logger.info(
            f"Restored {restored} session(s) from database",
            extra={"app": settings.APP_NAME, "event": "sessions_restored"},
        )


@app.on_event("shutdown")
async def shutdown() -> None:
    logger.info(
        "Application shutdown complete",
        extra={"app": settings.APP_NAME, "event": "shutdown"},
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "version": _VERSION,
    }


@app.get("/health")
async def health() -> JSONResponse:
    """
    Returns HTTP 200 + status=healthy when all dependencies are reachable.
    Returns HTTP 503 + status=degraded if any dependency is down.
    Railway / Docker health checks should target this endpoint.
    """
    scenarios_dir = Path(settings.SCENARIOS_DIR)
    scenario_files = list(scenarios_dir.glob("*.json")) if scenarios_dir.exists() else []

    db_status = "ok"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    is_healthy = (
        db_status == "ok"
        and scenarios_dir.exists()
        and len(scenario_files) > 0
    )

    body = {
        "status": "healthy" if is_healthy else "degraded",
        "database": db_status,
        "scenarios_dir": str(scenarios_dir),
        "scenarios_dir_exists": scenarios_dir.exists(),
        "scenario_count": len(scenario_files),
        "version": _VERSION,
        "startup_timestamp": _STARTUP_TIMESTAMP,
    }
    return JSONResponse(content=body, status_code=200 if is_healthy else 503)


@app.get("/version")
async def version() -> dict[str, str | None]:
    """
    Returns build metadata. Used by the frontend footer and by operators
    to confirm which build is deployed.
    """
    # Railway injects this env var automatically when deploying from GitHub.
    git_commit: str | None = os.environ.get("RAILWAY_GIT_COMMIT_SHA")

    if not git_commit:
        # Development convenience: read from git if available.
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                git_commit = result.stdout.strip()
        except Exception:
            pass

    return {
        "version": _VERSION,
        "git_commit": git_commit,
        "build_timestamp": _STARTUP_TIMESTAMP,
        "environment": "development" if settings.DEBUG else "production",
        "python_version": sys.version,
    }
