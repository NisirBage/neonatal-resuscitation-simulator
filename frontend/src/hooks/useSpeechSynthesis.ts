import { useCallback, useEffect, useMemo, useState } from "react";

export interface SpeechSynthesisControls {
  cancel: () => void;
  speak: (text: string) => void;
  speaking: boolean;
  supported: boolean;
}

export function useSpeechSynthesis(): SpeechSynthesisControls {
  const supported = useMemo(() => "speechSynthesis" in window, []);
  const [speaking, setSpeaking] = useState(false);

  const cancel = useCallback(() => {
    if (!supported) {
      return;
    }

    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      const cleanText = text.trim();
      if (!supported || cleanText.length === 0) {
        return;
      }

      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.lang = "en-US";
      utterance.rate = 0.95;
      utterance.pitch = 1;
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);
      window.speechSynthesis.speak(utterance);
    },
    [supported]
  );

  useEffect(() => cancel, [cancel]);

  return {
    cancel,
    speak,
    speaking,
    supported
  };
}
