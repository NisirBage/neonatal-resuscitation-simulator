/**
 * Part 13 — Tests: Voice reliability controller (Parts 1, 3, 4, 9).
 *
 * Tests the processResult() state machine without a browser.
 * All logic is pure JS — no DOM, no SR API, no React.
 */

import { describe, it, expect } from "vitest";
import { normalizeToYesNo } from "../services/voice/normalize";
import { CONFIDENCE_THRESHOLDS } from "../services/voice/normalize";
import type { VoiceReliabilityConfig } from "../hooks/useVoiceReliability";

// ── Pure processResult logic (extracted for unit testing) ────────────────────
// We replicate the core decision logic here as a pure function so it can be
// tested without the React hook machinery.

interface ActionResult {
  type: "accept" | "confirm" | "retry" | "manual_fallback" | "circuit_open" | "ignore";
  normalised?: "yes" | "no";
  retryNumber?: number;
  reason?: string;
}

function processReliabilityAction(
  text: string,
  confidence: number,
  state: { retryCount: number; circuitOpen: boolean; isConfirming: boolean; pending: "yes" | "no" | null },
  config: VoiceReliabilityConfig,
): { action: ActionResult; newRetryCount: number; newCircuitOpen: boolean } {
  if (state.circuitOpen) {
    return { action: { type: "circuit_open" }, newRetryCount: state.retryCount, newCircuitOpen: true };
  }
  if (state.isConfirming) {
    const answer = normalizeToYesNo(text);
    if (answer === "yes" && state.pending) {
      return { action: { type: "accept", normalised: state.pending }, newRetryCount: 0, newCircuitOpen: false };
    }
    const next = state.retryCount + 1;
    if (next >= config.MAX_RETRIES) {
      return { action: { type: "manual_fallback" }, newRetryCount: next, newCircuitOpen: false };
    }
    return { action: { type: "retry", retryNumber: next, reason: "unknown" }, newRetryCount: next, newCircuitOpen: false };
  }
  if (confidence > 0 && confidence < config.MEDIUM_CONFIDENCE) {
    const next = state.retryCount + 1;
    if (next >= config.MAX_RETRIES) {
      return { action: { type: "manual_fallback" }, newRetryCount: next, newCircuitOpen: false };
    }
    return { action: { type: "retry", retryNumber: next, reason: "low_confidence" }, newRetryCount: next, newCircuitOpen: false };
  }
  const normalised = normalizeToYesNo(text);
  if (normalised === "unknown") {
    const next = state.retryCount + 1;
    if (next >= config.MAX_RETRIES) {
      return { action: { type: "manual_fallback" }, newRetryCount: next, newCircuitOpen: false };
    }
    return { action: { type: "retry", retryNumber: next, reason: "unknown" }, newRetryCount: next, newCircuitOpen: false };
  }
  if (confidence > 0 && confidence < config.HIGH_CONFIDENCE) {
    return {
      action: { type: "confirm", normalised, reason: "medium_confidence" },
      newRetryCount: state.retryCount,
      newCircuitOpen: false,
    };
  }
  return { action: { type: "accept", normalised }, newRetryCount: 0, newCircuitOpen: false };
}

const DEFAULT_CONFIG: VoiceReliabilityConfig = {
  HIGH_CONFIDENCE:           CONFIDENCE_THRESHOLDS.HIGH,
  MEDIUM_CONFIDENCE:         CONFIDENCE_THRESHOLDS.MEDIUM,
  MAX_RETRIES:               3,
  CIRCUIT_BREAKER_THRESHOLD: 3,
};

const freshState = () => ({
  retryCount: 0, circuitOpen: false, isConfirming: false, pending: null as "yes" | "no" | null,
});

// ── Part 1: Confidence thresholds ─────────────────────────────────────────────

describe("Confidence thresholds (Part 1)", () => {
  it("HIGH confidence (≥ 0.80) → accept immediately", () => {
    const { action } = processReliabilityAction("yes", 0.95, freshState(), DEFAULT_CONFIG);
    expect(action.type).toBe("accept");
    expect(action.normalised).toBe("yes");
  });

  it("MEDIUM confidence (0.60–0.79) → ask for confirmation", () => {
    const { action } = processReliabilityAction("yes", 0.70, freshState(), DEFAULT_CONFIG);
    expect(action.type).toBe("confirm");
  });

  it("LOW confidence (< 0.60) → retry, do not accept", () => {
    const { action } = processReliabilityAction("yes", 0.40, freshState(), DEFAULT_CONFIG);
    expect(action.type).toBe("retry");
    expect(action.reason).toBe("low_confidence");
  });

  it("confidence=0 (interim fallback) → treated as high confidence", () => {
    const { action } = processReliabilityAction("yes", 0, freshState(), DEFAULT_CONFIG);
    expect(action.type).toBe("accept");
  });
});

// ── Part 2: Synonym handling passes through correctly ─────────────────────────

