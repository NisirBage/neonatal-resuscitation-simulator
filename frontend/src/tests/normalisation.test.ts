/**
 * Regression tests for the single-source-of-truth voice normaliser.
 *
 * All imports come from services/voice/normalize — the canonical module.
 * No other file may define equivalent synonym logic.
 *
 * Coverage:
 *   - Full YES synonym table
 *   - Full NO synonym table
 *   - Negation guard ("absolutely not" must never map to YES)
 *   - Contextual phrases ("yes sir", "no doctor")
 *   - Case insensitivity
 *   - Punctuation stripping
 *   - Unknown / noise inputs
 *   - Partial-word boundary guard (no over-matching)
 *   - normalizeConfidence() tier classification
 */

import { describe, it, expect } from "vitest";
import {
  normalizeToYesNo,
  normalizeConfidence,
  YES_SYNONYMS,
  NO_SYNONYMS,
  CONFIDENCE_THRESHOLDS,
} from "../services/voice/normalize";

// ── YES synonyms ──────────────────────────────────────────────────────────────

describe("normalizeToYesNo — YES synonyms", () => {
  for (const word of YES_SYNONYMS) {
    it(`"${word}" → yes`, () => {
      expect(normalizeToYesNo(word)).toBe("yes");
    });
  }
});

// ── NO synonyms ───────────────────────────────────────────────────────────────

describe("normalizeToYesNo — NO synonyms", () => {
  for (const word of NO_SYNONYMS) {
    it(`"${word}" → no`, () => {
      expect(normalizeToYesNo(word)).toBe("no");
    });
  }
});

// ── Required regression phrases (from audit spec) ─────────────────────────────

describe("normalizeToYesNo — required regression phrases", () => {
  const YES_PHRASES = ["yes", "yeah", "yep", "affirmative", "correct", "absolutely yes"];
  const NO_PHRASES  = ["no", "nope", "negative", "nah", "absolutely not", "not at all", "never", "incorrect"];

  for (const phrase of YES_PHRASES) {
    it(`"${phrase}" → yes`, () => {
      expect(normalizeToYesNo(phrase)).toBe("yes");
    });
  }

  for (const phrase of NO_PHRASES) {
    it(`"${phrase}" → no or unknown (never yes)`, () => {
      expect(normalizeToYesNo(phrase)).not.toBe("yes");
    });
  }
});

// ── Negation guard ────────────────────────────────────────────────────────────
// "absolutely not" — the bug that was introduced without a single source of
// truth. This block is the canonical regression proof for that class of error.

describe("normalizeToYesNo — negation guard", () => {
  it('"absolutely not" → unknown  (affirmative + negation → blocked)', () => {
    expect(normalizeToYesNo("absolutely not")).toBe("unknown");
  });
  it('"not at all" → unknown', () => {
    expect(normalizeToYesNo("not at all")).toBe("unknown");
  });
  it('"not sure" → unknown', () => {
    expect(normalizeToYesNo("not sure")).toBe("unknown");
  });
  it('"no absolutely" → no  (explicit NO synonym wins)', () => {
    expect(normalizeToYesNo("no absolutely")).toBe("no");
  });
  it('"never" alone → no  (negation word that is also a NO synonym)', () => {
    expect(normalizeToYesNo("never")).toBe("no");
  });
  it('"yes" alone → yes  (negation guard must not block plain yes)', () => {
    expect(normalizeToYesNo("yes")).toBe("yes");
  });
  it('"absolutely" alone → yes  (no negation present)', () => {
    expect(normalizeToYesNo("absolutely")).toBe("yes");
  });
});

// ── Contextual phrases ────────────────────────────────────────────────────────

describe("normalizeToYesNo — contextual phrases", () => {
  it('"yes sir" → yes',        () => expect(normalizeToYesNo("yes sir")).toBe("yes"));
  it('"yes doctor" → yes',     () => expect(normalizeToYesNo("yes doctor")).toBe("yes"));
  it('"no sir" → no',          () => expect(normalizeToYesNo("no sir")).toBe("no"));
  it('"no doctor" → no',       () => expect(normalizeToYesNo("no doctor")).toBe("no"));
  it('"yes please" → yes',     () => expect(normalizeToYesNo("yes please")).toBe("yes"));
  it('"no thank you" → no',    () => expect(normalizeToYesNo("no thank you")).toBe("no"));
});

// ── Case insensitivity and punctuation ────────────────────────────────────────

describe("normalizeToYesNo — case and punctuation", () => {
  it('"YES" → yes',       () => expect(normalizeToYesNo("YES")).toBe("yes"));
  it('"No." → no',        () => expect(normalizeToYesNo("No.")).toBe("no"));
  it('"YEP!" → yes',      () => expect(normalizeToYesNo("YEP!")).toBe("yes"));
  it('"NEGATIVE." → no',  () => expect(normalizeToYesNo("NEGATIVE.")).toBe("no"));
  it('"Yeah," → yes',     () => expect(normalizeToYesNo("Yeah,")).toBe("yes"));
});

// ── Unknown / noise inputs ────────────────────────────────────────────────────

describe("normalizeToYesNo — unknown inputs", () => {
  for (const word of ["", "  ", "um", "uh", "maybe", "Ek", "the", "a", "background noise xyz"]) {
    it(`"${word}" → unknown`, () => {
      expect(normalizeToYesNo(word)).toBe("unknown");
    });
  }
});

// ── Partial-word boundary (must not over-match) ───────────────────────────────

describe("normalizeToYesNo — word-boundary enforcement", () => {
  it('"noisy" does not match "no"',      () => expect(normalizeToYesNo("noisy")).toBe("unknown"));
  it('"notable" does not match "no"',    () => expect(normalizeToYesNo("notable")).toBe("unknown"));
  it('"yesterday" does not match "yes"', () => expect(normalizeToYesNo("yesterday")).toBe("unknown"));
  it('"yesno" does not match either',    () => expect(normalizeToYesNo("yesno")).toBe("unknown"));
});

// ── normalizeConfidence ───────────────────────────────────────────────────────

describe("normalizeConfidence", () => {
  it("0 → interim-fallback (Chrome SR path)", () => {
    expect(normalizeConfidence(0)).toBe("interim-fallback");
  });
  it("0.80 → high (at threshold)", () => {
    expect(normalizeConfidence(0.80)).toBe("high");
  });
  it("0.95 → high", () => {
    expect(normalizeConfidence(0.95)).toBe("high");
  });
  it("0.60 → medium (at threshold)", () => {
    expect(normalizeConfidence(0.60)).toBe("medium");
  });
  it("0.75 → medium", () => {
    expect(normalizeConfidence(0.75)).toBe("medium");
  });
  it("0.59 → low", () => {
    expect(normalizeConfidence(0.59)).toBe("low");
  });
  it("0.01 → low", () => {
    expect(normalizeConfidence(0.01)).toBe("low");
  });
  it("respects custom thresholds", () => {
    expect(normalizeConfidence(0.82, { HIGH: 0.95, MEDIUM: 0.70 })).toBe("medium");
  });
  it("CONFIDENCE_THRESHOLDS.HIGH is 0.80", () => {
    expect(CONFIDENCE_THRESHOLDS.HIGH).toBe(0.80);
  });
  it("CONFIDENCE_THRESHOLDS.MEDIUM is 0.60", () => {
    expect(CONFIDENCE_THRESHOLDS.MEDIUM).toBe(0.60);
  });
});
