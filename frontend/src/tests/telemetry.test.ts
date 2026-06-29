/**
 * Part 13 — Tests: Voice telemetry service (Part 6).
 *
 * Verifies that telemetry events are recorded separately from clinical data
 * and that reliability metrics (Part 12) are computed correctly.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  voiceTelemetry,
  type TelemetryEvent,
} from "../services/voiceTelemetry";

const BASE: Omit<TelemetryEvent, "outcome" | "normalized"> = {
  sessionId: "test-session",
  stateId: "baby_born",
  attemptNumber: 1,
  timestamp: Date.now(),
  recognitionLatencyMs: 120,
  submitLatencyMs: 80,
  transitionLatencyMs: 45,
  retryCount: 0,
  confidence: 0.92,
  browser: "chrome",
  os: "windows",
  micError: null,
  speechError: null,
  noiseLevel: "normal",
  silenceDurationMs: null,
};

describe("VoiceTelemetry — event recording", () => {
  beforeEach(() => {
    voiceTelemetry.clearForSession("test-session");
  });

  it("records events and returns them via getEvents()", () => {
    voiceTelemetry.record({ ...BASE, outcome: "accepted", normalized: "yes" });
    const events = voiceTelemetry.getEvents();
    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events.at(-1)?.sessionId).toBe("test-session");
  });

  it("clearForSession removes only that session's events", () => {
    voiceTelemetry.record({ ...BASE, sessionId: "other", outcome: "accepted", normalized: "no" });
    voiceTelemetry.record({ ...BASE, outcome: "accepted", normalized: "yes" });
    voiceTelemetry.clearForSession("test-session");
    const remaining = voiceTelemetry.getEvents().filter((e) => e.sessionId === "test-session");
    expect(remaining).toHaveLength(0);
    const other = voiceTelemetry.getEvents().filter((e) => e.sessionId === "other");
    expect(other).toHaveLength(1);
    voiceTelemetry.clearForSession("other");
  });
});

describe("VoiceTelemetry — computeMetrics (Part 12)", () => {
  beforeEach(() => {
    voiceTelemetry.clearForSession("metrics-session");
  });

  it("returns 100% success rate for all accepted events", () => {
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", outcome: "accepted", normalized: "yes" });
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", outcome: "accepted", normalized: "no" });
    const m = voiceTelemetry.computeMetrics("metrics-session");
    expect(m.recognitionSuccessRate).toBe(1);
    expect(m.totalRetries).toBe(0);
    expect(m.manualFallbackCount).toBe(0);
    expect(m.speechFailureRate).toBe(0);
  });

  it("counts retries and failures correctly", () => {
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", outcome: "retry_unknown", normalized: "unknown", retryCount: 1 });
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", outcome: "rejected_low_confidence", normalized: "unknown", retryCount: 2, confidence: 0.4 });
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", outcome: "manual_fallback", normalized: "unknown", retryCount: 3 });
    const m = voiceTelemetry.computeMetrics("metrics-session");
    expect(m.recognitionSuccessRate).toBe(0);
    expect(m.manualFallbackCount).toBe(1);
    expect(m.totalRetries).toBe(6); // 1+2+3
    expect(m.speechFailureRate).toBeGreaterThan(0);
  });

  it("computes average confidence", () => {
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", confidence: 0.8, outcome: "accepted", normalized: "yes" });
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", confidence: 0.9, outcome: "accepted", normalized: "yes" });
    const m = voiceTelemetry.computeMetrics("metrics-session");
    expect(m.averageConfidence).toBeCloseTo(0.85, 5);
  });

  it("counts noise events", () => {
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", noiseLevel: "noisy", outcome: "accepted", normalized: "yes" });
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", noiseLevel: "clipping", outcome: "accepted", normalized: "yes" });
    voiceTelemetry.record({ ...BASE, sessionId: "metrics-session", noiseLevel: "normal", outcome: "accepted", normalized: "yes" });
    const m = voiceTelemetry.computeMetrics("metrics-session");
    expect(m.noiseEventCount).toBe(2);
  });

  it("returns safe defaults when no events recorded", () => {
    const m = voiceTelemetry.computeMetrics("empty-session");
    expect(m.recognitionSuccessRate).toBe(1);
    expect(m.averageConfidence).toBeNull();
    expect(m.totalRetries).toBe(0);
  });
});
