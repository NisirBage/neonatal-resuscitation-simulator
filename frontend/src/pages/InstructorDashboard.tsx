import { useCallback, useEffect, useRef, useState } from "react";

import { ConnectionStatusBadge } from "../components/ConnectionStatusBadge";
import { EventPanel } from "../components/EventPanel";
import { InstructorOverridePanel } from "../components/InstructorOverridePanel";
import { StateCard } from "../components/StateCard";
import { useTimerCountdown } from "../hooks/useTimerCountdown";
import {
  downloadSessionCsv,
  getSession,
  listSessions,
  sendInstructorEvent,
  stopSession,
  triggerTimer
} from "../services/api";
import { createInstructorSocket, type WebSocketHandle } from "../services/websocket";
import type { ActiveSessionItem, CurrentState, RuntimeEvent } from "../types";

const MAX_EVENTS = 40;
const REFRESH_EVENT_TYPES = new Set(["fsm.state_transition", "timer.expired"]);
const POLL_INTERVAL_MS = 5000;

export function InstructorDashboard() {
  const [sessions, setSessions] = useState<ActiveSessionItem[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [currentState, setCurrentState] = useState<CurrentState | null>(null);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [websocketStatus, setWebsocketStatus] = useState("closed");
  const [busy, setBusy] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<WebSocketHandle | null>(null);
  const activeSessionIdRef = useRef("");
  const refreshSequenceRef = useRef(0);

  const activeTimer = useTimerCountdown(currentState);

  // ── Session state refresh ─────────────────────────────────────────────────
  const refreshSessionState = useCallback(async (sid: string) => {
    const seq = ++refreshSequenceRef.current;
    try {
      const session = await getSession(sid);
      if (activeSessionIdRef.current !== sid || refreshSequenceRef.current !== seq) return;
      setCurrentState(session.current_state);
    } catch (err) {
      if (activeSessionIdRef.current !== sid) return;
      setError(err instanceof Error ? `Unable to refresh session: ${err.message}` : "Unable to refresh session.");
    }
  }, []);

  // ── Session list polling ──────────────────────────────────────────────────
  useEffect(() => {
    const poll = async () => {
      try {
        const list = await listSessions();
        setSessions(list);
      } catch {
        // silent — backend may have no sessions yet
      }
    };
    void poll();
    const id = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, []);

  // ── WS connection + initial state load on session selection ───────────────
  useEffect(() => {
    if (!selectedSessionId) {
      socketRef.current?.close();
      socketRef.current = null;
      activeSessionIdRef.current = "";
      setCurrentState(null);
      setEvents([]);
      setWebsocketStatus("closed");
      return;
    }

    activeSessionIdRef.current = selectedSessionId;
    refreshSequenceRef.current = 0;
    setEvents([]);
    setError(null);

    void refreshSessionState(selectedSessionId);

    socketRef.current?.close();
    setWebsocketStatus("connecting");

    const socket = createInstructorSocket(
      selectedSessionId,
      (event) => {
        setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS));
        if (REFRESH_EVENT_TYPES.has(event.type)) {
          void refreshSessionState(selectedSessionId);
        }
      },
      (status) => setWebsocketStatus(status)
    );
    socketRef.current = socket;

    return () => {
      activeSessionIdRef.current = "";
      socket.close();
    };
  }, [selectedSessionId, refreshSessionState]);

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleSendEvent = async (eventName: string) => {
    if (!selectedSessionId) return;
    setBusy(true);
    setError(null);
    try {
      const session = await sendInstructorEvent(selectedSessionId, eventName);
      setCurrentState(session.current_state);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Instructor event failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleTriggerTimer = async (timerId: string) => {
    if (!selectedSessionId) return;
    setBusy(true);
    setError(null);
    try {
      const session = await triggerTimer(selectedSessionId, timerId);
      setCurrentState(session.current_state);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Timer trigger failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleExportCsv = async () => {
    if (!selectedSessionId) return;
    setExportingCsv(true);
    setError(null);
    try {
      const blob = await downloadSessionCsv(selectedSessionId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `session_${selectedSessionId}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "CSV export failed.");
    } finally {
      setExportingCsv(false);
    }
  };

  const handleStopSession = async () => {
    if (!selectedSessionId) return;
    setBusy(true);
    setError(null);
    try {
      await stopSession(selectedSessionId);
      setSelectedSessionId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stop session failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleSelectSession = (sid: string) => {
    setSelectedSessionId(sid);
    setError(null);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <main className="min-h-screen bg-clinical-panel text-clinical-ink">
      <header className="border-b border-clinical-line bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-amber-600">
              Neonatal Resuscitation Simulator
            </p>
            <h1 className="mt-1 text-2xl font-semibold">Instructor Console</h1>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <select
              className="rounded-md border border-clinical-line bg-white px-3 py-2 text-sm text-clinical-ink outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-100"
              onChange={(e) => handleSelectSession(e.target.value)}
              value={selectedSessionId}
            >
              <option value="">— Select a session —</option>
              {sessions.map((s) => (
                <option key={s.session_id} value={s.session_id}>
                  {s.scenario_name} · {s.current_state_id} [{s.status}]
                </option>
              ))}
            </select>

            <button
              className="rounded-md border border-clinical-line bg-white px-4 py-2 text-sm font-semibold text-clinical-ink transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!selectedSessionId || exportingCsv || busy}
              onClick={() => void handleExportCsv()}
              type="button"
            >
              {exportingCsv ? "Exporting…" : "Export CSV"}
            </button>

            <button
              className="rounded-md border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-800 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy || !selectedSessionId}
              onClick={() => void handleStopSession()}
              type="button"
            >
              Stop Session
            </button>

            <ConnectionStatusBadge websocketStatus={websocketStatus} />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {error ? (
          <div className="mb-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
            {error}
          </div>
        ) : null}

        {!selectedSessionId ? (
          <div className="rounded-lg border border-clinical-line bg-white p-10 text-center shadow-soft">
            <p className="text-lg font-semibold text-clinical-ink">
              Select a session above to begin monitoring.
            </p>
            <p className="mt-2 text-sm text-slate-500">
              {sessions.length === 0
                ? "No active sessions. Ask the student to start a session first."
                : `${sessions.length} active session${sessions.length === 1 ? "" : "s"} available.`}
            </p>
            <p className="mt-4 text-xs text-slate-400">
              Session list refreshes automatically every {POLL_INTERVAL_MS / 1000} seconds.
            </p>
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-6">
              <StateCard
                activeTimer={activeTimer}
                state={currentState}
                websocketStatus={websocketStatus}
              />
              <InstructorOverridePanel
                busy={busy}
                currentState={currentState}
                onSendEvent={handleSendEvent}
                onTriggerTimer={handleTriggerTimer}
              />
            </div>

            <aside className="space-y-6">
              <section className="rounded-lg border border-clinical-line bg-white p-5 shadow-soft">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Session Info
                </h2>
                <dl className="mt-3 space-y-2 text-sm">
                  <div className="grid grid-cols-[90px_minmax(0,1fr)] gap-2">
                    <dt className="font-medium text-slate-500">Session ID</dt>
                    <dd className="break-all font-mono text-xs text-clinical-ink">
                      {selectedSessionId}
                    </dd>
                  </div>
                  <div className="grid grid-cols-[90px_minmax(0,1fr)] gap-2">
                    <dt className="font-medium text-slate-500">State ID</dt>
                    <dd className="font-mono text-xs text-clinical-ink">
                      {currentState?.id ?? "—"}
                    </dd>
                  </div>
                  <div className="grid grid-cols-[90px_minmax(0,1fr)] gap-2">
                    <dt className="font-medium text-slate-500">Transitions</dt>
                    <dd className="font-mono text-xs text-clinical-ink">
                      {currentState
                        ? `${currentState.transitions.filter((t) => t.trigger === "instructor").length} instructor / ${currentState.transitions.length} total`
                        : "—"}
                    </dd>
                  </div>
                </dl>
              </section>

              <EventPanel events={events} />
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}
