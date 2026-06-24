from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import PersistedSession
from app.session_service import SessionRecord


async def upsert_session(record: SessionRecord) -> None:
    fsm_blob = json.dumps(record.engine.serialize())
    async with AsyncSessionLocal() as db:
        row = await db.get(PersistedSession, str(record.session_id))
        if row is None:
            db.add(
                PersistedSession(
                    id=str(record.session_id),
                    scenario_id=record.scenario.id,
                    status=record.status,
                    fsm_state=fsm_blob,
                    created_at=record.created_at.isoformat(),
                    updated_at=record.updated_at.isoformat(),
                )
            )
        else:
            row.status = record.status
            row.fsm_state = fsm_blob
            row.updated_at = record.updated_at.isoformat()
        await db.commit()


async def mark_session_stopped(session_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(PersistedSession, str(session_id))
        if row is not None:
            row.status = "stopped"
            await db.commit()


async def load_running_sessions() -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PersistedSession).where(PersistedSession.status == "running")
        )
        return [
            {
                "id": row.id,
                "scenario_id": row.scenario_id,
                "status": row.status,
                "fsm_state": row.fsm_state,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in result.scalars().all()
        ]
