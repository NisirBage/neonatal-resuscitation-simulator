from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.events import EventBus
from app.scenario import Scenario
from app.session_service import SessionManager, SessionRecord


class ScenarioRunner:
    def __init__(
        self,
        session_manager: SessionManager | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.session_manager = session_manager or SessionManager()
        self.event_bus = event_bus or EventBus()

    async def start_session(
        self,
        scenario: Scenario,
        session_id: UUID | None = None,
    ) -> SessionRecord:
        record = await self.session_manager.create_session(
            scenario=scenario,
            session_id=session_id,
        )
        await self.event_bus.publish(
            "session.started",
            session_id=record.session_id,
            source="scenario_runner",
            aggregate_id=str(record.session_id),
            payload={
                "scenario_id": scenario.id,
                "scenario_name": scenario.name,
                "scenario_version": scenario.version,
                "current_state_id": record.engine.get_current_state().id,
            },
        )
        return record

    async def stop_session(self, session_id: UUID) -> SessionRecord:
        record = await self.session_manager.remove_session(session_id)
        await self.event_bus.publish(
            "session.stopped",
            session_id=session_id,
            source="scenario_runner",
            aggregate_id=str(session_id),
            payload={
                "scenario_id": record.scenario.id,
                "status": record.status,
            },
        )
        return record

    async def process_student_input(
        self,
        session_id: UUID,
        action_id: str,
        response: str | bool,
    ) -> SessionRecord:
        record = self._get_active_session(session_id)
        self._ensure_running(record)
        state = record.engine.process_student_input(
            action_id=action_id,
            response=response,
        )
        self._touch(record)
        await self.event_bus.publish(
            "student.input",
            session_id=session_id,
            source="scenario_runner",
            aggregate_id=str(session_id),
            payload={
                "action_id": action_id,
                "response": response,
                "current_state_id": state.current_state_id,
            },
        )
        await self._publish_latest_fsm_event(record)
        return record

    async def process_audio_input(
        self,
        session_id: UUID,
        action_id: str,
        transcript: str,
        confidence: float | None = None,
    ) -> SessionRecord:
        record = self._get_active_session(session_id)
        self._ensure_running(record)
        state = record.engine.process_audio_input(
            action_id=action_id,
            transcript=transcript,
            confidence=confidence,
        )
        self._touch(record)

        payload: dict[str, Any] = {
            "action_id": action_id,
            "transcript": transcript,
            "current_state_id": state.current_state_id,
        }
        if confidence is not None:
            payload["confidence"] = confidence

        await self.event_bus.publish(
            "audio.input",
            session_id=session_id,
            source="scenario_runner",
            aggregate_id=str(session_id),
            payload=payload,
        )
        await self._publish_latest_fsm_event(record)
        return record

    async def process_timer(
        self,
        session_id: UUID,
        timer_id: str,
    ) -> SessionRecord:
        record = self._get_active_session(session_id)
        self._ensure_running(record)
        state = record.engine.process_timer_event(timer_id)
        self._touch(record)
        await self.event_bus.publish(
            "timer.expired",
            session_id=session_id,
            source="scenario_runner",
            aggregate_id=str(session_id),
            payload={
                "timer_id": timer_id,
                "current_state_id": state.current_state_id,
            },
        )
        await self._publish_latest_fsm_event(record)
        return record

    async def process_instructor_action(
        self,
        session_id: UUID,
        event_name: str,
    ) -> SessionRecord:
        record = self._get_active_session(session_id)
        self._ensure_running(record)
        state = record.engine.process_instructor_event(event_name)
        self._touch(record)
        await self.event_bus.publish(
            "instructor.action",
            session_id=session_id,
            source="scenario_runner",
            aggregate_id=str(session_id),
            payload={
                "event": event_name,
                "current_state_id": state.current_state_id,
            },
        )
        await self._publish_latest_fsm_event(record)
        return record

    async def _publish_latest_fsm_event(self, record: SessionRecord) -> None:
        history = record.engine.get_history()
        if not history:
            return

        latest_event = history[-1]
        await self.event_bus.publish(
            f"fsm.{latest_event.type}",
            session_id=record.session_id,
            source="fsm",
            aggregate_id=str(record.session_id),
            payload=latest_event.model_dump(mode="json"),
        )

    def _get_active_session(self, session_id: UUID) -> SessionRecord:
        with self.session_manager._lock:
            return self.session_manager._get_record(session_id)

    def _ensure_running(self, record: SessionRecord) -> None:
        if record.status != "running":
            raise RuntimeError(f"session '{record.session_id}' is not running")

    def _touch(self, record: SessionRecord) -> None:
        record.updated_at = datetime.now(timezone.utc)
