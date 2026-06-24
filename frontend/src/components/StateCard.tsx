import { ActiveTimerDisplay } from "./ActiveTimerDisplay";
import { ConnectionStatusBadge } from "./ConnectionStatusBadge";
import type { ActiveTimerView } from "../hooks/useTimerCountdown";
import type { CurrentState } from "../types";

interface StateCardProps {
  state: CurrentState | null;
  websocketStatus: string;
  activeTimer: ActiveTimerView | null;
}

export function StateCard({ state, websocketStatus, activeTimer }: StateCardProps) {
  if (!state) {
    return (
      <section className="rounded-lg border border-clinical-line bg-white p-6 shadow-soft">
        <p className="text-sm font-medium uppercase tracking-wide text-clinical-green">
          Session not started
        </p>
        <h2 className="mt-3 text-2xl font-semibold text-clinical-ink">
          Select a scenario and start training.
        </h2>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-clinical-line bg-white p-6 shadow-soft">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-clinical-green">
            Current State
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-clinical-ink">{state.name}</h2>
        </div>
        <ConnectionStatusBadge websocketStatus={websocketStatus} />
      </div>
      <p className="mt-4 max-w-3xl text-base leading-7 text-slate-700">
        {state.description ?? "No description available for this state."}
      </p>

      {state.timers.length > 0 ? (
        <div className="mt-5 rounded-lg border border-teal-100 bg-teal-50/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-teal-800">
            Active Timer
          </p>
          <div className="mt-3">
            <ActiveTimerDisplay timer={activeTimer} />
          </div>
        </div>
      ) : (
        <div className="mt-5 rounded-full bg-slate-100 px-3 py-2 text-sm text-slate-600 inline-block">
          No timers in this state
        </div>
      )}
    </section>
  );
}