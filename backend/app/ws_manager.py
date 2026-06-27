from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from app.events import EventBus, EventEnvelope
from app.scenario_runner import ScenarioRunner
from app.session_service import SessionManager

logger = logging.getLogger(__name__)


ConnectionRole = Literal["student", "instructor"]


class ConnectionInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    connection_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    role: ConnectionRole
    websocket: WebSocket
    connected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionRoom(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: UUID
    students: dict[UUID, ConnectionInfo] = Field(default_factory=dict)
    instructors: dict[UUID, ConnectionInfo] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def connection_count(self) -> int:
        return len(self.students) + len(self.instructors)


class WebSocketManager:
    def __init__(
        self,
        event_bus: EventBus | None = None,
        session_manager: SessionManager | None = None,
        scenario_runner: ScenarioRunner | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.scenario_runner = scenario_runner
        self.session_manager = (
            session_manager
            if session_manager is not None
            else scenario_runner.session_manager if scenario_runner is not None else None
        )
        self._rooms: dict[UUID, SessionRoom] = {}
        self._connection_index: dict[UUID, UUID] = {}
        self._event_subscription_id: UUID | None = None
        self._lock = RLock()

    async def connect_student(
        self,
        session_id: UUID,
        websocket: WebSocket,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectionInfo:
        return await self._connect(
            session_id=session_id,
            websocket=websocket,
            role="student",
            metadata=metadata,
        )

    async def connect_instructor(
        self,
        session_id: UUID,
        websocket: WebSocket,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectionInfo:
        return await self._connect(
            session_id=session_id,
            websocket=websocket,
            role="instructor",
            metadata=metadata,
        )

    async def disconnect(self, connection_id: UUID) -> bool:
        with self._lock:
            session_id = self._connection_index.pop(connection_id, None)
            if session_id is None:
                logger.debug("[WS_MGR] disconnect called for unknown conn=%s (already removed)", connection_id)
                return False

            room = self._rooms.get(session_id)
            if room is None:
                return False

            connection = room.students.pop(connection_id, None)
            if connection is None:
                connection = room.instructors.pop(connection_id, None)

            room.updated_at = datetime.now(timezone.utc)
            should_cleanup = room.connection_count == 0
            if should_cleanup:
                self._rooms.pop(session_id, None)

        logger.info("[WS_MGR] disconnecting conn=%s session=%s", connection_id, session_id)
        if connection is not None:
            await self._close_websocket(connection.websocket)

        return True

    async def broadcast_to_session(
        self,
        session_id: UUID,
        message: dict[str, Any],
    ) -> None:
        room = self.get_room(session_id)
        if room is None:
            return

        connections = list(room.students.values()) + list(room.instructors.values())
        await self._send_to_connections(connections, message)

    async def broadcast_to_students(
        self,
        session_id: UUID,
        message: dict[str, Any],
    ) -> None:
        room = self.get_room(session_id)
        if room is None:
            return

        await self._send_to_connections(list(room.students.values()), message)

    async def broadcast_to_instructors(
        self,
        session_id: UUID,
        message: dict[str, Any],
    ) -> None:
        room = self.get_room(session_id)
        if room is None:
            return

        await self._send_to_connections(list(room.instructors.values()), message)

    async def send_personal_message(
        self,
        connection_id: UUID,
        message: dict[str, Any],
    ) -> bool:
        connection = self._get_connection(connection_id)
        if connection is None:
            return False

        try:
            await connection.websocket.send_json(message)
            return True
        except (RuntimeError, WebSocketDisconnect) as exc:
            logger.warning("[WS_MGR] send_personal_message failed conn=%s exc=%r — disconnecting", connection_id, exc)
            await self.disconnect(connection_id)
            return False
        except Exception:
            logger.exception("[WS_MGR] send_personal_message unexpected error conn=%s — disconnecting", connection_id)
            await self.disconnect(connection_id)
            return False

    def get_room(self, session_id: UUID) -> SessionRoom | None:
        with self._lock:
            room = self._rooms.get(session_id)
            if room is None:
                return None

            return room.model_copy(
                update={
                    "students": dict(room.students),
                    "instructors": dict(room.instructors),
                },
                deep=False,
            )

    def list_active_sessions(self) -> list[UUID]:
        with self._lock:
            return list(self._rooms.keys())

    def subscribe_to_events(self) -> UUID:
        with self._lock:
            if self._event_subscription_id is not None:
                return self._event_subscription_id

            self._event_subscription_id = self.event_bus.subscribe(
                "*",
                self._handle_event,
            )
            return self._event_subscription_id

    def unsubscribe_from_events(self) -> bool:
        with self._lock:
            subscription_id = self._event_subscription_id
            if subscription_id is None:
                return False

            self._event_subscription_id = None

        return self.event_bus.unsubscribe(subscription_id)

    async def _connect(
        self,
        session_id: UUID,
        websocket: WebSocket,
        role: ConnectionRole,
        metadata: dict[str, Any] | None,
    ) -> ConnectionInfo:
        await websocket.accept()
        connection = ConnectionInfo(
            session_id=session_id,
            role=role,
            websocket=websocket,
            metadata=metadata or {},
        )

        with self._lock:
            room = self._rooms.setdefault(session_id, SessionRoom(session_id=session_id))
            if role == "student":
                room.students[connection.connection_id] = connection
            else:
                room.instructors[connection.connection_id] = connection

            room.updated_at = datetime.now(timezone.utc)
            self._connection_index[connection.connection_id] = session_id

        return connection

    async def _handle_event(self, event: EventEnvelope) -> None:
        if event.session_id is None:
            return

        message = {
            "type": event.event_type,
            "event_id": str(event.id),
            "sequence": event.sequence,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "payload": event.payload,
            "metadata": event.metadata,
        }

        try:
            if self._is_instructor_only_event(event.event_type):
                await self.broadcast_to_instructors(event.session_id, message)
                return

            await self.broadcast_to_session(event.session_id, message)
        except Exception:
            logger.exception("[WS_MGR] _handle_event failed event_type=%s session=%s", event.event_type, event.session_id)

    def _is_instructor_only_event(self, event_type: str) -> bool:
        return event_type.startswith("analytics.")

    def _get_connection(self, connection_id: UUID) -> ConnectionInfo | None:
        with self._lock:
            session_id = self._connection_index.get(connection_id)
            if session_id is None:
                return None

            room = self._rooms.get(session_id)
            if room is None:
                return None

            return room.students.get(connection_id) or room.instructors.get(
                connection_id
            )

    async def _send_to_connections(
        self,
        connections: list[ConnectionInfo],
        message: dict[str, Any],
    ) -> None:
        disconnected: list[UUID] = []

        for connection in connections:
            try:
                await connection.websocket.send_json(message)
            except (RuntimeError, WebSocketDisconnect) as exc:
                logger.warning("[WS_MGR] send failed conn=%s exc=%r — queuing disconnect", connection.connection_id, exc)
                disconnected.append(connection.connection_id)
            except Exception:
                logger.exception("[WS_MGR] send unexpected error conn=%s — queuing disconnect", connection.connection_id)
                disconnected.append(connection.connection_id)

        for connection_id in disconnected:
            await self.disconnect(connection_id)

    async def _close_websocket(self, websocket: WebSocket) -> None:
        logger.info("[WS_MGR] closing websocket state=%s", getattr(websocket, 'client_state', '?'))
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect) as exc:
            logger.debug("[WS_MGR] close raised (expected if already closed): %r", exc)
            return
        except Exception:
            logger.exception("[WS_MGR] close raised unexpected error")
            return
