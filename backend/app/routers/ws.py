import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.routers.sessions import scenario_runner, session_manager
from app.ws_manager import ConnectionInfo, WebSocketManager

logger = logging.getLogger(__name__)

router = APIRouter()

websocket_manager = WebSocketManager(
    event_bus=scenario_runner.event_bus,
    session_manager=session_manager,
    scenario_runner=scenario_runner,
)
websocket_manager.subscribe_to_events()


@router.websocket("/sessions/{session_id}/{role}")
async def session_websocket(
    websocket: WebSocket,
    session_id: UUID,
    role: Literal["student", "instructor"],
) -> None:
    logger.info("[WS] connecting session=%s role=%s", session_id, role)
    connection = await _connect(websocket, session_id, role)
    logger.info("[WS] accepted session=%s conn=%s", session_id, connection.connection_id)

    sent = await websocket_manager.send_personal_message(
        connection.connection_id,
        {
            "type": "connection.accepted",
            "session_id": str(session_id),
            "connection_id": str(connection.connection_id),
            "role": role,
        },
    )
    logger.info("[WS] connection.accepted sent=%s session=%s conn=%s", sent, session_id, connection.connection_id)

    try:
        while True:
            text = await websocket.receive_text()
            logger.debug("[WS] received session=%s text=%r", session_id, text[:80] if text else "")
            # Silently discard client keepalive pings — they exist only to prevent
            # Railway/nginx proxy from closing idle connections after 60 s.
            # All other client messages are also discarded; the backend is server-push only.
    except WebSocketDisconnect as exc:
        logger.info("[WS] client disconnected session=%s conn=%s code=%s", session_id, connection.connection_id, exc.code)
        await websocket_manager.disconnect(connection.connection_id)
    except Exception:
        logger.exception("[WS] unexpected error in receive loop session=%s conn=%s", session_id, connection.connection_id)
        await websocket_manager.disconnect(connection.connection_id)


async def _connect(
    websocket: WebSocket,
    session_id: UUID,
    role: Literal["student", "instructor"],
) -> ConnectionInfo:
    if role == "student":
        return await websocket_manager.connect_student(session_id, websocket)

    return await websocket_manager.connect_instructor(session_id, websocket)
