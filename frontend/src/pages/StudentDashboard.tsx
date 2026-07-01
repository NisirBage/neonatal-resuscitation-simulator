import { useCallback, useEffect, useRef, useState } from "react";

import { ConnectionStatusBadge } from "../components/ConnectionStatusBadge";
import { PerformanceReport } from "../components/PerformanceReport";
import { SessionReplay } from "../components/SessionReplay";
import { useTimerCountdown } from "../hooks/useTimerCountdown";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useSpeechSynthesis } from "../hooks/useSpeechSynthesis";
import { useVoiceReliability, addLifecycleListeners } from "../hooks/useVoiceReliability";
import { useNoiseDetector } from "../hooks/useNoiseDetector";
import { normalizeToYesNo } from "../services/voice/normalize";
import { voiceTelemetry, detectBrowser, detectOS } from "../services/voiceTelemetry";
import {
  downloadClinicalCsv,
  downloadClinicalXlsx,
  downloadSessionCsv,
  downloadSessionPdf,
  getSession,
  getSessionMetrics,
  listScenarios,
  startSession,
  stopSession,
  submitStudentInput,
} from "../services/api";
import { createStudentSocket, type WebSocketHandle } from "../services/websocket";
import { PROFESSOR_WORKFLOW_STEPS, getWorkflowStepStatus } from "../constants/demoWorkflow";
import type { CurrentState, ScenarioListItem, SessionMetrics } from "../types";

// ── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_SCENARIO_ID = "baby_birth";

// ── Voice-pipeline logger ────────────────────────────────────────────────────
// Prefixed console output makes filtering trivial in browser devtools.
// Each event maps to one of the 10 audit categories.
function vlog(category: string, msg: string, data?: unknown): void {
  const ts = new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  if (data !== undefined) {
    console.log(`[NRS ${ts}] [${category}] ${msg}`, data);
  } else {
    console.log(`[NRS ${ts}] [${category}] ${msg}`);
  }
}

type ErrorContext = "start" | "stop" | "submit" | "load" | "report";

function friendlyError(err: unknown, context: ErrorContext): string {
  if (!(err instanceof Error)) return "An unexpected error occurred. Please try again.";
  const msg = err.message;

  if (
    msg === "Failed to fetch" ||
    msg.includes("NetworkError") ||
    msg.includes("ERR_CONNECTION") ||
    msg.includes("net::ERR")
  ) {
    return context === "load"
      ? "Cannot reach the backend. Check that the server is running and refresh the page."
      : "Cannot reach the backend. Check your connection and try again.";
  }

  if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
    if (context === "start") return "Scenario not found. Please refresh and try again.";
    return "Session not found — it may have expired after a server restart. Please start a new session.";
  }

  if (/50[0-9]/.test(msg)) {
    return "The server encountered an error. Please try again in a moment.";
  }

  return msg;
}
const REFRESH_EVENT_TYPES = new Set(["fsm.state_transition", "timer.expired"]);

// ── Helpers ──────────────────────────────────────────────────────────────────

function voicePrompt(state: CurrentState): string {
  const meta = state.metadata;
  if (typeof meta.voice_prompt === "string" && meta.voice_prompt.trim()) {
    let prompt = meta.voice_prompt.trim();
    if (prompt.includes("{TIME}")) {
      const t = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
      prompt = prompt.replace("{TIME}", t);
    }
    return prompt;
  }
  return state.description ?? state.name;
}

// Audible alarm using browser AudioContext — no external file required.
// birth_timer: 2-beep pattern every 60 s; ventilation_timer: 3-beep pattern on expiry.
function playAlarmBeep(frequency: number, duration: number, count: number): void {
  try {
    const Ctx = (window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext);
    const ctx = new Ctx();
    let time = ctx.currentTime;
    for (let i = 0; i < count; i++) {
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = frequency;
      gain.gain.setValueAtTime(0.5, time);
      gain.gain.exponentialRampToValueAtTime(0.001, time + duration);
      osc.start(time);
      osc.stop(time + duration);
      time += duration + 0.08;
    }
    setTimeout(() => void ctx.close(), (duration + 0.1) * count * 1000 + 200);
  } catch {
    // AudioContext unavailable — silent degradation
  }
}

// States that have an active ventilation countdown reminder timer
const VENT_TIMER_STATES = new Set(["ventilation_in_progress", "ventilation_corrective_steps", "continue_ventilation_15s"]);

// All states that belong to the active ventilation phase (for the continuous elapsed timer)
const VENT_PHASE_STATES = new Set([
  "ventilation_in_progress",
  "heart_rate_after_ventilation",
  "ventilation_corrective_steps",
  "continue_ventilation_15s",
]);

function hasPrimaryYesNo(state: CurrentState | null): boolean {
  if (!state) return false;
  return state.actions.some((a) => a.type === "yes_no" && !a.metadata.fallback_only);
}

function primaryYesNo(state: CurrentState | null) {
  if (!state) return null;
  return state.actions.find((a) => a.type === "yes_no" && !a.metadata.fallback_only) ?? null;
}

function primaryTextAction(state: CurrentState | null) {
  if (!state) return null;
  return state.actions.find((a) => a.type === "text") ?? null;
}

function isTerminal(state: CurrentState | null): boolean {
  return Boolean(state?.metadata.terminal) || state?.id === "simulation_complete" || state?.id === "routine_care";
}

