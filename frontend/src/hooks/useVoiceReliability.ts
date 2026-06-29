/**
 * useVoiceReliability — production voice reliability controller.
 *
 * Implements:
 *   Part 1:  Confidence-aware recognition (HIGH / MEDIUM / LOW thresholds)
 *   Part 3:  Retry engine (configurable MAX_RETRIES)
 *   Part 4:  Manual YES/NO fallback after MAX_RETRIES exhausted
 *   Part 9:  Circuit breaker (3 consecutive recognition failures → disable SR)
 *   Part 10: Browser lifecycle (tab hidden → pause SR; tab restored → resume)
 *
 * The FSM, WebSocket layer, clinical timeline, CSV/XLSX/PDF exports, and
 * voice prompts are completely unaffected by this hook.
 *
 * Usage in StudentDashboard:
 *   const reliability = useVoiceReliability(config);
 *   // Pass reliability.processResult to the voice handler instead of the
 *   // raw normaliseToYesNo check.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  normalizeToYesNo,
  CONFIDENCE_THRESHOLDS,
} from "../services/voice/normalize";

// Re-export so existing imports of normaliseToYesNo from this module continue
// to work without changes (backwards-compatible alias).
export { normalizeToYesNo as normaliseToYesNo } from "../services/voice/normalize";

// ── Configuration (Part 1, 3) ─────────────────────────────────────────────────

export interface VoiceReliabilityConfig {
  /** Confidence at or above which a result is accepted immediately. */
  HIGH_CONFIDENCE: number;
  /** Confidence at or above which the user is asked to confirm before submitting. */
  MEDIUM_CONFIDENCE: number;
  /** Maximum retries before the manual fallback is shown (Part 3, 4). */
  MAX_RETRIES: number;
  /** Consecutive recognition failures before the circuit breaker opens (Part 9). */
  CIRCUIT_BREAKER_THRESHOLD: number;
}

export const DEFAULT_VOICE_CONFIG: VoiceReliabilityConfig = {
  HIGH_CONFIDENCE:           CONFIDENCE_THRESHOLDS.HIGH,
  MEDIUM_CONFIDENCE:         CONFIDENCE_THRESHOLDS.MEDIUM,
  MAX_RETRIES:               3,
  CIRCUIT_BREAKER_THRESHOLD: 3,
};

// ── Action type returned by processResult ────────────────────────────────────

export type VoiceAction =
  /** Result is accepted; proceed with normalised value. */
  | { type: "accept"; normalised: "yes" | "no" }
  /**
   * Medium confidence — ask "I heard YES. Is that correct?"
   * The next voice result should be routed to processConfirmation().
   */
  | { type: "confirm"; heard: string; normalised: "yes" | "no"; prompt: string }
  /** Low confidence or unknown transcript — repeat the clinical question. */
  | { type: "retry"; reason: "low_confidence" | "unknown"; retryNumber: number }
  /** MAX_RETRIES exhausted — show manual YES/NO buttons. */
  | { type: "manual_fallback" }
  /** Circuit breaker is open — SR is disabled; manual controls already shown. */
  | { type: "circuit_open" }
  /** Ignore this result (e.g. tab hidden, not relevant). */
  | { type: "ignore" }

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface VoiceReliabilityState {
  retryCount:           number;
  showManualFallback:   boolean;
  circuitOpen:          boolean;
  consecutiveFailures:  number;
  /** True when the next voice result is interpreted as a confirmation answer. */
  isConfirming:         boolean;
}

export interface UseVoiceReliabilityResult extends VoiceReliabilityState {
  /**
   * Process a raw (text, confidence) pair from the SR provider.
   * Returns a VoiceAction that tells the caller what to do next.
   */
  processResult: (text: string, confidence: number) => VoiceAction;
  /**
   * Enter confirmation mode: the next call to processResult will be
   * interpreted as the user's answer to the confirmation prompt.
   */
  enterConfirmationMode: (pendingNormalised: "yes" | "no") => void;
  /** Reset retry / circuit state when transitioning to a new FSM state. */
  resetForNewState: () => void;
  /** Manually open the fallback (e.g. when circuit breaker fires externally). */
  openManualFallback: () => void;
  /** Record an external success (e.g. accepted via manual button) to reset circuit. */
  recordSuccess: () => void;
}

