import {
  PROFESSOR_WORKFLOW_STEPS,
  getWorkflowStepStatus,
  type WorkflowStepStatus
} from "../constants/demoWorkflow";
import type { CurrentState } from "../types";

interface ProgressPanelProps {
  currentState: CurrentState | null;
  scenarioId: string;
  sessionId: string | null;
  status: string;
}

const STEP_STATUS_STYLES: Record<
  WorkflowStepStatus,
  { icon: string; textClass: string; iconClass: string }
> = {
  complete: {
    icon: "✓",
    textClass: "text-slate-600",
    iconClass: "bg-emerald-100 text-emerald-700"
  },
  current: {
    icon: "●",
    textClass: "font-semibold text-clinical-ink",
    iconClass: "bg-clinical-green text-white"
  },
  pending: {
    icon: "□",
    textClass: "text-slate-400",
    iconClass: "bg-slate-100 text-slate-400"
  }
};

export function ProgressPanel({ currentState, scenarioId, sessionId, status }: ProgressPanelProps) {
  return (
    <section className="rounded-lg border border-clinical-line bg-white p-6 shadow-soft">
      <h2 className="text-lg font-semibold text-clinical-ink">Workflow Progress</h2>

      <ol className="mt-4 space-y-2">
        {PROFESSOR_WORKFLOW_STEPS.map((step, index) => {
          const stepStatus = getWorkflowStepStatus(index, currentState?.id);
          const styles = STEP_STATUS_STYLES[stepStatus];

          return (
            <li className="flex items-center gap-3 text-sm" key={step.label}>
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${styles.iconClass}`}
              >
                {styles.icon}
              </span>
              <span className={styles.textClass}>{step.label}</span>
            </li>
          );
        })}
      </ol>

      <dl className="mt-5 space-y-3 border-t border-clinical-line pt-4 text-sm">
        <div>
          <dt className="font-medium text-slate-500">Scenario</dt>
          <dd className="mt-1 break-words text-clinical-ink">{scenarioId || "Not selected"}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Runtime Status</dt>
          <dd className="mt-1 text-clinical-ink">{status}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Session</dt>
          <dd className="mt-1 break-all font-mono text-xs text-clinical-ink">
            {sessionId ?? "Not started"}
          </dd>
        </div>
      </dl>
    </section>
  );
}