function formatMMSS(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

type VoicePhase = "idle" | "speaking" | "listening" | "processing" | "complete" | "confirming";

// ── Component ────────────────────────────────────────────────────────────────

export function StudentDashboard() {
  // Session state
  const [scenarios, setScenarios]       = useState<ScenarioListItem[]>([]);
  const [scenarioId, setScenarioId]     = useState(DEFAULT_SCENARIO_ID);
  const [sessionId, setSessionId]       = useState<string | null>(null);
  const [currentState, setCurrentState] = useState<CurrentState | null>(null);
  const [wsStatus, setWsStatus]         = useState("closed");
  const [error, setError]               = useState<string | null>(null);
  const [busy, setBusy]                 = useState(false);
  const [metrics, setMetrics]           = useState<SessionMetrics | null>(null);
  const [showReplay, setShowReplay]     = useState(false);
  const [downloadingPdf, setDownloadingPdf]         = useState(false);
  const [exportingCsv, setExportingCsv]             = useState(false);
  const [exportingClinical, setExportingClinical]   = useState(false);
  const [exportingXlsx, setExportingXlsx]           = useState(false);

  // Voice UI state
  const [voicePhase, setVoicePhase]           = useState<VoicePhase>("idle");
  const [lastRecognized, setLastRecognized]   = useState("");
  const [lastConfidence, setLastConfidence]   = useState<number | null>(null);
  // null = no input yet in this state; true = last input was valid; false = invalid
  const [voiceInputValid, setVoiceInputValid] = useState<boolean | null>(null);
  // Dev panel metrics (only rendered when NRS_DEV=1 in localStorage)
  const [lastHttpStatus, setLastHttpStatus] = useState<number | null>(null);

  // Birth elapsed clock
  const [birthElapsed, setBirthElapsed]   = useState(0);
  const sessionStartRef                   = useRef<number | null>(null);
  const lastMinuteAnnouncedRef            = useRef(-1);

  // Continuous ventilation elapsed clock
  const [ventElapsed, setVentElapsed] = useState(0);
  const ventStartRef                  = useRef<number | null>(null);

  // Stable refs
  const sessionIdRef    = useRef<string | null>(null);
  const currentStateRef = useRef<CurrentState | null>(null);
  const busyRef         = useRef(false);
  const voicePhaseRef   = useRef<VoicePhase>("idle");
  const socketRef       = useRef<WebSocketHandle | null>(null);
  const activeSessionRef = useRef<string | null>(null);
  const refreshSeqRef   = useRef(0);
  // Tracks the FSM state id from the previous render cycle — used to disambiguate
  // simulation_complete (two entry paths produce different spoken conclusions).
  const prevStateIdRef  = useRef<string | null>(null);
  // Voice result handler lives in a ref; startContinuous gets a stable proxy to it
  const voiceHandlerRef = useRef<(text: string, confidence: number) => void>(() => {});

  useEffect(() => { sessionIdRef.current    = sessionId;    }, [sessionId]);
  useEffect(() => { currentStateRef.current = currentState; }, [currentState]);
  useEffect(() => { busyRef.current         = busy;         }, [busy]);
  useEffect(() => { voicePhaseRef.current   = voicePhase;   }, [voicePhase]);

  // Latency tracking refs (for telemetry — Part 6)
  const listenStartRef  = useRef<number | null>(null);
  const submitStartRef  = useRef<number | null>(null);
  const httpDoneRef     = useRef<number | null>(null);
  // Attempt counter within the current FSM state
  const attemptRef      = useRef(0);

  // Speech hooks
  const {
    supported: micSupported,
    error: micError,
    transcript: rawTranscript,
    startContinuous,
    stopContinuous,
    getGeneration,
  } = useSpeechRecognition();

  // Reliability layer (Parts 1, 3, 4, 9)
  const reliability = useVoiceReliability();

  // Noise detector (Part 5) — active only while listening
  const { noiseLevel, rms, warningMessage: noiseWarning } = useNoiseDetector(
    voicePhase === "listening"
  );

  const { speak, cancel: cancelSpeech, getSpeechToken } = useSpeechSynthesis();

  const activeTimer = useTimerCountdown(currentState);

  // Stable proxy — passed to startContinuous once, always delegates to latest handler
  const stableProxy = useCallback((text: string, confidence: number) => {
    voiceHandlerRef.current(text, confidence);
  }, []);

  // ── Scenarios on mount ────────────────────────────────────────────────────

  useEffect(() => {
    listScenarios()
      .then((list) => {
        setScenarios(list);
        if (list.length && !list.some((s) => s.id === scenarioId)) {
          setScenarioId(list[0]?.id ?? DEFAULT_SCENARIO_ID);
        }
      })
      .catch((err: unknown) => {
        setError(friendlyError(err, "load"));
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Metrics on completion ─────────────────────────────────────────────────

  useEffect(() => {
    if (!isTerminal(currentState) || !sessionId) { setMetrics(null); return; }
    getSessionMetrics(sessionId).then(setMetrics).catch(() => setMetrics(null));
  }, [currentState?.id, sessionId]);

  // ── Reset replay on session change ────────────────────────────────────────

  useEffect(() => { setShowReplay(false); }, [sessionId]);

  // ── Birth elapsed clock ───────────────────────────────────────────────────

  useEffect(() => {
    if (!sessionId) {
      setBirthElapsed(0);
      sessionStartRef.current = null;
      lastMinuteAnnouncedRef.current = -1;
      return;
    }
    sessionStartRef.current = Date.now();
    const iv = setInterval(() => {
      setBirthElapsed(Math.floor((Date.now() - (sessionStartRef.current ?? Date.now())) / 1000));
    }, 1000);
    return () => clearInterval(iv);
  }, [sessionId]);

  // ── Continuous ventilation elapsed clock ─────────────────────────────────
  // Starts when entering any ventilation phase state, persists across transitions
  // within the phase, stops and resets when leaving the phase or on new session.

  useEffect(() => {
    if (!sessionId) {
      ventStartRef.current = null;
      setVentElapsed(0);
      return;
    }
    const inVentPhase = currentState ? VENT_PHASE_STATES.has(currentState.id) : false;
    if (!inVentPhase) {
      if (ventStartRef.current !== null) {
        ventStartRef.current = null;
        setVentElapsed(0);
      }
      return;
    }
    // First entry into the ventilation phase: record start time
    if (ventStartRef.current === null) {
      ventStartRef.current = Date.now();
      setVentElapsed(0);
    }
    const iv = setInterval(() => {
      if (ventStartRef.current !== null) {
        setVentElapsed(Math.floor((Date.now() - ventStartRef.current) / 1000));
      }
    }, 1000);
    return () => clearInterval(iv);
  }, [currentState?.id, sessionId]);

  // ── Birth timer: alarm beep + announce every minute ──────────────────────
  // Audible 2-beep alarm fires at every 60-second boundary regardless of voice phase.
  // Voice announcement only interrupts when listening.

  useEffect(() => {
    if (!sessionId || birthElapsed === 0) return;
    // Audible alarm on every 60-second boundary
    if (birthElapsed % 60 === 0) {
      playAlarmBeep(880, 0.25, 2);
    }
    const mins = Math.floor(birthElapsed / 60);
    if (mins <= 0 || mins === lastMinuteAnnouncedRef.current) return;
    if (voicePhaseRef.current !== "listening") return;
    lastMinuteAnnouncedRef.current = mins;
    vlog("TIMER", `birth timer: ${mins} min — announcing`);
    stopContinuous();
    speak(`${mins} minute${mins !== 1 ? "s" : ""} since birth.`, () => {
      const _s = currentStateRef.current;
      if (sessionIdRef.current && (hasPrimaryYesNo(_s) || !!primaryTextAction(_s))) {
        setVoicePhase("listening");
        startContinuous(stableProxy);
      }
    });
  }, [birthElapsed, sessionId, speak, stopContinuous, startContinuous, stableProxy]);

  // ── Cleanup on unmount ────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      activeSessionRef.current = null;
      socketRef.current?.close();
      stopContinuous();
      cancelSpeech();
    };
  }, [stopContinuous, cancelSpeech]);

  // ── Browser lifecycle: pause SR when tab hidden, resume when restored (Part 10) ──

  useEffect(() => {
    if (!sessionId) return;
    const cleanup = addLifecycleListeners(
      () => {
        // Tab hidden — stop SR to avoid Chrome aborting it silently
        if (voicePhaseRef.current === "listening") {
          vlog("LIFECYCLE", "tab hidden — pausing recognition");
          stopContinuous();
        }
      },
      () => {
        // Tab restored — restart if we were listening
        if (voicePhaseRef.current === "listening" || voicePhaseRef.current === "idle") {
          const state = currentStateRef.current;
          if (sessionIdRef.current && (hasPrimaryYesNo(state) || !!primaryTextAction(state))) {
            vlog("LIFECYCLE", "tab restored — resuming recognition");
            listenStartRef.current = Date.now();
            setVoicePhase("listening");
            startContinuous(stableProxy);
          }
        }
      },
    );
    return cleanup;
  }, [sessionId, stopContinuous, startContinuous, stableProxy]);

  // ── Submit yes/no — shared by voice and YES/NO buttons ───────────────────

  const submitResponse = useCallback(
    async (sid: string, actionId: string, response: string) => {
      vlog("FSM", `submitting response: action=${actionId} response=${response}`);
      setBusy(true);
      busyRef.current = true;
      setVoicePhase("processing");
      setError(null);
      const prevStateId = currentStateRef.current?.id ?? null;
      try {
        const session = await submitStudentInput(sid, actionId, response);
        setLastHttpStatus(200);
        vlog("FSM", `transitioned to state: ${session.current_state.id}`, { name: session.current_state.name });
        setCurrentState(session.current_state);
        if (session.current_state.id === prevStateId) {
          // FSM produced no_transition — state ID unchanged so the voice loop effect
          // won't re-fire.  Re-prompt immediately so the pipeline doesn't deadlock.
          vlog("MIC", `no transition in state ${prevStateId} — re-prompting`);
          setVoicePhase("speaking");
          speak(voicePrompt(session.current_state), () => {
            const state = currentStateRef.current;
            if (sessionIdRef.current && (hasPrimaryYesNo(state) || !!primaryTextAction(state))) {
              vlog("MIC", "microphone ON — retry after no-transition");
              setVoicePhase("listening");
              startContinuous(stableProxy);
            } else {
              setVoicePhase("idle");
            }
          });
        }
        // voice loop re-triggers via currentState?.id effect when state DID change
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Submission failed.";
        setLastHttpStatus(0);
        vlog("FSM", `submission error: ${msg}`);
        setError(msg);
        speak("An error occurred. Please try again.", () => {
          const state = currentStateRef.current;
          if (sessionIdRef.current && (hasPrimaryYesNo(state) || !!primaryTextAction(state))) {
            setVoicePhase("listening");
            startContinuous(stableProxy);
          } else {
            setVoicePhase("idle");
          }
        });
      } finally {
        setBusy(false);
        busyRef.current = false;
      }
    },
    [speak, startContinuous, stableProxy]
  );

  // ── Speak prompt then auto-start listening ────────────────────────────────

  const speakThenListen = useCallback(
    (prompt: string) => {
      vlog("TTS", `speaking: "${prompt}"`);
      setVoicePhase("speaking");
      stopContinuous();
      speak(prompt, () => {
        vlog("TTS", "speech ended");
        const state = currentStateRef.current;
        if (sessionIdRef.current && (hasPrimaryYesNo(state) || !!primaryTextAction(state))) {
          vlog("MIC", "microphone ON — listening for response");
          listenStartRef.current = Date.now();
          setVoicePhase("listening");
          startContinuous(stableProxy);
        } else {
          vlog("MIC", "microphone OFF — no active action in current state");
          setVoicePhase("idle");
        }
      });
    },
    [speak, stopContinuous, startContinuous, stableProxy]
  );

  // ── Wire voice result handler ─────────────────────────────────────────────

  useEffect(() => {
    voiceHandlerRef.current = (rawText: string, confidence: number) => {
      vlog("MIC", `recognised: "${rawText}" confidence=${confidence.toFixed(2)}`);
      setLastRecognized(rawText);
      setLastConfidence(confidence);

      // Compute recognition latency
      const recognitionLatencyMs = listenStartRef.current !== null
        ? Date.now() - listenStartRef.current
        : null;

      // Text action early-exit: bypass yes/no normalization for states like ventilation_path
      {
        const _ts = currentStateRef.current;
        const _sid = sessionIdRef.current;
        const textAct = primaryTextAction(_ts);
        if (textAct && !busyRef.current && _sid) {
          const synonyms = textAct.metadata.text_synonyms as string[] | undefined;
          if (synonyms && synonyms.length > 0) {
            const matched = synonyms.find((s) => rawText.toLowerCase().includes(s));
            if (!matched) {
              vlog("MIC", `text action — no synonym match in "${rawText}", continuing to listen`);
              setVoiceInputValid(false);
              return;
            }
            const normalized = synonyms[0];
            vlog("MIC", `text action — matched "${matched}" → normalizing to "${normalized}"`);
            setVoiceInputValid(true);
            stopContinuous();
            setVoicePhase("processing");
            void submitResponse(_sid, textAct.id, normalized);
          } else {
            vlog("MIC", `text action — submitting raw transcript: "${rawText}"`);
            setVoiceInputValid(true);
            stopContinuous();
            setVoicePhase("processing");
            void submitResponse(_sid, textAct.id, rawText);
          }
          return;
        }
      }

      // Route through the reliability layer (Parts 1, 3, 4, 9)
      const action = reliability.processResult(rawText, confidence);
      vlog("MIC", `reliability action: ${action.type}`, action);

      const restartListening = () => {
        const state = currentStateRef.current;
        if (sessionIdRef.current && (hasPrimaryYesNo(state) || !!primaryTextAction(state))) {
          listenStartRef.current = Date.now();
          setVoicePhase("listening");
          startContinuous(stableProxy);
        } else {
          setVoicePhase("idle");
        }
      };

      if (action.type === "ignore" || action.type === "circuit_open") {
        if (action.type === "circuit_open") {
          vlog("MIC", "circuit breaker open — manual fallback active");
        }
        return;
      }

      if (action.type === "manual_fallback") {
        vlog("MIC", `MAX_RETRIES exhausted — showing manual fallback`);
        setVoiceInputValid(false);
        stopContinuous();
        setVoicePhase("idle");
        speak("Please use the YES or NO buttons to answer.", undefined);
        voiceTelemetry.record({
          sessionId: sessionIdRef.current ?? "",
          stateId:   currentStateRef.current?.id ?? "",
          attemptNumber: ++attemptRef.current,
          timestamp: Date.now(),
          recognitionLatencyMs, submitLatencyMs: null, transitionLatencyMs: null,
          retryCount: reliability.retryCount,
          confidence: confidence || null,
          outcome: "manual_fallback",
          normalized: "unknown",
          browser: detectBrowser(), os: detectOS(),
          micError: null, speechError: null,
          noiseLevel: noiseLevel ?? null, silenceDurationMs: null,
        });
        return;
      }

      if (action.type === "retry") {
        const msg = action.reason === "low_confidence"
          ? "I couldn't hear that clearly. Please answer yes or no."
          : "I didn't understand. Please answer yes or no.";
        vlog("MIC", `retry #${action.retryNumber}: ${action.reason}`);
        setVoiceInputValid(false);
        stopContinuous();
        setVoicePhase("speaking");
        speak(msg, restartListening);
        voiceTelemetry.record({
          sessionId: sessionIdRef.current ?? "",
          stateId:   currentStateRef.current?.id ?? "",
          attemptNumber: ++attemptRef.current,
          timestamp: Date.now(),
          recognitionLatencyMs, submitLatencyMs: null, transitionLatencyMs: null,
          retryCount: action.retryNumber,
          confidence: confidence || null,
          outcome: action.reason === "low_confidence" ? "rejected_low_confidence" : "retry_unknown",
          normalized: "unknown",
          browser: detectBrowser(), os: detectOS(),
          micError: null, speechError: null,
          noiseLevel: noiseLevel ?? null, silenceDurationMs: null,
        });
        return;
      }

      if (action.type === "confirm") {
        vlog("MIC", `medium confidence — asking confirmation: "${action.prompt}"`);
        setLastRecognized(action.normalised);
        stopContinuous();
        setVoicePhase("confirming");
        speak(action.prompt, () => {
          reliability.enterConfirmationMode(action.normalised);
          listenStartRef.current = Date.now();
          setVoicePhase("listening");
          startContinuous(stableProxy);
        });
        return;
      }

      // action.type === "accept"
      const { normalised } = action;
      vlog("MIC", `normalised → ${normalised.toUpperCase()} (confidence=${confidence.toFixed(2)})`);
      setVoiceInputValid(true);
      setLastRecognized(normalised);

      const state = currentStateRef.current;
      const sid   = sessionIdRef.current;
      if (!state || !sid || busyRef.current) return;

      const fsm_action = primaryYesNo(state);
      if (!fsm_action) return;

      vlog("MIC", "microphone OFF — response accepted, submitting");
      stopContinuous();
      submitStartRef.current = Date.now();
      void submitResponse(sid, fsm_action.id, normalised).then(() => {
        httpDoneRef.current = Date.now();
        const submitLatencyMs = submitStartRef.current !== null
          ? httpDoneRef.current - submitStartRef.current : null;
        reliability.recordSuccess();
        voiceTelemetry.record({
          sessionId: sid,
          stateId:   state.id,
          attemptNumber: ++attemptRef.current,
          timestamp: Date.now(),
          recognitionLatencyMs,
          submitLatencyMs,
          transitionLatencyMs: null, // set later via WS event timing
          retryCount: reliability.retryCount,
          confidence: confidence || null,
          outcome: action.type === "accept" ? "accepted" : "confirmation_accepted",
          normalized: normalised,
          browser: detectBrowser(), os: detectOS(),
          micError: null, speechError: null,
          noiseLevel: noiseLevel ?? null, silenceDurationMs: null,
        });
      });
    };
  }, [speak, stopContinuous, startContinuous, stableProxy, submitResponse, reliability, noiseLevel]);

  // ── Voice loop: re-fires whenever FSM state changes ───────────────────────

  useEffect(() => {
    // Capture and update the previous state for disambiguation logic below
    const prevStateId = prevStateIdRef.current;
    prevStateIdRef.current = currentState?.id ?? null;

    if (!currentState || !sessionId) {
      stopContinuous();
      cancelSpeech();
      setVoicePhase("idle");
      setLastRecognized("");
      setVoiceInputValid(null);
      return;
    }

    // Ventilation timer alarm: 3-beep pattern fires when leaving a vent-timer state.
    // This coincides with the 30/15-second ventilation timer expiring.
    if (prevStateId && VENT_TIMER_STATES.has(prevStateId) && currentState.id !== prevStateId) {
      vlog("TIMER", `ventilation timer alarm (left ${prevStateId})`);
      playAlarmBeep(660, 0.35, 3);
    }

    vlog("FSM", `state entered: ${currentState.id}`, { name: currentState.name, prev: prevStateId });
    // Reset reliability and voice input tracking on every new FSM state
    reliability.resetForNewState();
    attemptRef.current = 0;
    setVoiceInputValid(null);

    if (isTerminal(currentState)) {
      stopContinuous();
      setVoicePhase("complete");
      vlog("SESSION", `simulation complete — terminal state: ${currentState.id}`);
      // simulation_complete is reached via two paths:
      //   1. heart_rate_assessment (HR > 100, no ventilation) → say the HR prompt
      //   2. continue_ventilation_15s (ventilation succeeded) → that state already
      //      said "Continue ventilation for 15 seconds and stop", so stay silent here
      if (currentState.id !== "simulation_complete" || prevStateId !== "continue_ventilation_15s") {
        speak(voicePrompt(currentState));
      }
      return;
    }
    // Multi-part TTS: speak intro, wait, then speak main prompt and listen
    // (e.g. heart_rate_assessment: "Measure heart rate." → 3s → "Is HR > 100?")
    const parts = currentState.metadata.voice_prompt_parts as string[] | undefined;
    const partsDelay = typeof currentState.metadata.voice_prompt_parts_delay_ms === "number"
      ? currentState.metadata.voice_prompt_parts_delay_ms : 0;

    if (parts && parts.length >= 2) {
      vlog("TTS", `multi-part speak: "${parts[0]}" → ${partsDelay}ms → "${parts.slice(1).join(" ")}"`);
      setVoicePhase("speaking");
      stopContinuous();
      speak(parts[0], () => {
        setTimeout(() => speakThenListen(parts.slice(1).join(" ")), partsDelay);
      });
    } else {
      speakThenListen(voicePrompt(currentState));
    }
  // Only re-run on actual state/session changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentState?.id, sessionId]);

  // ── Emergency YES / NO buttons ────────────────────────────────────────────

  const handleButton = useCallback(
    (response: "yes" | "no") => {
      const state = currentStateRef.current;
      const sid   = sessionIdRef.current;
      if (!state || !sid || busyRef.current) return;
      const action = primaryYesNo(state);
      if (!action) return;
      stopContinuous();
      cancelSpeech();
      setLastRecognized(response);
      // Manual button clears circuit breaker and reliability state (Part 4)
      reliability.recordSuccess();
      void submitResponse(sid, action.id, response);
    },
    [stopContinuous, cancelSpeech, submitResponse, reliability]
  );

  // ── Text action fallback button (DONE / VENTILATION STARTED) ────────────────

  const handleTextButton = useCallback(() => {
    const state = currentStateRef.current;
    const sid   = sessionIdRef.current;
    if (!state || !sid || busyRef.current) return;
    const action = primaryTextAction(state);
    if (!action) return;
    const synonyms = action.metadata.text_synonyms as string[] | undefined;
    const response = synonyms?.[0] ?? "done";
    stopContinuous();
    cancelSpeech();
    void submitResponse(sid, action.id, response);
  }, [stopContinuous, cancelSpeech, submitResponse]);

  // ── Keyboard shortcuts Y / N — route through the same handleButton path (Part 4) ──

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (!currentStateRef.current || !sessionIdRef.current || busyRef.current) return;
      // Text action states: Y triggers DONE/VENTILATION STARTED, no N shortcut
      if (primaryTextAction(currentStateRef.current)) {
        if (e.key === "y" || e.key === "Y") { e.preventDefault(); handleTextButton(); }
        return;
      }
      // YES/NO action states: Y/N shortcuts
      if (!hasPrimaryYesNo(currentStateRef.current)) return;
      if (e.key === "y" || e.key === "Y") { e.preventDefault(); handleButton("yes"); }
      if (e.key === "n" || e.key === "N") { e.preventDefault(); handleButton("no"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleButton, handleTextButton]);

  // ── Session management ────────────────────────────────────────────────────

  const refreshState = useCallback(async (targetSid: string) => {
    const seq = ++refreshSeqRef.current;
    try {
      const session = await getSession(targetSid);
      if (activeSessionRef.current !== targetSid || refreshSeqRef.current !== seq) return;
      setCurrentState(session.current_state);
    } catch (err: unknown) {
      if (activeSessionRef.current !== targetSid) return;
      setError(err instanceof Error ? err.message : "State refresh failed.");
    }
  }, []);

  const connectWS = useCallback(
    (sid: string) => {
      socketRef.current?.close();
      setWsStatus("connecting");
      socketRef.current = createStudentSocket(
        sid,
        (event) => {
          vlog("WS", `event received: ${event.type}`);
          if (REFRESH_EVENT_TYPES.has(event.type)) void refreshState(sid);
        },
        (s) => {
          vlog("WS", `status → ${s}`);
          setWsStatus(s);
        }
      );
    },
    [refreshState]
  );

  // ── Re-sync state after WebSocket reconnects ─────────────────────────────
  // When the backend restarts, sessions are restored from DB.
  // Fetching the session once after reconnect brings the UI back in sync
  // without requiring a browser refresh.

  const prevWsStatusRef = useRef<string>("closed");
  useEffect(() => {
    if (
      wsStatus === "connected" &&
      prevWsStatusRef.current === "reconnecting" &&
      sessionId
    ) {
      void refreshState(sessionId);
    }
    prevWsStatusRef.current = wsStatus;
  }, [wsStatus, sessionId, refreshState]);

  const handleStart = async () => {
    setBusy(true);
    setError(null);
    setLastRecognized("");
    try {
      if (sessionId) {
        vlog("SESSION", `restarting — stopping previous session ${sessionId}`);
        await stopSession(sessionId);
        socketRef.current?.close();
        activeSessionRef.current = null;
        stopContinuous();
        cancelSpeech();
      }
      const session = await startSession(scenarioId);
      vlog("SESSION", `started: session_id=${session.session_id} initial_state=${session.current_state.id}`);
      activeSessionRef.current = session.session_id;
      setSessionId(session.session_id);
      setCurrentState(session.current_state);
      connectWS(session.session_id);
    } catch (err: unknown) {
      vlog("SESSION", `start failed: ${err instanceof Error ? err.message : String(err)}`);
      setError(friendlyError(err, "start"));
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    stopContinuous();
    cancelSpeech();
    try {
      await stopSession(sessionId);
      activeSessionRef.current = null;
      setSessionId(null);
      setCurrentState(null);
      socketRef.current?.close();
      setVoicePhase("idle");
    } catch (err: unknown) {
      setError(friendlyError(err, "stop"));
    } finally {
      setBusy(false);
    }
  };

  // ── PDF / CSV ─────────────────────────────────────────────────────────────

  const handlePdf = async () => {
    if (!sessionId) return;
    setDownloadingPdf(true);
    try {
      const blob = await downloadSessionPdf(sessionId);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `session_${sessionId}_report.pdf`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "PDF download failed.");
    } finally {
      setDownloadingPdf(false);
    }
  };

  const handleCsv = async () => {
    if (!sessionId) return;
    setExportingCsv(true);
    try {
      const blob = await downloadSessionCsv(sessionId);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `session_${sessionId}.csv`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "CSV export failed.");
    } finally {
      setExportingCsv(false);
    }
  };

  const handleClinicalCsv = async () => {
    if (!sessionId) return;
    setExportingClinical(true);
    try {
      const blob = await downloadClinicalCsv(sessionId);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `session_${sessionId}_clinical.csv`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Clinical CSV export failed.");
    } finally {
      setExportingClinical(false);
    }
  };

  const handleXlsx = async () => {
    if (!sessionId) return;
    setExportingXlsx(true);
    try {
      const blob = await downloadClinicalXlsx(sessionId);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `session_${sessionId}_clinical.xlsx`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Excel report export failed.");
    } finally {
      setExportingXlsx(false);
    }
  };

  // ── Derived ───────────────────────────────────────────────────────────────

  const hasYesNo     = hasPrimaryYesNo(currentState);
  const textAction   = primaryTextAction(currentState);
  const isComplete   = isTerminal(currentState);
  const isVentPhase  = currentState ? VENT_PHASE_STATES.has(currentState.id) : false;
  const isVentTimer  =
    activeTimer?.id === "ventilation_timer" ||
    activeTimer?.id === "continue_ventilation_timer" ||
    activeTimer?.id === "corrective_ventilation_timer";

  const micLabel = !micSupported
    ? "Voice unavailable — use buttons"
    : reliability.circuitOpen      ? "Voice paused — use buttons below"
    : reliability.showManualFallback ? "Please answer using the buttons"
    : voicePhase === "listening"   ? "Listening…"
    : voicePhase === "speaking"    ? "Speaking…"
    : voicePhase === "confirming"  ? "Confirming…"
    : voicePhase === "processing"  ? "Processing…"
    : voicePhase === "complete"    ? "Simulation complete"
    : sessionId                    ? "Ready"
    :                                "Start a session";

  // Voice status indicator — four states derived from voice phase, validity, and mic health.
  // BLUE:   system is speaking (mic intentionally paused)
  // GREEN:  listening and ready, or last input was valid
  // YELLOW: last recognised input was invalid for the current state
  // RED:    mic unavailable, circuit open, or fallback active
  type VoiceStatusColor = "red" | "green" | "yellow" | "blue";
  const voiceStatusColor: VoiceStatusColor | null = (() => {
    if (!sessionId) return null;
    if (!micSupported || !!micError || reliability.circuitOpen || reliability.showManualFallback) return "red";
    if (voicePhase === "idle" || voicePhase === "complete") return null;
    if (voicePhase === "speaking" || voicePhase === "confirming") return "blue";
    // listening or processing: YELLOW only after a confirmed invalid utterance
    if (voiceInputValid === false) return "yellow";
    return "green"; // null (no input yet) or true (valid) → show as Listening/valid
  })();

  const voiceStatusLabel =
    voiceStatusColor === "blue"   ? "Voice Status: Speaking"
    : voiceStatusColor === "green"  ? "Voice Status: Listening"
    : voiceStatusColor === "yellow" ? "Voice Status: Input Not Recognized"
    : voiceStatusColor === "red"    ? "Voice Status: Voice Unavailable"
    : "Voice Status: inactive";

  const micRingClass =
    voicePhase === "listening"
      ? "bg-clinical-green shadow-[0_0_0_8px_rgba(13,148,136,0.25),0_0_0_18px_rgba(13,148,136,0.1)] animate-pulse"
    : voicePhase === "speaking"
      ? "bg-clinical-blue shadow-[0_0_0_6px_rgba(37,99,235,0.15)]"
    : voicePhase === "processing"
      ? "bg-amber-500"
    : voicePhase === "complete"
      ? "bg-emerald-600"
    : "bg-slate-700";

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-slate-950 text-white flex flex-col">

      {/* Header */}
      <header className="flex-shrink-0 border-b border-white/10 bg-slate-900">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3 sm:px-6">

          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-clinical-green">
              <svg className="h-4 w-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
              </svg>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-clinical-green leading-none">
                NRS Voice Assistant
              </p>
              <p className="text-sm font-semibold leading-tight">Neonatal Resuscitation</p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <ConnectionStatusBadge websocketStatus={wsStatus} />
            <select
              className="rounded border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none focus:border-clinical-green disabled:opacity-50"
              disabled={busy || Boolean(sessionId)}
              onChange={(e) => setScenarioId(e.target.value)}
              value={scenarioId}
            >
              {scenarios.length === 0
                ? <option value={scenarioId}>{scenarioId}</option>
                : scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <button
              className="rounded bg-clinical-green px-4 py-1.5 text-sm font-semibold text-white hover:bg-teal-600 disabled:cursor-not-allowed disabled:opacity-50 transition"
              disabled={busy}
              onClick={() => void handleStart()}
              type="button"
            >
              {sessionId ? "Restart" : "Start"}
            </button>
            <button
              className="rounded border border-white/20 px-4 py-1.5 text-sm font-semibold hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50 transition"
              disabled={busy || !sessionId}
              onClick={() => void handleStop()}
              type="button"
            >
              Stop
            </button>
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex flex-col gap-5 items-center px-4 py-6 sm:px-6 max-w-3xl mx-auto w-full">

        {wsStatus === "reconnecting" && (
          <div className="w-full rounded-lg border border-amber-500/30 bg-amber-950/50 px-4 py-2 text-sm text-amber-300 text-center">
            Connection lost — attempting to reconnect…
          </div>
        )}

        {error ? (
          <div className="w-full rounded-lg border border-rose-500/30 bg-rose-950/50 px-4 py-3 text-sm text-rose-300 flex items-start justify-between gap-3">
            <span>{error}</span>
            <button
              className="shrink-0 text-rose-400 hover:text-rose-200 transition text-xs underline"
              onClick={() => setError(null)}
              type="button"
            >
              Dismiss
            </button>
          </div>
        ) : null}

        {/* Timers */}
        {sessionId ? (
          <div className="grid grid-cols-2 gap-3 w-full">
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-center">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                Birth Timer
              </p>
              <p className="mt-1 text-4xl font-bold tabular-nums tracking-tight">
                {formatMMSS(birthElapsed)}
              </p>
            </div>
            <div className={`rounded-xl border p-4 transition ${isVentTimer ? "border-amber-500/40 bg-amber-950/30" : "border-white/10 bg-white/5"}`}>
              {isVentTimer && activeTimer ? (
                <div className="space-y-2">
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-amber-400">
                    {activeTimer.label}
                  </p>
                  <p className="text-3xl font-bold tabular-nums tracking-tight text-amber-200">
                    {formatMMSS(activeTimer.remainingSeconds)}
                  </p>
                  <div className="h-1 overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-amber-400 transition-[width] duration-1000 ease-linear"
                      style={{ width: `${100 - activeTimer.progressPercent}%` }}
                    />
                  </div>
                  <p className="text-xs text-amber-400/60">{activeTimer.remainingSeconds}s remaining</p>
                </div>
              ) : (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600">
                    Ventilation Timer
                  </p>
                  <p className="mt-1 text-3xl font-bold tabular-nums text-slate-700">--:--</p>
                </div>
              )}
            </div>
          </div>
        ) : null}

        {/* Continuous Ventilation Elapsed Timer */}
        {sessionId && isVentPhase ? (
          <div className="rounded-xl border border-clinical-green/30 bg-clinical-green/10 p-4 text-center w-full">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-clinical-green">
              Ventilation Elapsed
            </p>
            <p className="mt-1 text-4xl font-bold tabular-nums tracking-tight text-clinical-green">
              {formatMMSS(ventElapsed)}
            </p>
          </div>
        ) : null}

        {/* Current instruction */}
        <div className="w-full rounded-2xl border border-white/10 bg-white/5 px-8 py-8 text-center">
          {currentState ? (
            <>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-clinical-green">
                {currentState.name}
              </p>
              <h2 className="mt-4 text-2xl sm:text-3xl font-bold leading-snug">
                {voicePrompt(currentState)}
              </h2>
            </>
          ) : (
            <>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600">
                Ready
              </p>
              <h2 className="mt-4 text-xl font-semibold text-slate-500">
                Select a scenario and press Start.
              </h2>
            </>
          )}
        </div>

        {/* Microphone indicator */}
        <div className="flex flex-col items-center gap-4">
          <div className={`h-24 w-24 rounded-full flex items-center justify-center transition-all duration-500 ${micRingClass}`}>
            <svg className="h-11 w-11 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
            </svg>
          </div>
          <p className="text-sm font-medium text-slate-400">{micLabel}</p>
          {micError ? <p className="text-xs text-rose-400 text-center max-w-xs">{micError}</p> : null}
          {voiceStatusColor ? (
            <div className="flex flex-col items-center gap-1.5">
              <div
                aria-label={voiceStatusLabel}
                className={`h-5 w-5 rounded-full transition-colors duration-300 ${
                  voiceStatusColor === "blue"   ? "bg-blue-400"
                  : voiceStatusColor === "green"  ? "bg-emerald-400"
                  : voiceStatusColor === "yellow" ? "bg-amber-400"
                  : "bg-rose-500"
                }`}
                role="status"
              />
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                {voiceStatusColor === "blue"   ? "Speaking"
                : voiceStatusColor === "green"  ? "Listening"
                : voiceStatusColor === "yellow" ? "Input Not Recognized"
                : "Voice Unavailable"}
              </p>
            </div>
          ) : null}
        </div>

        {/* Noise / silence warning (Part 5) — advisory only, never blocks FSM */}
        {voicePhase === "listening" && noiseWarning ? (
          <div className="w-full rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-400">
            {noiseWarning}
          </div>
        ) : null}

        {/* Manual fallback — shown after MAX_RETRIES or circuit open (Parts 4, 9) */}
        {hasYesNo && sessionId && !isComplete && (reliability.showManualFallback || reliability.circuitOpen) ? (
          <div className="w-full rounded-xl border border-white/20 bg-white/5 px-4 py-4">
            <p className="mb-3 text-center text-sm font-semibold text-slate-300">
              {reliability.circuitOpen
                ? "Voice recognition paused. Please answer using the buttons (Y / N)."
                : "Voice not recognised after several attempts. Please answer using the buttons (Y / N)."}
            </p>
            <div className="grid grid-cols-2 gap-4">
              <button
                className="rounded-2xl border-2 border-clinical-green bg-clinical-green/20 py-6 text-3xl font-black text-clinical-green transition hover:bg-clinical-green hover:text-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
                disabled={busy}
                onClick={() => handleButton("yes")}
                type="button"
              >
                YES <span className="text-base font-normal opacity-60">[Y]</span>
              </button>
              <button
                className="rounded-2xl border-2 border-rose-500 bg-rose-500/20 py-6 text-3xl font-black text-rose-400 transition hover:bg-rose-500 hover:text-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
                disabled={busy}
                onClick={() => handleButton("no")}
                type="button"
              >
                NO <span className="text-base font-normal opacity-60">[N]</span>
              </button>
            </div>
          </div>
        ) : null}

        {/* Emergency YES / NO buttons — always visible for quick override */}
        {hasYesNo && sessionId && !isComplete && !reliability.showManualFallback && !reliability.circuitOpen ? (
          <div className="w-full">
            <div className="grid grid-cols-2 gap-4">
              <button
                className="rounded-2xl border-2 border-clinical-green/40 bg-clinical-green/10 py-6 text-3xl font-black text-clinical-green transition hover:bg-clinical-green hover:text-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
                disabled={busy || !sessionId}
                onClick={() => handleButton("yes")}
                type="button"
              >
                YES
              </button>
              <button
                className="rounded-2xl border-2 border-rose-500/40 bg-rose-500/10 py-6 text-3xl font-black text-rose-400 transition hover:bg-rose-500 hover:text-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
                disabled={busy || !sessionId}
                onClick={() => handleButton("no")}
                type="button"
              >
                NO
              </button>
            </div>
          </div>
        ) : null}

        {/* Text action fallback button — DONE or VENTILATION STARTED */}
        {textAction && sessionId && !isComplete ? (
          <div className="w-full">
            <button
              className="w-full rounded-2xl border-2 border-clinical-green bg-clinical-green/20 py-6 text-3xl font-black text-clinical-green transition hover:bg-clinical-green hover:text-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
              disabled={busy || !sessionId}
              onClick={handleTextButton}
              type="button"
            >
              {String(textAction.metadata.fallback_button_label ?? "DONE")}
              <span className="ml-3 text-base font-normal opacity-60">[Y]</span>
            </button>
          </div>
        ) : null}

        {/* Protocol stage */}
        {sessionId ? (
          <div className="w-full rounded-xl border border-white/10 bg-white/5 px-5 py-4">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-3">
              Protocol Stage
            </p>
            <div className="flex flex-wrap gap-2">
              {PROFESSOR_WORKFLOW_STEPS.map((step, i) => {
                const st = getWorkflowStepStatus(i, currentState?.id);
                return (
                  <span
                    key={step.label}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                      st === "complete" ? "bg-clinical-green/20 text-clinical-green"
                      : st === "current" ? "bg-white text-slate-900 font-bold"
                      : "bg-white/5 text-slate-700"
                    }`}
                  >
                    {step.label}
                  </span>
                );
              })}
            </div>
          </div>
        ) : null}

        {/* Performance report */}
        {metrics ? <div className="w-full"><PerformanceReport metrics={metrics} /></div> : null}

        {/* Session replay */}
        {showReplay && sessionId ? (
          <div className="w-full">
            <SessionReplay sessionId={sessionId} onClose={() => setShowReplay(false)} />
          </div>
        ) : null}

        {/* Footer toolbar */}
        <div className="w-full flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/5 px-5 py-3">
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50 transition"
              disabled={!sessionId || exportingCsv}
              onClick={() => void handleCsv()}
              type="button"
            >
              {exportingCsv ? "Exporting…" : "Export CSV"}
            </button>
            <button
              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50 transition"
              disabled={!sessionId || exportingClinical}
              onClick={() => void handleClinicalCsv()}
              type="button"
            >
              {exportingClinical ? "Exporting…" : "Clinical Timeline"}
            </button>
            <button
              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50 transition"
              disabled={!sessionId || exportingXlsx}
              onClick={() => void handleXlsx()}
              type="button"
            >
              {exportingXlsx ? "Generating…" : "Export Excel Timeline"}
            </button>
            <button
              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50 transition"
              disabled={!sessionId || downloadingPdf}
              onClick={() => void handlePdf()}
              type="button"
            >
              {downloadingPdf ? "Generating…" : "PDF Report"}
            </button>
            <button
              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50 transition"
              disabled={!sessionId}
              onClick={() => setShowReplay((v) => !v)}
              type="button"
            >
              {showReplay ? "Hide Replay" : "View Replay"}
            </button>
          </div>
          <span className="font-mono text-[10px] text-slate-700 truncate max-w-[14rem]">
            {sessionId ?? "No session"}
          </span>
        </div>

      </div>

      {/* ── Dev panel ─────────────────────────────────────────────────────────
          Hidden by default. Enable via browser console:
            localStorage.setItem('NRS_DEV', '1'); location.reload();
          Disable:
            localStorage.removeItem('NRS_DEV'); location.reload();
      */}
      {/* ── Dev diagnostics panel (Part 7) ────────────────────────────────────
          Hidden by default. Enable via browser console:
            localStorage.setItem('NRS_DEV', '1'); location.reload();
          Disable:
            localStorage.removeItem('NRS_DEV'); location.reload();
          MUST be disabled in production (no NRS_DEV key in localStorage).
      */}
      {typeof window !== "undefined" && window.localStorage.getItem("NRS_DEV") === "1" ? (
        <div className="fixed bottom-0 left-0 right-0 z-50 bg-black/90 border-t border-green-500/40 px-4 py-2 font-mono text-[10px] text-green-400 overflow-x-auto">
          <div className="flex flex-wrap gap-x-6 gap-y-1 max-w-full">
            <span><span className="text-green-600">PHASE</span> {voicePhase.toUpperCase()}</span>
            <span><span className="text-green-600">FSM</span> {currentState?.id ?? "—"}</span>
            <span><span className="text-green-600">RAW</span> &ldquo;{rawTranscript || "—"}&rdquo;</span>
            <span><span className="text-green-600">NORM</span> &ldquo;{lastRecognized || "—"}&rdquo;</span>
            <span><span className="text-green-600">CONF</span> {lastConfidence !== null ? lastConfidence.toFixed(2) : "—"}</span>
            <span><span className="text-green-600">RETRY</span> {reliability.retryCount}/{reliability.retryCount}</span>
            <span><span className="text-green-600">CIRC</span> {reliability.circuitOpen ? "OPEN" : "closed"}</span>
            <span><span className="text-green-600">FALLBK</span> {reliability.showManualFallback ? "Y" : "N"}</span>
            <span><span className="text-green-600">NOISE</span> {noiseLevel}</span>
            <span><span className="text-green-600">RMS</span> {rms.toFixed(3)}</span>
            <span><span className="text-green-600">HTTP</span> {lastHttpStatus !== null ? String(lastHttpStatus) : "—"}</span>
            <span><span className="text-green-600">WS</span> {wsStatus}</span>
            <span><span className="text-green-600">GEN</span> {getGeneration()}</span>
            <span><span className="text-green-600">TOK</span> {getSpeechToken()}</span>
            <span><span className="text-green-600">SID</span> {sessionId?.slice(0, 8) ?? "—"}</span>
            <span><span className="text-green-600">BUSY</span> {busy ? "Y" : "N"}</span>
            <span className="text-green-600/50">NRS-DEV · filter [NRS] [VOICE] in console</span>
          </div>
        </div>
      ) : null}

    </main>
  );
}