export function useVoiceReliability(
  config: VoiceReliabilityConfig = DEFAULT_VOICE_CONFIG,
): UseVoiceReliabilityResult {
  const [retryCount, setRetryCount]                   = useState(0);
  const [showManualFallback, setShowManualFallback]   = useState(false);
  const [circuitOpen, setCircuitOpen]                 = useState(false);
  const [consecutiveFailures, setConsecutiveFailures] = useState(0);
  const [isConfirming, setIsConfirming]               = useState(false);

  // Refs mirror state so callbacks never go stale
  const retryCountRef           = useRef(0);
  const showManualFallbackRef   = useRef(false);
  const circuitOpenRef          = useRef(false);
  const consecutiveFailuresRef  = useRef(0);
  const isConfirmingRef         = useRef(false);
  const pendingNormalisedRef    = useRef<"yes" | "no" | null>(null);

  // Keep refs in sync with state (state drives React renders; refs drive callbacks)
  useEffect(() => { retryCountRef.current          = retryCount;         }, [retryCount]);
  useEffect(() => { showManualFallbackRef.current   = showManualFallback;  }, [showManualFallback]);
  useEffect(() => { circuitOpenRef.current          = circuitOpen;         }, [circuitOpen]);
  useEffect(() => { consecutiveFailuresRef.current  = consecutiveFailures; }, [consecutiveFailures]);
  useEffect(() => { isConfirmingRef.current         = isConfirming;        }, [isConfirming]);

  // ── Private helpers ──────────────────────────────────────────────────────

  const incrementFailure = useCallback(() => {
    const next = consecutiveFailuresRef.current + 1;
    consecutiveFailuresRef.current = next;
    setConsecutiveFailures(next);
    if (next >= config.CIRCUIT_BREAKER_THRESHOLD) {
      circuitOpenRef.current = true;
      setCircuitOpen(true);
      showManualFallbackRef.current = true;
      setShowManualFallback(true);
    }
  }, [config.CIRCUIT_BREAKER_THRESHOLD]);

  const resetCircuit = useCallback(() => {
    consecutiveFailuresRef.current = 0;
    setConsecutiveFailures(0);
  }, []);

  // ── Public API ───────────────────────────────────────────────────────────

  const processResult = useCallback(
    (text: string, confidence: number): VoiceAction => {
      // Circuit breaker takes priority
      if (circuitOpenRef.current) return { type: "circuit_open" };

      // ── Confirmation mode ────────────────────────────────────────────────
      // The previous call entered confirmation mode ("I heard YES — correct?")
      // The current result is the user's yes/no answer to that prompt.
      if (isConfirmingRef.current) {
        isConfirmingRef.current = false;
        setIsConfirming(false);
        const answer = normalizeToYesNo(text);
        if (answer === "yes") {
          // User confirmed — accept the original pending normalised value
          const pending = pendingNormalisedRef.current;
          pendingNormalisedRef.current = null;
          if (pending) {
            resetCircuit();
            return { type: "accept", normalised: pending };
          }
        }
        // "no" or unknown → retry
        const r = retryCountRef.current + 1;
        retryCountRef.current = r;
        setRetryCount(r);
        if (r >= config.MAX_RETRIES) {
          showManualFallbackRef.current = true;
          setShowManualFallback(true);
          return { type: "manual_fallback" };
        }
        incrementFailure();
        return { type: "retry", reason: "unknown", retryNumber: r };
      }

      // ── Confidence check (Part 1) ────────────────────────────────────────
      const normalised = normalizeToYesNo(text);

      if (confidence > 0 && confidence < config.MEDIUM_CONFIDENCE) {
        // Low confidence — reject, count as failure
        const r = retryCountRef.current + 1;
        retryCountRef.current = r;
        setRetryCount(r);
        if (r >= config.MAX_RETRIES) {
          showManualFallbackRef.current = true;
          setShowManualFallback(true);
          return { type: "manual_fallback" };
        }
        incrementFailure();
        return { type: "retry", reason: "low_confidence", retryNumber: r };
      }

      // ── Normalisation check ───────────────────────────────────────────────
      if (normalised === "unknown") {
        const r = retryCountRef.current + 1;
        retryCountRef.current = r;
        setRetryCount(r);
        if (r >= config.MAX_RETRIES) {
          showManualFallbackRef.current = true;
          setShowManualFallback(true);
          return { type: "manual_fallback" };
        }
        incrementFailure();
        return { type: "retry", reason: "unknown", retryNumber: r };
      }

      // ── Medium confidence → ask confirmation ─────────────────────────────
      if (confidence > 0 && confidence < config.HIGH_CONFIDENCE) {
        pendingNormalisedRef.current = normalised;
        // Caller will enter confirmation mode after speaking the prompt
        return {
          type:       "confirm",
          heard:      normalised,
          normalised,
          prompt:     `I heard ${normalised.toUpperCase()}. Is that correct?`,
        };
      }

      // ── High confidence (or confidence === 0, e.g. from interim fallback) ─
      resetCircuit();
      return { type: "accept", normalised };
    },
    [config.MEDIUM_CONFIDENCE, config.HIGH_CONFIDENCE, config.MAX_RETRIES, incrementFailure, resetCircuit],
  );

  const enterConfirmationMode = useCallback((pendingNormalised: "yes" | "no") => {
    pendingNormalisedRef.current = pendingNormalised;
    isConfirmingRef.current = true;
    setIsConfirming(true);
  }, []);

  const resetForNewState = useCallback(() => {
    retryCountRef.current           = 0;
    showManualFallbackRef.current   = false;
    isConfirmingRef.current         = false;
    pendingNormalisedRef.current    = null;
    setRetryCount(0);
    setShowManualFallback(false);
    setIsConfirming(false);
    // Do NOT reset the circuit breaker — it persists across states intentionally.
    // It resets when recordSuccess() is called (i.e., when voice actually works).
  }, []);

  const openManualFallback = useCallback(() => {
    showManualFallbackRef.current = true;
    setShowManualFallback(true);
  }, []);

  const recordSuccess = useCallback(() => {
    resetCircuit();
    circuitOpenRef.current = false;
    setCircuitOpen(false);
  }, [resetCircuit]);

  return {
    retryCount,
    showManualFallback,
    circuitOpen,
    consecutiveFailures,
    isConfirming,
    processResult,
    enterConfirmationMode,
    resetForNewState,
    openManualFallback,
    recordSuccess,
  };
}

// ── Browser lifecycle utilities (Part 10) ────────────────────────────────────

/**
 * Returns a cleanup function that listens for tab visibility changes.
 * When the tab is hidden, the provided onHidden callback is called.
 * When the tab is restored, onVisible is called.
 *
 * Used in StudentDashboard to pause SR on hide and resume on restore.
 */
export function addLifecycleListeners(
  onHidden: () => void,
  onVisible: () => void,
): () => void {
  const handler = () => {
    if (document.hidden) { onHidden(); }
    else                 { onVisible(); }
  };
  document.addEventListener("visibilitychange", handler);
  return () => document.removeEventListener("visibilitychange", handler);
}
