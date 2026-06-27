import { useCallback, useMemo, useRef, useState } from "react";

interface SpeechRecognitionAlternativeResult {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultItem {
  readonly 0: SpeechRecognitionAlternativeResult;
  isFinal: boolean;
  length: number;
}

interface SpeechRecognitionResultCollection {
  readonly length: number;
  item(index: number): SpeechRecognitionResultItem;
  [index: number]: SpeechRecognitionResultItem;
}

interface SpeechRecognitionEventResult extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultCollection;
}

interface SpeechRecognitionErrorEventResult extends Event {
  error: string;
  message?: string;
}

interface BrowserSpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart:       (() => void) | null;
  onaudiostart:  (() => void) | null;
  onsoundstart:  (() => void) | null;
  onspeechstart: (() => void) | null;
  onend:   (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventResult) => void) | null;
  onresult:((event: SpeechRecognitionEventResult) => void) | null;
}

interface BrowserSpeechRecognitionConstructor {
  new (): BrowserSpeechRecognition;
}

declare global {
  interface Window {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  }
}

export interface SpeechRecognitionControls {
  error: string | null;
  listening: boolean;
  resetTranscript: () => void;
  startListening: () => void;
  stopListening: () => void;
  supported: boolean;
  transcript: string;
  // Continuous mode — microphone stays active until stopContinuous() is called
  continuousActive: boolean;
  startContinuous: (onFinalResult: (text: string) => void) => void;
  stopContinuous: () => void;
  // Dev panel — returns current generation counter without triggering re-renders
  getGeneration: () => number;
}

