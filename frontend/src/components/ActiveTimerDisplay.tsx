import type { ActiveTimerView } from "../hooks/useTimerCountdown";

interface ActiveTimerDisplayProps {
  timer: ActiveTimerView | null;
  compact?: boolean;
}

export function ActiveTimerDisplay({ timer, compact = false }: ActiveTimerDisplayProps) {
  if (!timer) {
    return (
      <p className={`text-slate-500 ${compact ? "text-sm" : "text-base"}`}>No active timers</p>
    );
  }

  const remainingLabel =
    timer.remainingSeconds === 1
      ? "1 second remaining"
      : `${timer.remainingSeconds} seconds remaining`;

  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className={`font-semibold text-clinical-ink ${compact ? "text-sm" : "text-lg"}`}>
          {timer.label}
        </p>
        {!timer.isAutoStart ? (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
            Manual
          </span>
        ) : null}
      </div>
      <p className={`text-slate-600 ${compact ? "text-sm" : "text-base"}`}>{remainingLabel}</p>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-clinical-green transition-[width] duration-1000 ease-linear"
          style={{ width: `${timer.progressPercent}%` }}
        />
      </div>
      {!compact ? (
        <p className="text-sm text-slate-500">
          {timer.isAutoStart
            ? `Auto timer · ${timer.durationSeconds}s total`
            : `Awaiting manual trigger · ${timer.durationSeconds}s`}
        </p>
      ) : null}
    </div>
  );
}