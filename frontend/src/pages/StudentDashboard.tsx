import { useEffect, useMemo, useRef, useState } from "react";

import { ActionPanel } from "../components/ActionPanel";
import { DemoModePanel } from "../components/DemoModePanel";
import { EventPanel } from "../components/EventPanel";
import { PerformanceReport } from "../components/PerformanceReport";
import { ProgressPanel } from "../components/ProgressPanel";
import { StateCard } from "../components/StateCard";
import { useTimerCountdown } from "../hooks/useTimerCountdown";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useSpeechSynthesis } from "../hooks/useSpeechSynthesis";
import {
  downloadSessionCsv,
  getSession,
  getSessionMetrics,
  listScenarios,
  startSession,
  stopSession,
  submitStudentInput,
  triggerTimer
} from "../services/api";
import { createStudentSocket } from "../services/websocket";
import type { ActionSummary, CurrentState, RuntimeEvent, ScenarioListItem, SessionMetrics } from "../types";

const DEFAULT_SCENARIO_ID = "baby_birth";
const MAX_EVENTS = 40;
const REFRESH_EVENT_TYPES = new Set(["fsm.state_transition", "timer.expired"]);

function normalizeSpokenResponse(text: string, action: ActionSummary | undefined): string {
  const normalized = text.trim().toLowerCase();

  if (/\b(yes|yeah|yep|correct|affirmative)\b/.test(normalized)) {
    return "yes";
  }

  if (/\b(no|nope|negative|incorrect)\b/.test(normalized)) {
    return "no";
  }

  if (/\b(under|below|less than)\s+(one\s+)?hundred\b/.test(normalized)) {
    return "under_100";
  }

  if (
    /\b((one\s+)?hundred\s+or\s+more|greater\s+than\s+(one\s+)?hundred|above\s+(one\s+)?hundred)\b/.test(
      normalized
    )
  ) {
    return "100_or_more";
  }

  if (/\b(under|below|less than)\s+sixty\b/.test(normalized)) {
    return "under_60";
  }

  return normalized.replace(/\s+/g, "_");
}

function promptForState(state: CurrentState): string {
  const actionPrompts = state.actions
    .map((action) => action.prompt)
    .filter((prompt): prompt is string => Boolean(prompt));

  return [state.name, state.description, actionPrompts[0]].filter(Boolean).join(". ");
}

