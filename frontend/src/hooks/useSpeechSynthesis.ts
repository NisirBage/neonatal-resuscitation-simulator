import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export interface SpeechSynthesisControls {
  cancel: () => void;
  speak: (text: string, onEnd?: () => void) => void;
  speaking: boolean;
  supported: boolean;
  // Dev panel — returns current speech token without triggering re-renders
  getSpeechToken: () => number;
}

export function useSpeechSynthesis(): SpeechSynthesisControls {
  const supported = useMemo(() => "speechSynthesis" in window, []);
  const [speaking, setSpeaking] = useState(false);
  const tokenRef = useRef(0);

  const cancel = useCallback(() => {
    if (!supported) return;
    tokenRef.current += 1;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (text: string, onEnd?: () => void) => {
      const cleanText = text.trim();
      if (!supported || cleanText.length === 0) {
        onEnd?.();
        return;
      }

      tokenRef.current += 1;
      const myToken = tokenRef.current;

      window.speechSynthesis.cancel();

      // Chrome bug: speechSynthesis silently stalls when the page has been
      // idle or when the internal queue gets into a bad state.  resume()
      // clears the stall before we enqueue the new utterance.
      window.speechSynthesis.resume();

      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.lang = "en-US";
      utterance.rate = 0.9;
      utterance.pitch = 1;

      // Watchdog: if onstart hasn't fired within 5 s the browser silently
      // dropped the utterance.  Invoke onEnd so the voice pipeline continues.
      const watchdog = window.setTimeout(() => {
        if (tokenRef.current === myToken) {
          window.speechSynthesis.cancel();
          setSpeaking(false);
          onEnd?.();
        }
      }, 5000);

      utterance.onstart = () => {
        window.clearTimeout(watchdog);
        setSpeaking(true);
      };
      utterance.onend = () => {
        window.clearTimeout(watchdog);
        setSpeaking(false);
        if (tokenRef.current === myToken) onEnd?.();
      };
      utterance.onerror = () => {
        window.clearTimeout(watchdog);
        setSpeaking(false);
        if (tokenRef.current === myToken) onEnd?.();
      };
      window.speechSynthesis.speak(utterance);
    },
    [supported]
  );

  const getSpeechToken = useCallback(() => tokenRef.current, []);

  useEffect(() => cancel, [cancel]);

  return { cancel, speak, speaking, supported, getSpeechToken };
}
