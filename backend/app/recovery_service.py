from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from app.scenario_runner import ScenarioRunner
from app.session_service import SessionManager


CHECKPOINT_SCHEMA_VERSION = "1.0"


class CheckpointMetadata(BaseModel):
    schema_version: str = CHECKPOINT_SCHEMA_VERSION
    checkpoint_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_count: int
    checksum: str


class CheckpointDocument(BaseModel):
    metadata: CheckpointMetadata
    sessions: list[dict[str, Any]]


class RecoveryResult(BaseModel):
    success: bool
    message: str
    checkpoint: CheckpointDocument | None = None
    errors: list[str] = Field(default_factory=list)


class RecoveryService:
    def __init__(
        self,
        session_manager: SessionManager | None = None,
        scenario_runner: ScenarioRunner | None = None,
    ) -> None:
        if session_manager is None and scenario_runner is None:
            session_manager = SessionManager()

        self.session_manager = (
            session_manager
            if session_manager is not None
            else scenario_runner.session_manager
        )
        self.scenario_runner = scenario_runner
        self._lock = RLock()

    async def save_checkpoint(self, path: str) -> RecoveryResult:
        with self._lock:
            try:
                checkpoint = await self.snapshot_sessions()
                checkpoint_path = Path(path)
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

                payload = checkpoint.model_dump(mode="json")
                serialized = json.dumps(payload, indent=2, sort_keys=True)
                temporary_path = checkpoint_path.with_name(
                    f"{checkpoint_path.name}.{uuid4()}.tmp"
                )

                try:
                    temporary_path.write_text(serialized, encoding="utf-8")
                    os.replace(temporary_path, checkpoint_path)
                finally:
                    if temporary_path.exists():
                        temporary_path.unlink()

                return RecoveryResult(
                    success=True,
                    message="checkpoint saved",
                    checkpoint=checkpoint,
                )
            except OSError as exc:
                return RecoveryResult(
                    success=False,
                    message="failed to write checkpoint",
                    errors=[str(exc)],
                )

    async def load_checkpoint(self, path: str) -> RecoveryResult:
        with self._lock:
            try:
                raw_payload = Path(path).read_text(encoding="utf-8")
                checkpoint_data = json.loads(raw_payload)
                checkpoint = CheckpointDocument.model_validate(checkpoint_data)
                validation = await self.validate_checkpoint(checkpoint)
                if not validation.success:
                    return validation

                return RecoveryResult(
                    success=True,
                    message="checkpoint loaded",
                    checkpoint=checkpoint,
                )
            except FileNotFoundError as exc:
                return RecoveryResult(
                    success=False,
                    message="checkpoint file not found",
                    errors=[str(exc)],
                )
            except json.JSONDecodeError as exc:
                return RecoveryResult(
                    success=False,
                    message="checkpoint file is not valid JSON",
                    errors=[str(exc)],
                )
            except ValidationError as exc:
                return RecoveryResult(
                    success=False,
                    message="checkpoint schema validation failed",
                    errors=[error["msg"] for error in exc.errors()],
                )
            except OSError as exc:
                return RecoveryResult(
                    success=False,
                    message="failed to read checkpoint",
                    errors=[str(exc)],
                )

    async def snapshot_sessions(self) -> CheckpointDocument:
        sessions = await self.session_manager.serialize_all()
        checksum = self._calculate_checksum(sessions)
        metadata = CheckpointMetadata(
            session_count=len(sessions),
            checksum=checksum,
        )
        return CheckpointDocument(metadata=metadata, sessions=sessions)

    async def restore_sessions(
        self,
        checkpoint: CheckpointDocument | dict[str, Any],
    ) -> RecoveryResult:
        with self._lock:
            try:
                checkpoint_document = (
                    checkpoint
                    if isinstance(checkpoint, CheckpointDocument)
                    else CheckpointDocument.model_validate(checkpoint)
                )
                validation = await self.validate_checkpoint(checkpoint_document)
                if not validation.success:
                    return validation

                await self.session_manager.restore_all(checkpoint_document.sessions)
                return RecoveryResult(
                    success=True,
                    message="sessions restored",
                    checkpoint=checkpoint_document,
                )
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                return RecoveryResult(
                    success=False,
                    message="failed to restore sessions",
                    errors=[str(exc)],
                )

    async def validate_checkpoint(
        self,
        checkpoint: CheckpointDocument | dict[str, Any],
    ) -> RecoveryResult:
        try:
            checkpoint_document = (
                checkpoint
                if isinstance(checkpoint, CheckpointDocument)
                else CheckpointDocument.model_validate(checkpoint)
            )
        except ValidationError as exc:
            return RecoveryResult(
                success=False,
                message="checkpoint schema validation failed",
                errors=[error["msg"] for error in exc.errors()],
            )

        errors: list[str] = []
        if checkpoint_document.metadata.schema_version != CHECKPOINT_SCHEMA_VERSION:
            errors.append(
                "unsupported checkpoint schema version "
                f"'{checkpoint_document.metadata.schema_version}'"
            )

        if checkpoint_document.metadata.session_count != len(checkpoint_document.sessions):
            errors.append("checkpoint session count does not match session payload")

        checksum = self._calculate_checksum(checkpoint_document.sessions)
        if checksum != checkpoint_document.metadata.checksum:
            errors.append("checkpoint checksum mismatch")

        if errors:
            return RecoveryResult(
                success=False,
                message="checkpoint validation failed",
                checkpoint=checkpoint_document,
                errors=errors,
            )

        return RecoveryResult(
            success=True,
            message="checkpoint is valid",
            checkpoint=checkpoint_document,
        )

    def _calculate_checksum(self, sessions: list[dict[str, Any]]) -> str:
        serialized = json.dumps(sessions, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