export function StudentDashboard() {
  const [scenarios, setScenarios] = useState<ScenarioListItem[]>([]);
  const [scenarioId, setScenarioId] = useState(DEFAULT_SCENARIO_ID);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [currentState, setCurrentState] = useState<CurrentState | null>(null);
  const [selectedActionId, setSelectedActionId] = useState("");
  const [response, setResponse] = useState("");
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [websocketStatus, setWebsocketStatus] = useState("closed");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [metrics, setMetrics] = useState<SessionMetrics | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const activeSessionIdRef = useRef<string | null>(null);
  const refreshSequenceRef = useRef(0);

  const speechRecognition = useSpeechRecognition();
  const { cancel: cancelSpeech, speak, speaking, supported: speechOutputSupported } = useSpeechSynthesis();

  const selectedAction = useMemo(
    () => currentState?.actions.find((action) => action.id === selectedActionId),
    [currentState?.actions, selectedActionId]
  );

  const activeTimer = useTimerCountdown(currentState);
  const lastEventType = events[0]?.type ?? null;

  const addEvent = (event: RuntimeEvent) => {
    setEvents((existing) => [event, ...existing].slice(0, MAX_EVENTS));
  };

  useEffect(() => {
    listScenarios()
      .then((availableScenarios) => {
        setScenarios(availableScenarios);
        if (!availableScenarios.some((scenario) => scenario.id === scenarioId)) {
          setScenarioId(availableScenarios[0]?.id ?? DEFAULT_SCENARIO_ID);
        }
      })
      .catch((loadError: unknown) => {
        setError(loadError instanceof Error ? loadError.message : "Unable to load scenarios.");
      });
  }, [scenarioId]);

  useEffect(() => {
    if (!currentState) {
      setSelectedActionId("");
      setResponse("");
      return;
    }

    setSelectedActionId(currentState.actions[0]?.id ?? "");
    setResponse("");
    speak(promptForState(currentState));
  }, [currentState?.id, speak]);

  useEffect(() => {
    if (!speechRecognition.transcript || !selectedAction) {
      return;
    }

    setResponse(normalizeSpokenResponse(speechRecognition.transcript, selectedAction));
  }, [speechRecognition.transcript, selectedAction]);

  useEffect(() => {
    if (currentState?.id !== "simulation_complete" || !sessionId) {
      setMetrics(null);
      return;
    }
    getSessionMetrics(sessionId)
      .then(setMetrics)
      .catch(() => setMetrics(null));
  }, [currentState?.id, sessionId]);

  useEffect(() => {
    return () => {
      activeSessionIdRef.current = null;
      socketRef.current?.close();
      cancelSpeech();
    };
  }, [cancelSpeech]);

  const refreshSessionState = async (targetSessionId: string) => {
    const refreshSequence = refreshSequenceRef.current + 1;
    refreshSequenceRef.current = refreshSequence;

    try {
      const session = await getSession(targetSessionId);
      if (
        activeSessionIdRef.current !== targetSessionId ||
        refreshSequenceRef.current !== refreshSequence
      ) {
        return;
      }

      setStatus(session.status);
      setCurrentState(session.current_state);
    } catch (refreshError: unknown) {
      if (activeSessionIdRef.current !== targetSessionId) {
        return;
      }

      setError(
        refreshError instanceof Error
          ? `Unable to refresh session state: ${refreshError.message}`
          : "Unable to refresh session state."
      );
    }
  };

  const connectWebSocket = (newSessionId: string) => {
    socketRef.current?.close();
    setWebsocketStatus("connecting");
    socketRef.current = createStudentSocket(
      newSessionId,
      (event) => {
        addEvent(event);
        if (REFRESH_EVENT_TYPES.has(event.type)) {
          void refreshSessionState(newSessionId);
        }
      },
      (newStatus) => setWebsocketStatus(newStatus)
    );
  };

  const handleStartSession = async () => {
    setBusy(true);
    setError(null);

    try {
      if (sessionId) {
        await stopSession(sessionId);
        socketRef.current?.close();
        activeSessionIdRef.current = null;
      }

      const session = await startSession(scenarioId);
      activeSessionIdRef.current = session.session_id;
      setSessionId(session.session_id);
      setStatus(session.status);
      setCurrentState(session.current_state);
      setEvents([]);
      addEvent({
        type: "ui.session_started",
        timestamp: new Date().toISOString(),
        payload: { session_id: session.session_id, scenario_id: session.scenario_id }
      });
      connectWebSocket(session.session_id);
    } catch (startError: unknown) {
      setError(startError instanceof Error ? startError.message : "Unable to start session.");
    } finally {
      setBusy(false);
    }
  };

  const handleStopSession = async () => {
    if (!sessionId) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const session = await stopSession(sessionId);
      activeSessionIdRef.current = null;
      setSessionId(null);
      setStatus("stopped");
      setCurrentState(session.current_state);
      socketRef.current?.close();
      addEvent({
        type: "ui.session_stopped",
        timestamp: new Date().toISOString(),
        payload: { session_id: sessionId }
      });
    } catch (stopError: unknown) {
      setError(stopError instanceof Error ? stopError.message : "Unable to stop session.");
    } finally {
      setBusy(false);
    }
  };

  const handleSubmitAction = async (action: ActionSummary, actionResponse: string) => {
    if (!sessionId) {
      setError("Start a session before submitting an action.");
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const session = await submitStudentInput(sessionId, action.id, actionResponse.trim());
      setStatus(session.status);
      setCurrentState(session.current_state);
      speechRecognition.resetTranscript();
      addEvent({
        type: "ui.student_input_submitted",
        timestamp: new Date().toISOString(),
        payload: { action_id: action.id, response: actionResponse.trim() }
      });
    } catch (submitError: unknown) {
      setError(submitError instanceof Error ? submitError.message : "Unable to submit action.");
    } finally {
      setBusy(false);
    }
  };

  const handleExportCsv = async () => {
    if (!sessionId) {
      setError("Start a session before exporting CSV.");
      return;
    }

    setExportingCsv(true);
    setError(null);

    try {
      const blob = await downloadSessionCsv(sessionId);
      const downloadUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = `session_${sessionId}.csv`;
      anchor.click();
      URL.revokeObjectURL(downloadUrl);
      addEvent({
        type: "ui.session_csv_exported",
        timestamp: new Date().toISOString(),
        payload: { session_id: sessionId }
      });
    } catch (exportError: unknown) {
      setError(
        exportError instanceof Error ? exportError.message : "Unable to export session CSV."
      );
    } finally {
      setExportingCsv(false);
    }
  };

  const handleTriggerTimer = async (timerId: string) => {
    if (!sessionId) {
      setError("Start a session before triggering a timer.");
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const session = await triggerTimer(sessionId, timerId);
      setStatus(session.status);
      setCurrentState(session.current_state);
      addEvent({
        type: "ui.timer_triggered",
        timestamp: new Date().toISOString(),
        payload: { timer_id: timerId }
      });
    } catch (timerError: unknown) {
      setError(timerError instanceof Error ? timerError.message : "Unable to trigger timer.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen bg-clinical-panel text-clinical-ink">
      <header className="border-b border-clinical-line bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-clinical-green">
              Neonatal Resuscitation Simulator
            </p>
            <h1 className="mt-1 text-2xl font-semibold">Student Console</h1>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <select
              className="rounded-md border border-clinical-line bg-white px-3 py-2 text-sm text-clinical-ink outline-none focus:border-clinical-green focus:ring-2 focus:ring-teal-100"
              disabled={busy || Boolean(sessionId)}
              onChange={(event) => setScenarioId(event.target.value)}
              value={scenarioId}
            >
              {scenarios.length === 0 ? (
                <option value={scenarioId}>{scenarioId}</option>
              ) : (
                scenarios.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.name}
                  </option>
                ))
              )}
            </select>
            <button
              className="rounded-md bg-clinical-blue px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy}
              onClick={handleStartSession}
              type="button"
            >
              {sessionId ? "Restart Session" : "Start Session"}
            </button>
            <button
              className="rounded-md border border-clinical-line px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy || !sessionId}
              onClick={handleStopSession}
              type="button"
            >
              Stop
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:px-8">
        <div className="space-y-6">
          {error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
              {error}
            </div>
          ) : null}
          <StateCard
            activeTimer={activeTimer}
            state={currentState}
            websocketStatus={websocketStatus}
          />
          {metrics ? <PerformanceReport metrics={metrics} /> : null}
          <ActionPanel
            busy={busy}
            currentState={currentState}
            listening={speechRecognition.listening}
            onStartListening={speechRecognition.startListening}
            onStopListening={speechRecognition.stopListening}
            onSubmitAction={handleSubmitAction}
            onTriggerTimer={handleTriggerTimer}
            response={response}
            selectedActionId={selectedActionId}
            setResponse={setResponse}
            setSelectedActionId={setSelectedActionId}
            speechError={speechRecognition.error}
            speechSupported={speechRecognition.supported}
          />
          <p className="text-sm text-slate-500">
            Voice output: {speechOutputSupported ? (speaking ? "speaking" : "ready") : "not supported"}
          </p>
        </div>

        <aside className="space-y-6">
          <DemoModePanel
            activeTimer={activeTimer}
            currentState={currentState}
            exportingCsv={exportingCsv}
            lastEventType={lastEventType}
            onExportCsv={() => void handleExportCsv()}
            sessionId={sessionId}
            websocketStatus={websocketStatus}
          />
          <ProgressPanel
            currentState={currentState}
            scenarioId={scenarioId}
            sessionId={sessionId}
            status={status}
          />
          <EventPanel events={events} />
        </aside>
      </div>
    </main>
  );
}
