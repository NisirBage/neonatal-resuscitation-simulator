/**
 * Part 13 — Tests: Speech provider abstraction (Part 11).
 *
 * Verifies interface conformance without a real browser by providing a
 * mock implementation.  Proves the abstraction allows swapping providers
 * without touching any other code.
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import type { SpeechProvider, RecognitionResult, RecognitionErrorCode } from "../services/speechProvider";

// ── Mock implementation of SpeechProvider ─────────────────────────────────────

class MockSpeechProvider implements SpeechProvider {
  readonly name     = "mock";
  readonly supported = true;

  private _onResult?: (r: RecognitionResult) => void;
  private _onEnd?:   () => void;
  private _onError?: (code: RecognitionErrorCode, msg?: string) => void;

  started  = false;
  stopped  = false;
  aborted  = false;

  start(
    onResult: (r: RecognitionResult) => void,
    onEnd: () => void,
    onError: (code: RecognitionErrorCode, msg?: string) => void,
  ): void {
    this._onResult = onResult;
    this._onEnd    = onEnd;
    this._onError  = onError;
    this.started   = true;
  }

  stop():  void { this.stopped  = true; this._onEnd?.(); }
  abort(): void { this.aborted  = true; }

  /** Test helper: emit a result from the provider side */
  emitResult(transcript: string, confidence: number, isFinal: boolean): void {
    this._onResult?.({
      transcript, confidence, isFinal, timestamp: performance.now(),
    });
  }

  emitError(code: RecognitionErrorCode): void {
    this._onError?.(code);
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("SpeechProvider abstraction (Part 11)", () => {
  afterEach(() => { vi.restoreAllMocks(); });

  it("mock provider satisfies the SpeechProvider interface", () => {
    const provider: SpeechProvider = new MockSpeechProvider();
    expect(provider.name).toBe("mock");
    expect(provider.supported).toBe(true);
    expect(typeof provider.start).toBe("function");
    expect(typeof provider.stop).toBe("function");
    expect(typeof provider.abort).toBe("function");
  });

  it("start() receives callbacks and fires onResult", () => {
    const provider = new MockSpeechProvider();
    const onResult = vi.fn();
    const onEnd    = vi.fn();
    const onError  = vi.fn();

    provider.start(onResult, onEnd, onError);
    provider.emitResult("yes", 0.95, true);

    expect(onResult).toHaveBeenCalledOnce();
    expect(onResult.mock.calls[0][0]).toMatchObject({
      transcript: "yes",
      confidence: 0.95,
      isFinal:    true,
    });
  });

  it("stop() triggers onEnd", () => {
    const provider = new MockSpeechProvider();
    const onEnd = vi.fn();
    provider.start(vi.fn(), onEnd, vi.fn());
    provider.stop();
    expect(onEnd).toHaveBeenCalledOnce();
    expect(provider.stopped).toBe(true);
  });

  it("abort() does NOT call onEnd", () => {
    const provider = new MockSpeechProvider();
    const onEnd = vi.fn();
    provider.start(vi.fn(), onEnd, vi.fn());
    provider.abort();
    expect(onEnd).not.toHaveBeenCalled();
    expect(provider.aborted).toBe(true);
  });

  it("emits error codes without crashing", () => {
    const provider = new MockSpeechProvider();
    const onError = vi.fn();
    provider.start(vi.fn(), vi.fn(), onError);
    provider.emitError("no-speech");
    expect(onError).toHaveBeenCalledWith("no-speech");
  });

  it("a second provider implementation works the same way", () => {
    class AltProvider implements SpeechProvider {
      readonly name = "alt";
      readonly supported = false;
      start(): void { /* no-op */ }
      stop():  void { /* no-op */ }
      abort(): void { /* no-op */ }
    }
    const alt: SpeechProvider = new AltProvider();
    expect(alt.name).toBe("alt");
    expect(alt.supported).toBe(false);
  });
});
