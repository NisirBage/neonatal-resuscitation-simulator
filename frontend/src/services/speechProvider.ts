/**
 * Speech recognition provider abstraction (Part 11).
 *
 * The current implementation delegates to the Chrome Web Speech API.
 * Future providers — Google Cloud Speech, Azure Cognitive Services,
 * Deepgram, OpenAI Whisper, Vosk — implement SpeechProvider and can
 * be swapped in without touching the FSM, WebSocket layer, or any
 * clinical workflow code.
 */

// ── Public types ─────────────────────────────────────────────────────────────

export interface RecognitionResult {
  transcript: string;
  /** 0–1. Chrome SR may return 0 for interim results. */
  confidence: number;
  isFinal: boolean;
  /** performance.now() at the moment the result arrived from the provider. */
  timestamp: number;
}

export type RecognitionErrorCode =
  | "no-speech"
  | "audio-capture"
  | "not-allowed"
  | "network"
  | "aborted"
  | "service-not-allowed"
  | "bad-grammar"
  | "language-not-supported"
  | "unknown";

export interface SpeechProvider {
  /** Human-readable identifier for diagnostics and telemetry. */
  readonly name: string;
  /** True when the provider can be used in the current browser/environment. */
  readonly supported: boolean;
  /**
   * Begin a recognition session.
   * @param onResult - fired for every interim AND final result
   * @param onEnd    - fired when the session ends naturally (no error)
   * @param onError  - fired for errors; "no-speech" and "aborted" are
   *                   informational and do NOT indicate a provider failure
   */
  start(
    onResult: (result: RecognitionResult) => void,
    onEnd: () => void,
    onError: (code: RecognitionErrorCode, message?: string) => void,
  ): void;
  /** Graceful stop — may still deliver buffered results before onEnd fires. */
  stop(): void;
  /** Immediate abort — no further results. */
  abort(): void;
}

// ── Factory ──────────────────────────────────────────────────────────────────

/** Returns the best available provider for the current environment. */
export function createDefaultProvider(): SpeechProvider {
  return new ChromeSpeechProvider();
}

// ── Chrome Web Speech API provider ───────────────────────────────────────────
// This is the only provider implemented. The abstraction allows adding
// Google, Azure, Deepgram, Whisper or Vosk without touching any other file.

interface ChromeSR extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string; message?: string }) => void) | null;
  onresult: ((e: {
    resultIndex: number;
    results: {
      length: number;
      [i: number]: {
        isFinal: boolean;
        length: number;
        [j: number]: { transcript: string; confidence: number };
      };
    };
  }) => void) | null;
}


const KNOWN_ERROR_CODES: RecognitionErrorCode[] = [
  "no-speech", "audio-capture", "not-allowed", "network",
  "aborted", "service-not-allowed", "bad-grammar", "language-not-supported",
];

class ChromeSpeechProvider implements SpeechProvider {
  readonly name = "chrome-web-speech-api";

  get supported(): boolean {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return Boolean((window as any).SpeechRecognition ?? window.webkitSpeechRecognition);
  }

  private _recognition: ChromeSR | null = null;

  start(
    onResult: (r: RecognitionResult) => void,
    onEnd: () => void,
    onError: (code: RecognitionErrorCode, message?: string) => void,
  ): void {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const Ctor: (new () => ChromeSR) | undefined = (window as any).SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Ctor) {
      onError("service-not-allowed", "SpeechRecognition is not available in this browser");
      return;
    }
    const recognition = new Ctor();
    recognition.continuous     = false;
    recognition.interimResults = true;
    recognition.lang           = "en-US";
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      const ts = performance.now();
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        onResult({
          transcript: (result[0]?.transcript ?? "").trim(),
          confidence: result[0]?.confidence ?? 0,
          isFinal:    result.isFinal ?? false,
          timestamp:  ts,
        });
      }
    };

    recognition.onend   = onEnd;
    recognition.onerror = (e: { error: string; message?: string }) => {
      const code: RecognitionErrorCode = KNOWN_ERROR_CODES.includes(e.error as RecognitionErrorCode)
        ? (e.error as RecognitionErrorCode)
        : "unknown";
      onError(code, e.message);
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    this._recognition = recognition as any;
    recognition.start();
  }

  stop(): void  { this._recognition?.stop(); }
  abort(): void { this._recognition?.abort(); this._recognition = null; }
}
