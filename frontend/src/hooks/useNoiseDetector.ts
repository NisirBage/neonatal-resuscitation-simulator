/**
 * Microphone noise detector (Part 5).
 *
 * Measures RMS amplitude from the microphone stream using the Web Audio API
 * and classifies the environment as: silent | normal | noisy | clipping.
 *
 * Advisory only — this hook NEVER advances the FSM or blocks recognition.
 * It surfaces user-facing warnings only.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type NoiseLevel = "silent" | "normal" | "noisy" | "clipping";

export interface NoiseDetectorState {
  noiseLevel:  NoiseLevel;
  /** Instantaneous RMS value in the range 0–1. */
  rms:         number;
  supported:   boolean;
  /** Non-null when the environment warrants a user-facing warning. */
  warningMessage: string | null;
}

// Empirical RMS thresholds — tunable via environment variable or config.
const SILENCE_THRESHOLD  = 0.008;
const NOISY_THRESHOLD    = 0.15;
const CLIPPING_THRESHOLD = 0.90;
const SAMPLE_INTERVAL_MS = 200;
const BUFFER_SIZE        = 256;

const WARNING: Record<string, string> = {
  silent:   "No speech detected.",
  noisy:    "Environment is too noisy. Please move closer to the microphone.",
  clipping: "Microphone input is clipping. Please speak a little quieter.",
};

function getAudioContext(): typeof AudioContext | null {
  return window.AudioContext
    ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    ?? null;
}

export function useNoiseDetector(active: boolean): NoiseDetectorState {
  const Ctx = getAudioContext();
  const supported = Boolean(Ctx);

  const [noiseLevel, setNoiseLevel] = useState<NoiseLevel>("silent");
  const [rms, setRms]               = useState(0);

  const contextRef  = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef   = useRef<MediaStream | null>(null);
  const timerRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const bufRef      = useRef(new Float32Array(BUFFER_SIZE));

  const teardown = useCallback(() => {
    if (timerRef.current)  { clearInterval(timerRef.current); timerRef.current = null; }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void contextRef.current?.close();
    contextRef.current  = null;
    analyserRef.current = null;
    setNoiseLevel("silent");
    setRms(0);
  }, []);

  useEffect(() => {
    if (!active || !supported || !Ctx) { teardown(); return; }

    let cancelled = false;

    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }

        streamRef.current = stream;
        const ctx     = new Ctx();
        contextRef.current = ctx;

        const analyser = ctx.createAnalyser();
        analyser.fftSize = BUFFER_SIZE * 2;
        analyserRef.current = analyser;
        ctx.createMediaStreamSource(stream).connect(analyser);

        timerRef.current = setInterval(() => {
          if (!analyserRef.current) return;
          analyserRef.current.getFloatTimeDomainData(bufRef.current);
          let sum = 0;
          for (let i = 0; i < bufRef.current.length; i++) {
            sum += bufRef.current[i] * bufRef.current[i];
          }
          const r = Math.sqrt(sum / bufRef.current.length);
          setRms(r);
          setNoiseLevel(
            r >= CLIPPING_THRESHOLD ? "clipping"
            : r >= NOISY_THRESHOLD  ? "noisy"
            : r <= SILENCE_THRESHOLD ? "silent"
            : "normal"
          );
        }, SAMPLE_INTERVAL_MS);
      })
      .catch(() => {
        // getUserMedia refused — the main SR pipeline handles mic permissions;
        // noise detection simply becomes unavailable in that case.
      });

    return () => { cancelled = true; teardown(); };
  }, [active, supported, Ctx, teardown]);

  const warningMessage =
    noiseLevel === "silent"   ? WARNING.silent
    : noiseLevel === "noisy"  ? WARNING.noisy
    : noiseLevel === "clipping" ? WARNING.clipping
    : null;

  return { noiseLevel, rms, supported, warningMessage };
}
