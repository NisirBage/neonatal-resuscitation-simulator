/**
 * Voice reliability telemetry service (Part 6).
 *
 * Records QA metrics for every recognition attempt.  Completely separate from
 * the clinical timeline — these events are NEVER injected into session exports,
 * CSV, XLSX, or PDF reports.
 *
 * Usage:
 *   import { voiceTelemetry } from "../services/voiceTelemetry";
 *   voiceTelemetry.record({ ... });
 *   const summary = voiceTelemetry.computeMetrics(sessionId);
 */

// ── Event shape ───────────────────────────────────────────────────────────────

export type TelemetryOutcome =
  | "accepted"
  | "rejected_low_confidence"
  | "confirmation_accepted"
  | "confirmation_rejected"
  | "retry_unknown"
  | "manual_fallback"
  | "circuit_open"
  | "timeout";

export type TelemetryNormalised = "yes" | "no" | "unknown";
export type TelemetryNoiseLevel = "silent" | "normal" | "noisy" | "clipping";

export interface TelemetryEvent {
  sessionId:             string;
  stateId:               string;
  attemptNumber:         number;   // 1-based within the current FSM state
  timestamp:             number;   // Date.now()

  // Latencies — null when the phase did not complete
  recognitionLatencyMs:  number | null;  // listening-start → transcript received
  submitLatencyMs:       number | null;  // accepted-result  → HTTP 200
  transitionLatencyMs:   number | null;  // HTTP 200        → FSM state updated

  retryCount:    number;
  confidence:    number | null;   // 0-1 from SR provider; null if unavailable
  outcome:       TelemetryOutcome;
  normalized:    TelemetryNormalised;

  // Environment
  browser:       string;
  os:            string;
  micError:      string | null;
  speechError:   string | null;
  noiseLevel:    TelemetryNoiseLevel | null;
  silenceDurationMs: number | null;
}

// ── Summary metrics (Part 12) ─────────────────────────────────────────────────

export interface ReliabilityMetrics {
  /** Fraction of attempts that produced an accepted result (0–1). */
  recognitionSuccessRate: number;
  /** Mean SR confidence across all recorded attempts. Null if none. */
  averageConfidence: number | null;
  /** Total retry events across all states. */
  totalRetries: number;
  /** Number of times the manual fallback was triggered. */
  manualFallbackCount: number;
  /** Mean time from listening start to accepted transcript (ms). Null if none. */
  averageRecognitionMs: number | null;
  /** Mean time from HTTP 200 to FSM state update (ms). Null if none. */
  averageTransitionMs: number | null;
  /** Fraction of attempts that resulted in a rejection or circuit-open. */
  speechFailureRate: number;
  /** Attempts where noiseLevel was "noisy" or "clipping". */
  noiseEventCount: number;
  /** Attempts where outcome was "timeout". */
  timeoutEventCount: number;
}

// ── Service ───────────────────────────────────────────────────────────────────

class VoiceTelemetryService {
  private _events: TelemetryEvent[] = [];

  record(event: TelemetryEvent): void {
    this._events.push({ ...event });
  }

  getEvents(): readonly TelemetryEvent[] {
    return this._events;
  }

  /** Remove all events belonging to a given session (e.g. on session restart). */
  clearForSession(sessionId: string): void {
    this._events = this._events.filter((e) => e.sessionId !== sessionId);
  }

  /** Compute summary metrics for a session (Part 12). */
  computeMetrics(sessionId: string): ReliabilityMetrics {
    const events = this._events.filter((e) => e.sessionId === sessionId);

    if (events.length === 0) {
      return {
        recognitionSuccessRate: 1,
        averageConfidence:      null,
        totalRetries:           0,
        manualFallbackCount:    0,
        averageRecognitionMs:   null,
        averageTransitionMs:    null,
        speechFailureRate:      0,
        noiseEventCount:        0,
        timeoutEventCount:      0,
      };
    }

    const accepted   = events.filter((e) => e.outcome === "accepted" || e.outcome === "confirmation_accepted");
    const withConf   = events.filter((e) => e.confidence !== null);
    const withRecog  = events.filter((e) => e.recognitionLatencyMs !== null);
    const withTrans  = accepted.filter((e) => e.transitionLatencyMs !== null);
    const failures   = events.filter((e) =>
      e.outcome === "rejected_low_confidence" || e.outcome === "circuit_open"
    );

    return {
      recognitionSuccessRate: accepted.length / events.length,

      averageConfidence: withConf.length > 0
        ? withConf.reduce((s, e) => s + (e.confidence ?? 0), 0) / withConf.length
        : null,

      totalRetries: events.reduce((s, e) => s + e.retryCount, 0),

      manualFallbackCount: events.filter((e) => e.outcome === "manual_fallback").length,

      averageRecognitionMs: withRecog.length > 0
        ? withRecog.reduce((s, e) => s + (e.recognitionLatencyMs ?? 0), 0) / withRecog.length
        : null,

      averageTransitionMs: withTrans.length > 0
        ? withTrans.reduce((s, e) => s + (e.transitionLatencyMs ?? 0), 0) / withTrans.length
        : null,

      speechFailureRate: failures.length / events.length,

      noiseEventCount: events.filter((e) =>
        e.noiseLevel === "noisy" || e.noiseLevel === "clipping"
      ).length,

      timeoutEventCount: events.filter((e) => e.outcome === "timeout").length,
    };
  }
}

/** Singleton telemetry instance. Import this everywhere voice events need recording. */
export const voiceTelemetry = new VoiceTelemetryService();

// ── Browser / OS detection (best-effort) ─────────────────────────────────────

export function detectBrowser(): string {
  const ua = navigator.userAgent;
  if (ua.includes("Edg/"))    return "edge";
  if (ua.includes("Chrome/")) return "chrome";
  if (ua.includes("Firefox/")) return "firefox";
  if (ua.includes("Safari/")) return "safari";
  return "unknown";
}

export function detectOS(): string {
  const ua = navigator.userAgent;
  if (ua.includes("Windows")) return "windows";
  if (ua.includes("Mac"))     return "macos";
  if (ua.includes("Linux"))   return "linux";
  if (ua.includes("Android")) return "android";
  if (ua.includes("iPhone") || ua.includes("iPad")) return "ios";
  return "unknown";
}