// Lightweight voice-pipeline logger — filter on "[VOICE]" in DevTools console.
function vr(msg: string, data?: Record<string, unknown>): void {
  const ts = new Date().toLocaleTimeString("en-US", {
    hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  if (data !== undefined) {
    console.log(`[VOICE ${ts}] ${msg}`, data);
  } else {
    console.log(`[VOICE ${ts}] ${msg}`);
  }
}

export function useSpeechRecognition(): SpeechRecognitionControls {
  const recognitionRef        = useRef<BrowserSpeechRecognition | null>(null);
  const continuousActiveRef   = useRef(false);
  const onFinalResultRef      = useRef<((text: string) => void) | null>(null);
  const restartTimerRef       = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Generation counter: incremented by stopContinuous() so that any pending
  // onend handler from the old recognition instance sees a stale generation
  // and does NOT launch a new recognition session.
  const genRef                = useRef(0);

  const [transcript, setTranscript]         = useState("");
  const [listening, setListening]           = useState(false);
  const [error, setError]                   = useState<string | null>(null);
  const [continuousActive, setContinuousActive] = useState(false);

  const SpeechRecognitionConstructor = useMemo(
    () => window.SpeechRecognition ?? window.webkitSpeechRecognition,
    []
  );

  const supported = Boolean(SpeechRecognitionConstructor);

  // ── Single-utterance mode (existing API, unchanged) ─────────────────────────
  const startListening = useCallback(() => {
    if (!SpeechRecognitionConstructor) {
      setError("Speech recognition is not available in this browser.");
      return;
    }

    const recognition = new SpeechRecognitionConstructor();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const spoken = Array.from({ length: event.results.length }, (_, index) => {
        return event.results[index]?.[0]?.transcript ?? "";
      }).join(" ");
      setTranscript(spoken.trim());
    };
    recognition.onerror = (event) => {
      setError(event.message ?? event.error);
      setListening(false);
    };
    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    setError(null);
    setListening(true);
    recognition.start();
  }, [SpeechRecognitionConstructor]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setError(null);
  }, []);

  // ── Continuous mode ──────────────────────────────────────────────────────────
  const stopContinuous = useCallback(() => {
    continuousActiveRef.current = false;
    genRef.current += 1;          // invalidate pending onend handlers from old instances
    onFinalResultRef.current = null;
    if (restartTimerRef.current !== null) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    // abort() terminates immediately without firing onresult; stop() would
    // keep processing pending audio and still fire onend.  We want neither.
    recognitionRef.current?.abort();
    setListening(false);
    setContinuousActive(false);
  }, []);

  const startContinuous = useCallback(
    (onFinalResult: (text: string) => void) => {
      if (!SpeechRecognitionConstructor) {
        setError("Speech recognition is not available in this browser.");
        return;
      }

      // Guard: if an old recognition session is still alive, invalidate it so
      // its onend does not restart.  This prevents duplicate recognition instances
      // if startContinuous is called without a preceding stopContinuous().
      if (continuousActiveRef.current) {
        genRef.current += 1;
        if (restartTimerRef.current !== null) {
          clearTimeout(restartTimerRef.current);
          restartTimerRef.current = null;
        }
        recognitionRef.current?.abort();
      }

      // Store the callback and mark active
      onFinalResultRef.current = onFinalResult;
      continuousActiveRef.current = true;
      setContinuousActive(true);

      const launchRecognition = () => {
        if (!continuousActiveRef.current || !SpeechRecognitionConstructor) return;

        // Capture generation at launch time.  If stopContinuous() is called
        // before this recognition's onend fires, genRef will have been
        // incremented and the stale onend will bail out without restarting.
        const capturedGen = genRef.current;

        // Per-session tracking:
        // finalDelivered — true when isFinal=true was processed in this session.
        // lastInterim    — last non-empty interim transcript; used as fallback
        //                  when Chrome fires onend without a final result (a
        //                  known Chromium behaviour for short utterances like
        //                  "yes" / "no" with continuous=false).
        let finalDelivered = false;
        let lastInterim    = "";

        const recognition = new SpeechRecognitionConstructor();
        // continuous: false + manual restart is more reliable than continuous: true
        // (Chrome stops continuous mode unpredictably on silence)
        recognition.continuous     = false;
        recognition.interimResults = true;
        recognition.lang           = "en-US";
        recognition.maxAlternatives = 1;

        // ── Lifecycle instrumentation ──────────────────────────────────────────
        recognition.onstart = () => {
          vr("onstart — microphone open, sending audio to recognition service");
        };
        recognition.onaudiostart = () => {
          vr("onaudiostart — audio capture has begun");
        };
        recognition.onsoundstart = () => {
          vr("onsoundstart — sound detected in audio stream");
        };
        recognition.onspeechstart = () => {
          vr("onspeechstart — speech detected (voice activity confirmed)");
        };

        recognition.onresult = (event) => {
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const result     = event.results[i];
            const text       = (result[0]?.transcript ?? "").trim();
            const isFinal    = result?.isFinal ?? false;
            const confidence = result[0]?.confidence ?? 0;

            vr(`onresult`, {
              index:      i,
              isFinal,
              confidence: confidence.toFixed(2),
              transcript: text,
              gen:        capturedGen,
            });

            if (isFinal) {
              if (text) {
                finalDelivered = true;
                lastInterim    = "";
                setTranscript(text);
                vr(`FINAL transcript="${text}" — invoking callback`);
                onFinalResultRef.current?.(text);
              }
            } else {
              // Track interim for the Chrome fallback (see onend below)
              if (text) lastInterim = text;
            }
          }
        };

        recognition.onerror = (event) => {
          vr(`onerror`, { error: event.error, message: event.message });
          if (event.error === "no-speech") {
            // Silence — restart automatically via onend, not an error
            return;
          }
          if (event.error === "aborted") {
            // We called abort() intentionally in stopContinuous — not an error
            return;
          }
          if (event.error === "not-allowed" || event.error === "audio-capture") {
            setError(`Microphone error: ${event.error}. Please allow microphone access.`);
            continuousActiveRef.current = false;
            genRef.current += 1;
            setContinuousActive(false);
            setListening(false);
            return;
          }
          // Transient errors (network, etc.) — onend will handle restart
        };

        recognition.onend = () => {
          vr(`onend`, {
            finalDelivered,
            lastInterim,
            continuousActive: continuousActiveRef.current,
            gen:              genRef.current,
            capturedGen,
          });
          setListening(false);

          // ── Chrome isFinal omission workaround ─────────────────────────────
          // Chrome with continuous=false sometimes fires onend without ever
          // sending isFinal=true for short single-word utterances ("yes", "no").
          // The interim result was already sent to the UI (transcript panel) but
          // the callback was never invoked.  If we have an undelivered interim
          // and the session is still active (generation matches), treat it as
          // the final answer so the voice pipeline can advance.
          if (
            !finalDelivered &&
            lastInterim &&
            onFinalResultRef.current &&
            continuousActiveRef.current &&
            genRef.current === capturedGen
          ) {
            vr(`onend: INTERIM FALLBACK — Chrome did not send isFinal=true`,
              { transcript: lastInterim });
            const text = lastInterim;
            lastInterim = "";
            setTranscript(text);
            onFinalResultRef.current(text);
            // Do NOT restart — the callback manages the next phase.
            return;
          }

          // Normal restart: only if still in this generation and continuous mode
          // is still active (i.e. stopContinuous() was not called externally).
          if (continuousActiveRef.current && genRef.current === capturedGen) {
            // Brief pause before restart to prevent rapid-fire starts on silence
            restartTimerRef.current = setTimeout(launchRecognition, 150);
          }
        };

        recognitionRef.current = recognition;
        setError(null);
        setListening(true);

        try {
          recognition.start();
          vr(`recognition.start() called`, { gen: capturedGen });
        } catch (err) {
          // start() throws if already running — wait and retry
          vr(`recognition.start() threw — retrying in 300ms`, { err: String(err) });
          setListening(false);
          restartTimerRef.current = setTimeout(launchRecognition, 300);
        }
      };

      launchRecognition();
    },
    [SpeechRecognitionConstructor]
  );

  const getGeneration = useCallback(() => genRef.current, []);

  return {
    error,
    listening,
    resetTranscript,
    startListening,
    stopListening,
    supported,
    transcript,
    continuousActive,
    startContinuous,
    stopContinuous,
    getGeneration,
  };
}
