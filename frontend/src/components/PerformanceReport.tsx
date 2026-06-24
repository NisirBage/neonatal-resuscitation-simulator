import type { SessionMetrics } from "../types";

interface PerformanceReportProps {
  metrics: SessionMetrics;
}

function formatDuration(seconds: number): string {
  if (seconds < 1) return "< 1s";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

interface MetricRowProps {
  label: string;
  value: string | number;
  accent?: boolean;
}

function MetricRow({ label, value, accent = false }: MetricRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 border-b border-clinical-line last:border-0">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd
        className={`text-sm font-semibold tabular-nums ${
          accent ? "text-clinical-rose" : "text-clinical-ink"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

export function PerformanceReport({ metrics }: PerformanceReportProps) {
  const isComplete = metrics.completion_status === "complete";

  return (
    <section className="rounded-lg border border-clinical-green/40 bg-white p-6 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-clinical-green">
            Session Complete
          </p>
          <h2 className="mt-1 text-xl font-semibold text-clinical-ink">Performance Report</h2>
        </div>
        <span
          className={`mt-1 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            isComplete
              ? "bg-emerald-100 text-emerald-800"
              : "bg-amber-100 text-amber-800"
          }`}
        >
          {isComplete ? "Complete" : "In Progress"}
        </span>
      </div>

      <dl className="mt-5">
        <MetricRow
          label="Total Duration"
          value={formatDuration(metrics.total_duration_seconds)}
        />
        <MetricRow
          label="Student Inputs"
          value={metrics.student_input_count}
        />
        <MetricRow
          label="Voice Inputs"
          value={metrics.voice_input_count}
        />
        <MetricRow
          label="Successful Transitions"
          value={metrics.successful_transition_count}
        />
        <MetricRow
          label="Unmatched Inputs"
          value={metrics.no_transition_count}
          accent={metrics.no_transition_count > 0}
        />
        <MetricRow
          label="Instructor Interventions"
          value={metrics.instructor_intervention_count}
          accent={metrics.instructor_intervention_count > 0}
        />
        <MetricRow
          label="Timer Events"
          value={metrics.timer_event_count}
        />
      </dl>
    </section>
  );
}
