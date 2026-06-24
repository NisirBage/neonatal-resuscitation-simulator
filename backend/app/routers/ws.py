from typing import Literal
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.routers.sessions import scenario_runner, session_manager
from app.ws_manager import ConnectionInfo, WebSocketManager


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
    connection = await _connect(websocket, session_id, role)
    await websocket_manager.send_personal_message(
        connection.connection_id,
        {
            "type": "connection.accepted",
            "session_id": str(session_id),
            "connection_id": str(connection.connection_id),
            "role": role,
        },
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await websocket_manager.disconnect(connection.connection_id)


async def _connect(
    websocket: WebSocket,
    session_id: UUID,
    role: Literal["student", "instructor"],
) -> ConnectionInfo:
    if role == "student":
        return await websocket_manager.connect_student(session_id, websocket)

    return await websocket_manager.connect_instructor(session_id, websocket)
