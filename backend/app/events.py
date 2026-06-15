from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable
from datetime import datetime, timezone
from inspect import isawaitable
from threading import RLock
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


HandlerResult = Awaitable[None] | None


class EventHandler(Protocol):
    def __call__(self, event: "EventEnvelope") -> HandlerResult:
        ...


class EventEnvelope(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    sequence: int | None = None
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "runtime"
    session_id: UUID | None = None
    aggregate_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._history: list[EventEnvelope] = []
        self._subscribers: dict[str, dict[UUID, EventHandler]] = defaultdict(dict)
        self._subscription_index: dict[UUID, str] = {}
        self._next_sequence = 1
        self._lock = RLock()

    async def publish(
        self,
        event: EventEnvelope | str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "runtime",
        session_id: UUID | None = None,
        aggregate_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        dispatch: bool = True,
    ) -> EventEnvelope:
        envelope = self._build_envelope(
            event=event,
            payload=payload,
            source=source,
            session_id=session_id,
            aggregate_id=aggregate_id,
            metadata=metadata,
        )

        with self._lock:
            stored_event = envelope.model_copy(
                update={"sequence": self._next_sequence}
            )
            self._next_sequence += 1
            self._history.append(stored_event)

        if dispatch:
            await self.dispatch(stored_event)

        return stored_event

    def subscribe(self, event_type: str, handler: EventHandler) -> UUID:
        subscription_id = uuid4()

        with self._lock:
            self._subscribers[event_type][subscription_id] = handler
            self._subscription_index[subscription_id] = event_type

        return subscription_id

    def unsubscribe(self, subscription_id: UUID) -> bool:
        with self._lock:
            event_type = self._subscription_index.pop(subscription_id, None)
            if event_type is None:
                return False

            self._subscribers[event_type].pop(subscription_id, None)
            if not self._subscribers[event_type]:
                self._subscribers.pop(event_type, None)

            return True

    async def dispatch(self, event: EventEnvelope) -> None:
        handlers = self._get_handlers(event.event_type)

        for handler in handlers:
            result = handler(event)
            if isawaitable(result):
                await result

    async def replay(
        self,
        *,
        event_type: str | None = None,
        session_id: UUID | None = None,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
        dispatch: bool = False,
    ) -> list[EventEnvelope]:
        events = self.get_history(
            event_type=event_type,
            session_id=session_id,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
        )

        if dispatch:
            for event in events:
                await self.dispatch(event)

        return events

    def get_history(
        self,
        *,
        event_type: str | None = None,
        session_id: UUID | None = None,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
    ) -> list[EventEnvelope]:
        with self._lock:
            events = list(self._history)

        return [
            event
            for event in events
            if self._matches_filter(
                event,
                event_type=event_type,
                session_id=session_id,
                from_sequence=from_sequence,
                to_sequence=to_sequence,
            )
        ]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
            self._next_sequence = 1

    def _build_envelope(
        self,
        event: EventEnvelope | str,
        payload: dict[str, Any] | None,
        source: str,
        session_id: UUID | None,
        aggregate_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> EventEnvelope:
        if isinstance(event, EventEnvelope):
            return event

        return EventEnvelope(
            event_type=event,
            source=source,
            session_id=session_id,
            aggregate_id=aggregate_id,
            payload=payload or {},
            metadata=metadata or {},
        )

    def _get_handlers(self, event_type: str) -> list[EventHandler]:
        with self._lock:
            exact_handlers = list(self._subscribers.get(event_type, {}).values())
            wildcard_handlers = list(self._subscribers.get("*", {}).values())

        return exact_handlers + wildcard_handlers

    def _matches_filter(
        self,
        event: EventEnvelope,
        *,
        event_type: str | None,
        session_id: UUID | None,
        from_sequence: int | None,
        to_sequence: int | None,
    ) -> bool:
        if event_type is not None and event.event_type != event_type:
            return False

        if session_id is not None and event.session_id != session_id:
            return False

        if from_sequence is not None and (
            event.sequence is None or event.sequence < from_sequence
        ):
            return False

        if to_sequence is not None and (
            event.sequence is None or event.sequence > to_sequence
        ):
            return False

        return True
