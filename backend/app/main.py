import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import scenarios, sessions, ws


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
    debug=settings.DEBUG,
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
    from app.models import PersistedSession

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: PersistedSession.__table__.create(sync_conn, checkfirst=True)
        )

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    await _restore_sessions()

    logger.info(
        "Application startup complete",
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
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
