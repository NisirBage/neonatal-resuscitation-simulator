import type { RuntimeEvent } from "../types";

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000";

function createSocket(
  url: string,
  onEvent: (event: RuntimeEvent) => void,
  onStatus?: (status: "connected" | "closed" | "error") => void
): WebSocket {
  const socket = new WebSocket(url);
  socket.onopen = () => onStatus?.("connected");
  socket.onclose = () => onStatus?.("closed");
  socket.onerror = () => onStatus?.("error");
  socket.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as RuntimeEvent);
    } catch {
      onEvent({
        type: "websocket.unparseable_message",
        payload: { raw: String(message.data) }
      });
    }
  };
  return socket;
}

export function createStudentSocket(
  sessionId: string,
  onEvent: (event: RuntimeEvent) => void,
  onStatus?: (status: "connected" | "closed" | "error") => void
): WebSocket {
  return createSocket(
    `${WS_BASE_URL}/api/ws/sessions/${sessionId}/student`,
    onEvent,
    onStatus
  );
}

export function createInstructorSocket(
  sessionId: string,
  onEvent: (event: RuntimeEvent) => void,
  onStatus?: (status: "connected" | "closed" | "error") => void
): WebSocket {
  return createSocket(
    `${WS_BASE_URL}/api/ws/sessions/${sessionId}/instructor`,
    onEvent,
    onStatus
  );
}
