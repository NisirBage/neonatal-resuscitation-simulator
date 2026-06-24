import type { RuntimeEvent } from "../types";

interface EventPanelProps {
  events: RuntimeEvent[];
}

export function EventPanel({ events }: EventPanelProps) {
  return (
    <section className="rounded-lg border border-clinical-line bg-white p-6 shadow-soft">
      <h2 className="text-lg font-semibold text-clinical-ink">Live Events</h2>
      <div className="mt-4 max-h-96 space-y-3 overflow-auto pr-1">
        {events.map((event, index) => (
          <article className="rounded-md bg-slate-50 p-3" key={`${event.event_id ?? event.type}-${index}`}>
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-clinical-ink">{event.type}</p>
              {event.timestamp ? (
                <time className="text-xs text-slate-500">{new Date(event.timestamp).toLocaleTimeString()}</time>
              ) : null}
            </div>
            <pre className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-slate-600">
              {JSON.stringify(event.payload ?? event, null, 2)}
            </pre>
          </article>
        ))}
        {events.length === 0 ? (
          <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-600">
            Events will appear here when the session starts.
          </p>
        ) : null}
      </div>
    </section>
  );
}
