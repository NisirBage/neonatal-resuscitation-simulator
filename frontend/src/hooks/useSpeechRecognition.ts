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
  start(): void;
  stop(): void;
  abort(): void;
  onend: (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventResult) => void) | null;
  onresult: ((event: SpeechRecognitionEventResult) => void) | null;
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
}

export function useSpeechRecognition(): SpeechRecognitionControls {
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const [transcript, setTranscript] = useState("");
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const SpeechRecognitionConstructor = useMemo(
    () => window.SpeechRecognition ?? window.webkitSpeechRecognition,
    []
  );

  const supported = Boolean(SpeechRecognitionConstructor);

  const startListening = useCallback(() => {
    if (!SpeechRecognitionConstructor) {
      setError("Speech recognition is not available in this browser.");
      return;
    }

    const recognition = new SpeechRecognitionConstructor();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";
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

  return {
    error,
    listening,
    resetTranscript,
    startListening,
    stopListening,
    supported,
    transcript
  };
}
