from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.fsm import FSMEngine, SimulationState
from app.scenario import Scenario


SessionStatus = Literal["running", "paused"]


class SessionRecord(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: UUID
    scenario: Scenario
    engine: FSMEngine
    status: SessionStatus = "running"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def serialize(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "scenario": self.scenario.model_dump(mode="json"),
            "state": self.engine.serialize(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[UUID, SessionRecord] = {}
        self._lock = RLock()

    async def create_session(
        self,
        scenario: Scenario,
        session_id: UUID | None = None,
    ) -> SessionRecord:
        with self._lock:
            resolved_session_id = session_id or uuid4()
            if resolved_session_id in self._sessions:
                raise ValueError(f"session '{resolved_session_id}' already exists")

            engine = FSMEngine(scenario)
            engine.start(session_id=resolved_session_id)

            record = SessionRecord(
                session_id=resolved_session_id,
                scenario=scenario,
                engine=engine,
            )
            self._sessions[resolved_session_id] = record
            return self._copy_record(record)

    async def get_session(self, session_id: UUID) -> SessionRecord:
        with self._lock:
            return self._copy_record(self._get_record(session_id))

    async def list_sessions(self) -> list[SessionRecord]:
        with self._lock:
            return [self._copy_record(record) for record in self._sessions.values()]

    async def pause_session(self, session_id: UUID) -> SessionRecord:
        with self._lock:
            record = self._get_record(session_id)
            record.status = "paused"
            record.updated_at = datetime.now(timezone.utc)
            return self._copy_record(record)

    async def resume_session(self, session_id: UUID) -> SessionRecord:
        with self._lock:
            record = self._get_record(session_id)
            record.status = "running"
            record.updated_at = datetime.now(timezone.utc)
            return self._copy_record(record)

    async def remove_session(self, session_id: UUID) -> SessionRecord:
        with self._lock:
            record = self._sessions.pop(session_id)
            return self._copy_record(record)

    async def session_exists(self, session_id: UUID) -> bool:
        with self._lock:
            return session_id in self._sessions

    async def serialize_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [record.serialize() for record in self._sessions.values()]

    async def restore_all(self, records: list[dict[str, Any]]) -> list[SessionRecord]:
        restored_records: list[SessionRecord] = []

        with self._lock:
            self._sessions.clear()

            for record_data in records:
                scenario = Scenario.model_validate(record_data["scenario"])
                state = SimulationState.model_validate(record_data["state"])
                engine = FSMEngine.deserialize(scenario, state.model_dump(mode="json"))
                session_id = UUID(str(record_data["session_id"]))

                record = SessionRecord(
                    session_id=session_id,
                    scenario=scenario,
                    engine=engine,
                    status=record_data["status"],
                    created_at=datetime.fromisoformat(record_data["created_at"]),
                    updated_at=datetime.fromisoformat(record_data["updated_at"]),
                )
                self._sessions[session_id] = record
                restored_records.append(self._copy_record(record))

        return restored_records

    def _get_record(self, session_id: UUID) -> SessionRecord:
        record = self._sessions.get(session_id)
        if record is None:
            raise KeyError(f"session '{session_id}' does not exist")
        return record

    def _copy_record(self, record: SessionRecord) -> SessionRecord:
        return record.model_copy(deep=False)
