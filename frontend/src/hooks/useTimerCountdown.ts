import { useEffect, useState } from "react";

import type { CurrentState, TimerSummary } from "../types";

export interface ActiveTimerView {
  id: string;
  label: string;
  durationSeconds: number;
  remainingSeconds: number;
  progressPercent: number;
  isAutoStart: boolean;
}

function timerLabel(timer: TimerSummary): string {
  const metadataLabel = timer.metadata.label;
  if (typeof metadataLabel === "string" && metadataLabel.trim().length > 0) {
    return metadataLabel;
  }

  return timer.id
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function pickDisplayTimer(timers: TimerSummary[]): TimerSummary | null {
  if (timers.length === 0) {
    return null;
  }

  return timers.find((timer) => timer.auto_start) ?? timers[0];
}

function buildTimerView(timer: TimerSummary, remainingSeconds: number): ActiveTimerView {
  const durationSeconds = timer.duration_seconds;
  const elapsed = Math.max(0, durationSeconds - remainingSeconds);
  const progressPercent =
    durationSeconds > 0 ? Math.min(100, Math.round((elapsed / durationSeconds) * 100)) : 0;

  return {
    id: timer.id,
    label: timerLabel(timer),
    durationSeconds,
    remainingSeconds,
    progressPercent,
    isAutoStart: timer.auto_start
  };
}

export function useTimerCountdown(currentState: CurrentState | null): ActiveTimerView | null {
  const [displayTimer, setDisplayTimer] = useState<TimerSummary | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [endsAtMs, setEndsAtMs] = useState<number | null>(null);

  useEffect(() => {
    if (!currentState) {
      setDisplayTimer(null);
      setRemainingSeconds(0);
      setEndsAtMs(null);
      return;
    }

    const timer = pickDisplayTimer(currentState.timers);
    setDisplayTimer(timer);

    if (!timer) {
      setRemainingSeconds(0);
      setEndsAtMs(null);
      return;
    }

    if (timer.auto_start) {
      setEndsAtMs(Date.now() + timer.duration_seconds * 1000);
      setRemainingSeconds(timer.duration_seconds);
      return;
    }

    setEndsAtMs(null);
    setRemainingSeconds(timer.duration_seconds);
  }, [currentState?.id]);

  useEffect(() => {
    if (!displayTimer?.auto_start || endsAtMs === null) {
      return;
    }

    const tick = () => {
      const remaining = Math.max(0, Math.ceil((endsAtMs - Date.now()) / 1000));
      setRemainingSeconds(remaining);
    };

    tick();
    const intervalId = window.setInterval(tick, 1000);
    return () => window.clearInterval(intervalId);
  }, [displayTimer?.id, displayTimer?.auto_start, endsAtMs]);

  if (!displayTimer) {
    return null;
  }

  return buildTimerView(displayTimer, remainingSeconds);
}