import type { RuntimeEvent } from "../types";

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000";

export type WsStatus = "connected" | "connecting" | "reconnecting" | "closed" | "error";

/** Opaque handle returned by createStudentSocket / createInstructorSocket. */
export interface WebSocketHandle {
  close(): void;
}

/**
 * Creates a WebSocket that automatically reconnects after unexpected closure
 * using exponential backoff (1 s → 2 s → 4 s … capped at 30 s).
 *
 * Status transitions:
 *   initial connect  → "connecting"
 *   onopen           → "connected"
 *   unexpected close → "reconnecting"  (schedules retry)
 *   explicit close() → "closed"
 */
function createReconnectingSocket(
  url: string,
  onEvent: (event: RuntimeEvent) => void,
  onStatus: (status: WsStatus) => void
): WebSocketHandle {
  let ws: WebSocket | null = null;
  let stopped = false;
  let attempt = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  // Keepalive: Railway/nginx proxies close idle WebSocket connections after ~60 s.
  // Sending a ping every 25 s keeps the connection alive with no visible side-effect
  // (the backend's receive_text() loop discards the message).
  let pingInterval: ReturnType<typeof setInterval> | null = null;

  function clearPing(): void {
    if (pingInterval !== null) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
  }

  function connect(): void {
    if (stopped) return;

    onStatus("connecting");
    ws = new WebSocket(url);

    ws.onopen = () => {
      attempt = 0;
      onStatus("connected");
      pingInterval = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, 25_000);
    };

    ws.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data) as RuntimeEvent);
      } catch {
        onEvent({
          type: "websocket.unparseable_message",
          payload: { raw: String(message.data) },
        });
      }
    };

    ws.onerror = () => {
      // onerror always fires before onclose — handle reconnect in onclose.
    };

    ws.onclose = () => {
      clearPing();
      if (stopped) {
        onStatus("closed");
        return;
      }
      // Exponential backoff: 1s, 2s, 4s, 8s, 16s, capped at 30s.
      const delayMs = Math.min(1_000 * Math.pow(2, attempt), 30_000);
      attempt++;
      onStatus("reconnecting");
      retryTimer = setTimeout(connect, delayMs);
    };
  }

  connect();

  return {
    close(): void {
      stopped = true;
      clearPing();
      if (retryTimer !== null) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
      ws?.close();
    },
  };
}

export function createStudentSocket(
  sessionId: string,
  onEvent: (event: RuntimeEvent) => void,
  onStatus?: (status: WsStatus) => void
): WebSocketHandle {
  return createReconnectingSocket(
    `${WS_BASE_URL}/api/ws/sessions/${sessionId}/student`,
    onEvent,
    onStatus ?? (() => {})
  );
}

export function createInstructorSocket(
  sessionId: string,
  onEvent: (event: RuntimeEvent) => void,
  onStatus?: (status: WsStatus) => void
): WebSocketHandle {
  return createReconnectingSocket(
    `${WS_BASE_URL}/api/ws/sessions/${sessionId}/instructor`,
    onEvent,
    onStatus ?? (() => {})
  );
}
