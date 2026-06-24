import { ConnectionStatusBadge } from "./ConnectionStatusBadge";
import { ActiveTimerDisplay } from "./ActiveTimerDisplay";
import type { ActiveTimerView } from "../hooks/useTimerCountdown";
import type { CurrentState } from "../types";

interface DemoModePanelProps {
  sessionId: string | null;
  currentState: CurrentState | null;
  websocketStatus: string;
  activeTimer: ActiveTimerView | null;
  lastEventType: string | null;
  exportingCsv: boolean;
  onExportCsv: () => void;
}

export function DemoModePanel({
  sessionId,
  currentState,
  websocketStatus,
  activeTimer,
  lastEventType,
  exportingCsv,
  onExportCsv
}: DemoModePanelProps) {
  return (
    <section className="rounded-lg border border-clinical-green/30 bg-teal-50/40 p-5 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-clinical-ink">Demo Status</h2>
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="rounded-md border border-clinical-line bg-white px-3 py-1.5 text-sm font-semibold text-clinical-ink transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!sessionId || exportingCsv}
            onClick={onExportCsv}
            type="button"
          >
            {exportingCsv ? "Exporting..." : "Export Session CSV"}
          </button>
          <ConnectionStatusBadge websocketStatus={websocketStatus} />
        </div>
      </div>

      <dl className="mt-4 grid gap-3 text-sm">
        <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-2">
          <dt className="font-medium text-slate-500">Session ID</dt>
          <dd className="break-all font-mono text-xs text-clinical-ink">
            {sessionId ?? "Not started"}
          </dd>
        </div>
        <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-2">
          <dt className="font-medium text-slate-500">Current State</dt>
          <dd className="text-clinical-ink">
            {currentState ? (
              <>
                <span className="font-medium">{currentState.name}</span>
                <span className="mt-0.5 block font-mono text-xs text-slate-500">
                  {currentState.id}
                </span>
              </>
            ) : (
              "None"
            )}
          </dd>
        </div>
        <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-2">
          <dt className="font-medium text-slate-500">Last Event</dt>
          <dd className="break-all font-mono text-xs text-clinical-ink">
            {lastEventType ?? "None"}
          </dd>
        </div>
      </dl>

      <div className="mt-4 rounded-md border border-clinical-line bg-white p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Active Timer
        </p>
        <div className="mt-2">
          <ActiveTimerDisplay compact timer={activeTimer} />
        </div>
      </div>
    </section>
  );
}