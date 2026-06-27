from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import UUID

from app.events import EventBus
from app.scenario import Scenario
from app.services.session_service import mark_session_stopped, upsert_session
from app.session_service import SessionManager, SessionRecord

logger = logging.getLogger(__name__)


class ScenarioRunner:
    def __init__(
        self,
        session_manager: SessionManager | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.session_manager = session_manager or SessionManager()
        self.event_bus = event_bus or EventBus()
        self._timer_tasks: dict[UUID, dict[str, asyncio.Task[None]]] = {}
        self._timer_lock = RLock()

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
        self._schedule_auto_start_timers(record)
        await upsert_session(record)
        logger.info("[SESSION] started session=%s scenario=%s", record.session_id, scenario.id)
        return record

    async def stop_session(self, session_id: UUID) -> SessionRecord:
        self._cancel_session_timers(session_id)
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
        await mark_session_stopped(session_id)
        logger.info("[SESSION] stopped session=%s", session_id)
        return record

    async def process_student_input(
        self,
        session_id: UUID,
        action_id: str,
        response: str | bool,
    ) -> SessionRecord:
        record = self._get_active_session(session_id)
        self._ensure_running(record)
        previous_state_id = record.engine.serialize()["current_state_id"]
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
        self._schedule_auto_start_timers(record, previous_state_id)
        if record.engine.get_history()[-1].type == "state_transition":
            await upsert_session(record)
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
        previous_state_id = record.engine.serialize()["current_state_id"]
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
        self._schedule_auto_start_timers(record, previous_state_id)
        if record.engine.get_history()[-1].type == "state_transition":
            await upsert_session(record)
        return record

    async def process_timer(
        self,
        session_id: UUID,
        timer_id: str,
    ) -> SessionRecord:
        record = self._get_active_session(session_id)
        self._ensure_running(record)
        previous_state_id = record.engine.serialize()["current_state_id"]
        logger.info("[TIMER] fired timer=%s session=%s state=%s", timer_id, session_id, previous_state_id)
        state = record.engine.process_timer_event(timer_id)
        self._touch(record)
        logger.info("[TIMER] processed timer=%s → state=%s", timer_id, state.current_state_id)
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
        self._schedule_auto_start_timers(record, previous_state_id)
        if record.engine.get_history()[-1].type == "state_transition":
            await upsert_session(record)
        return record

    async def process_instructor_action(
        self,
        session_id: UUID,
        event_name: str,
    ) -> SessionRecord:
        record = self._get_active_session(session_id)
        self._ensure_running(record)
        previous_state_id = record.engine.serialize()["current_state_id"]
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
        self._schedule_auto_start_timers(record, previous_state_id)
        if record.engine.get_history()[-1].type == "state_transition":
            await upsert_session(record)
        return record

    async def restore_session(self, record: SessionRecord) -> None:
        with self.session_manager._lock:
            self.session_manager._sessions[record.session_id] = record
        self._schedule_auto_start_timers(record)
        await self.event_bus.publish(
            "session.restored",
            session_id=record.session_id,
            source="scenario_runner",
            aggregate_id=str(record.session_id),
            payload={
                "scenario_id": record.scenario.id,
                "current_state_id": record.engine.get_current_state().id,
            },
        )

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

    def _schedule_auto_start_timers(
        self,
        record: SessionRecord,
        previous_state_id: str | None = None,
    ) -> None:
        current_state = record.engine.get_current_state()
        if previous_state_id == current_state.id:
            return

        self._cancel_session_timers(record.session_id)

        auto_start_timers = [
            timer for timer in current_state.timers if timer.auto_start
        ]
        if not auto_start_timers:
            return

        with self._timer_lock:
            session_tasks = self._timer_tasks.setdefault(record.session_id, {})
            for timer in auto_start_timers:
                logger.info("[TIMER] scheduled timer=%s duration=%ds session=%s state=%s", timer.id, timer.duration_seconds, record.session_id, current_state.id)
                session_tasks[timer.id] = asyncio.create_task(
                    self._run_auto_timer(
                        session_id=record.session_id,
                        timer_id=timer.id,
                        duration_seconds=timer.duration_seconds,
                    )
                )

    def _cancel_session_timers(self, session_id: UUID) -> None:
        current_task = asyncio.current_task()
        with self._timer_lock:
            session_tasks = self._timer_tasks.pop(session_id, {})

        for task in session_tasks.values():
            if task is not current_task and not task.done():
                task.cancel()

    async def _run_auto_timer(
        self,
        session_id: UUID,
        timer_id: str,
        duration_seconds: int,
    ) -> None:
        try:
            await asyncio.sleep(duration_seconds)
            logger.info("[TIMER] expiring timer=%s session=%s", timer_id, session_id)
            await self.process_timer(session_id=session_id, timer_id=timer_id)
        except asyncio.CancelledError:
            logger.debug("[TIMER] cancelled timer=%s session=%s", timer_id, session_id)
            raise
        except (KeyError, RuntimeError):
            return
        finally:
            current_task = asyncio.current_task()
            with self._timer_lock:
                session_tasks = self._timer_tasks.get(session_id)
                if session_tasks is None:
                    return

                if session_tasks.get(timer_id) is current_task:
                    session_tasks.pop(timer_id, None)

                if not session_tasks:
                    self._timer_tasks.pop(session_id, None)
