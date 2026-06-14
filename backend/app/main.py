import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine


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


@app.on_event("startup")
async def startup() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    logger.info(
        "Application startup complete",
        extra={"app": settings.APP_NAME, "event": "startup"},
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