describe("Synonym normalisation in reliability pipeline", () => {
  for (const word of ["yeah", "yep", "correct", "absolutely", "sure"]) {
    it(`"${word}" at high confidence → accept as yes`, () => {
      const { action } = processReliabilityAction(word, 0.9, freshState(), DEFAULT_CONFIG);
      expect(action.type).toBe("accept");
      expect(action.normalised).toBe("yes");
    });
  }
  for (const word of ["nope", "negative", "nah", "incorrect"]) {
    it(`"${word}" at high confidence → accept as no`, () => {
      const { action } = processReliabilityAction(word, 0.9, freshState(), DEFAULT_CONFIG);
      expect(action.type).toBe("accept");
      expect(action.normalised).toBe("no");
    });
  }
});

// ── Part 3: Retry engine ──────────────────────────────────────────────────────

describe("Retry engine (Part 3)", () => {
  it("unknown transcript → retry (attempt 1)", () => {
    const { action, newRetryCount } = processReliabilityAction("um", 0.9, freshState(), DEFAULT_CONFIG);
    expect(action.type).toBe("retry");
    expect(newRetryCount).toBe(1);
  });

  it("retry count increments on each failure", () => {
    let state = freshState();
    for (let i = 1; i <= DEFAULT_CONFIG.MAX_RETRIES - 1; i++) {
      const result = processReliabilityAction("um", 0.9, state, DEFAULT_CONFIG);
      expect(result.action.type).toBe("retry");
      state = { ...state, retryCount: result.newRetryCount };
    }
    expect(state.retryCount).toBe(DEFAULT_CONFIG.MAX_RETRIES - 1);
  });

  it("reaching MAX_RETRIES triggers manual_fallback", () => {
    const state = { ...freshState(), retryCount: DEFAULT_CONFIG.MAX_RETRIES - 1 };
    const { action } = processReliabilityAction("um", 0.9, state, DEFAULT_CONFIG);
    expect(action.type).toBe("manual_fallback");
  });
});

// ── Part 4: Manual fallback ───────────────────────────────────────────────────

describe("Manual fallback (Part 4)", () => {
  it("fallback triggered after MAX_RETRIES low-confidence results", () => {
    let state = freshState();
    let finalAction: ActionResult = { type: "ignore" };
    for (let i = 0; i <= DEFAULT_CONFIG.MAX_RETRIES; i++) {
      const result = processReliabilityAction("yes", 0.3, state, DEFAULT_CONFIG);
      finalAction = result.action;
      state = { ...state, retryCount: result.newRetryCount };
      if (finalAction.type === "manual_fallback") break;
    }
    expect(finalAction.type).toBe("manual_fallback");
  });
});

// ── Part 9: Circuit breaker ───────────────────────────────────────────────────

describe("Circuit breaker (Part 9)", () => {
  it("circuit_open state blocks all results", () => {
    const state = { ...freshState(), circuitOpen: true };
    const { action } = processReliabilityAction("yes", 0.95, state, DEFAULT_CONFIG);
    expect(action.type).toBe("circuit_open");
  });

  it("circuit_open overrides high confidence result", () => {
    const state = { ...freshState(), circuitOpen: true };
    const { action } = processReliabilityAction("yes", 1.0, state, DEFAULT_CONFIG);
    expect(action.type).toBe("circuit_open");
  });
});

// ── Confirmation flow (Part 1, medium confidence) ────────────────────────────

describe("Confirmation flow", () => {
  it("confirming YES after confirm action → accept with original normalised", () => {
    const state = { ...freshState(), isConfirming: true, pending: "yes" as const };
    const { action } = processReliabilityAction("yes", 0.9, state, DEFAULT_CONFIG);
    expect(action.type).toBe("accept");
    expect(action.normalised).toBe("yes");
  });

  it("rejecting confirmation (saying no) → retry", () => {
    const state = { ...freshState(), isConfirming: true, pending: "yes" as const };
    const { action } = processReliabilityAction("no", 0.9, state, DEFAULT_CONFIG);
    expect(action.type).toBe("retry");
  });

  it("unknown during confirmation → retry", () => {
    const state = { ...freshState(), isConfirming: true, pending: "yes" as const };
    const { action } = processReliabilityAction("um", 0.9, state, DEFAULT_CONFIG);
    expect(action.type).toBe("retry");
  });
});

// ── Configurable thresholds ───────────────────────────────────────────────────

describe("Configurable thresholds", () => {
  it("with higher HIGH_CONFIDENCE, more results go through confirmation", () => {
    const strictConfig = { ...DEFAULT_CONFIG, HIGH_CONFIDENCE: 0.95, MEDIUM_CONFIDENCE: 0.70 };
    // 0.82 would be accepted in default config, but requires confirmation in strict config
    const { action } = processReliabilityAction("yes", 0.82, freshState(), strictConfig);
    expect(action.type).toBe("confirm");
  });

  it("MAX_RETRIES=1 triggers manual_fallback on first failure", () => {
    const aggressive = { ...DEFAULT_CONFIG, MAX_RETRIES: 1 };
    const { action } = processReliabilityAction("um", 0.9, freshState(), aggressive);
    expect(action.type).toBe("manual_fallback");
  });
});
