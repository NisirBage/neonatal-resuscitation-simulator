/**
 * Single source of truth for all voice YES/NO normalisation logic.
 *
 * Every component that needs to interpret a speech-recognition transcript
 * MUST import from this file. No other file may duplicate this logic.
 *
 * Consumers:
 *   - useVoiceReliability  → normalizeToYesNo(), CONFIDENCE_THRESHOLDS
 *   - StudentDashboard     → normalizeToYesNo()
 *   - tests/normalize.test.ts → full regression suite
 */

// ── Synonym tables ─────────────────────────────────────────────────────────────
// Extend these tables to add new synonyms. Do NOT add synonyms anywhere else.

/** Words and phrases that map to YES. Order is irrelevant — all are tested. */
export const YES_SYNONYMS: readonly string[] = [
  "yes", "yeah", "yep", "yup",
  "correct", "affirmative",
  "absolutely", "sure",
  "okay", "ok",
  "indeed",
];

/** Words and phrases that map to NO. */
export const NO_SYNONYMS: readonly string[] = [
  "no", "nope", "nah",
  "negative",
  "incorrect",
  "never",
];

/**
 * Words that negate an otherwise affirmative phrase.
 * "absolutely not" contains "absolutely" (YES) AND "not" (negation) → unknown.
 * Applied before the YES check so negated affirmatives never mis-fire.
 */
export const NEGATION_WORDS: readonly string[] = ["not", "never", "no"];

// ── Confidence thresholds ─────────────────────────────────────────────────────
// The single authoritative set of confidence cut-offs used by the reliability
// layer. Import CONFIDENCE_THRESHOLDS instead of hard-coding 0.80 / 0.60.

export interface ConfidenceThresholds {
  /** At or above this value the result is accepted immediately. */
  HIGH:   number;
  /** At or above this value (but below HIGH) the user is asked to confirm. */
  MEDIUM: number;
}

export const CONFIDENCE_THRESHOLDS: ConfidenceThresholds = {
  HIGH:   0.80,
  MEDIUM: 0.60,
};

// ── Normalisation helpers ──────────────────────────────────────────────────────

/** Pre-process raw transcript: lowercase, strip punctuation, collapse spaces. */
function preprocess(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[.,!?;:'"-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Build a word-boundary regex that matches any word in the list. */
function anyOf(words: readonly string[]): RegExp {
  return new RegExp(`\\b(${words.join("|")})\\b`);
}

const YES_REGEX       = anyOf(YES_SYNONYMS);
const NO_REGEX        = anyOf(NO_SYNONYMS);
const NEGATION_REGEX  = anyOf(NEGATION_WORDS);

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Normalise a raw speech-recognition transcript to "yes", "no", or "unknown".
 *
 * Rules (applied in order):
 *  1. Empty / whitespace-only → "unknown"
 *  2. Contains a negation word (not, never, no) → check NO_SYNONYMS only.
 *     This prevents "absolutely not" from mapping to YES.
 *  3. Matches YES_SYNONYMS → "yes"
 *  4. Matches NO_SYNONYMS  → "no"
 *  5. Neither              → "unknown"
 *
 * Returns "unknown" (not null/undefined) so callers can distinguish
 * "heard but unrecognised" from "no recognition event at all".
 */
export function normalizeToYesNo(rawText: string): "yes" | "no" | "unknown" {
  const t = preprocess(rawText);
  if (!t) return "unknown";

  // Negation guard: a negation word blocks the YES branch.
  const negated = NEGATION_REGEX.test(t);

  if (!negated && YES_REGEX.test(t)) return "yes";
  if (NO_REGEX.test(t))              return "no";

  return "unknown";
}

/**
 * Classify a confidence score into a named tier.
 *
 * A score of exactly 0 is treated as "high" because the Chrome SR interim
 * fallback path emits confidence=0 when it synthesises a final result from
 * an interim transcript — in that case the reliability layer has already
 * accepted the text via the final-event path and should not re-check.
 */
export function normalizeConfidence(
  confidence: number,
  thresholds: ConfidenceThresholds = CONFIDENCE_THRESHOLDS,
): "high" | "medium" | "low" | "interim-fallback" {
  if (confidence === 0)                           return "interim-fallback";
  if (confidence >= thresholds.HIGH)              return "high";
  if (confidence >= thresholds.MEDIUM)            return "medium";
  return "low";
}
