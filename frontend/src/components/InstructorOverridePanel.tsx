import type { CurrentState } from "../types";

interface InstructorOverridePanelProps {
  busy: boolean;
  currentState: CurrentState | null;
  onSendEvent: (eventName: string) => Promise<void>;
  onTriggerTimer: (timerId: string) => Promise<void>;
}

function formatLabel(snakeCase: string): string {
  return snakeCase
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function InstructorOverridePanel({
  busy,
  currentState,
  onSendEvent,
  onTriggerTimer
}: InstructorOverridePanelProps) {
  const instructorTransitions = (currentState?.transitions ?? []).filter(
    (t) => t.trigger === "instructor" && typeof t.instructor_event === "string"
  );

  const manualTimers = (currentState?.timers ?? []).filter((t) => !t.auto_start);

  return (
    <section className="rounded-lg border border-amber-200 bg-white p-6 shadow-soft">
      <h2 className="text-lg font-semibold text-clinical-ink">Instructor Overrides</h2>
      <p className="mt-1 text-sm text-slate-500">
        Available transitions for the current state.
      </p>

      <div className="mt-4 space-y-2">
        {instructorTransitions.map((transition) => (
          <button
            className="w-full rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-left transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={busy}
            key={transition.id}
            onClick={() => void onSendEvent(transition.instructor_event as string)}
            type="button"
          >
            <span className="block text-sm font-semibold text-amber-900">
              {formatLabel(transition.instructor_event as string)}
            </span>
            <span className="mt-0.5 block font-mono text-xs text-amber-700">
              → {transition.target_state}
            </span>
          </button>
        ))}
        {currentState !== null && instructorTransitions.length === 0 ? (
          <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-600">
            No instructor overrides available for this state.
          </p>
        ) : null}
        {currentState === null ? (
          <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-600">
            Select a session to see available overrides.
          </p>
        ) : null}
      </div>

      {manualTimers.length > 0 ? (
        <div className="mt-5 border-t border-clinical-line pt-5">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Manual Timers
          </h3>
          <div className="mt-3 space-y-2">
            {manualTimers.map((timer) => (
              <button
                className="w-full rounded-md border border-clinical-line px-4 py-3 text-left text-sm font-medium text-clinical-ink transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={busy}
                key={timer.id}
                onClick={() => void onTriggerTimer(timer.id)}
                type="button"
              >
                Trigger {formatLabel(timer.id)} ({timer.duration_seconds}s)
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
