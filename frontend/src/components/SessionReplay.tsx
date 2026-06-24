import { useEffect, useRef, useState } from "react";

import { getSessionReplay } from "../services/api";
import type { ReplayEvent, ReplayResponse } from "../types";

const EVENT_BADGE: Record<string, string> = {
  session_started:  "bg-clinical-green text-white",
  student_input:    "bg-clinical-blue text-white",
  audio_input:      "bg-indigo-500 text-white",
  state_transition: "bg-emerald-600 text-white",
  no_transition:    "bg-amber-500 text-white",
  instructor_event: "bg-clinical-rose text-white",
  timer_event:      "bg-purple-600 text-white",
};

function badgeClass(type: string): string {
  return EVENT_BADGE[type] ?? "bg-slate-500 text-white";
}

function relElapsed(event: ReplayEvent, first: ReplayEvent): string {
  const ms = new Date(event.timestamp).getTime() - new Date(first.timestamp).getTime();
  return `+${(ms / 1000).toFixed(1)}s`;
}

interface SessionReplayProps {
  sessionId: string;
  onClose: () => void;
}

export function SessionReplay({ sessionId, onClose }: SessionReplayProps) {
  const [replay, setReplay]       = useState<ReplayResponse | null>(null);
  const [loading, setLoading]     = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [index, setIndex]         = useState(0);
  const [playing, setPlaying]     = useState(false);

  const tickRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const rowRef     = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    setLoading(true);
    setFetchError(null);
    getSessionReplay(sessionId)
      .then((data) => { setReplay(data); setLoading(false); })
      .catch((err: unknown) => {
        setFetchError(err instanceof Error ? err.message : "Failed to load replay.");
        setLoading(false);
      });
  }, [sessionId]);

  // Auto-scroll active row
  useEffect(() => {
    rowRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [index]);

  // Play interval — 1.5 s per event
  useEffect(() => {
    if (!playing || !replay) return;
    tickRef.current = setInterval(() => {
      setIndex((prev) => {
        if (prev >= replay.event_count - 1) {
          setPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, 1500);
    return () => {
      if (tickRef.current !== null) clearInterval(tickRef.current);
    };
  }, [playing, replay]);

  const prev = () => { setPlaying(false); setIndex((i) => Math.max(0, i - 1)); };
  const next = () => {
    if (!replay) return;
    setPlaying(false);
    setIndex((i) => Math.min(replay.event_count - 1, i + 1));
  };

  const current: ReplayEvent | null = replay?.events[index] ?? null;
  const first:   ReplayEvent | null = replay?.events[0]     ?? null;

  return (
    <section className="rounded-lg border border-clinical-line bg-white shadow-soft">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-clinical-line px-6 py-4">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-clinical-green">
            Read-Only
          </p>
          <h2 className="text-xl font-semibold text-clinical-ink">Session Replay</h2>
        </div>
        <button
          className="rounded-md border border-clinical-line px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          onClick={onClose}
          type="button"
        >
          Close
        </button>
      </div>

      {loading ? (
        <div className="p-10 text-center text-sm text-slate-500">Loading replay…</div>
      ) : fetchError ? (
        <div className="p-6 text-sm text-clinical-rose">{fetchError}</div>
      ) : !replay || !current || !first ? (
        <div className="p-10 text-center text-sm text-slate-500">No events to replay.</div>
      ) : (
        <>
          {/* Current event detail */}
          <div className="border-b border-clinical-line bg-clinical-panel px-6 py-4">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${badgeClass(current.type)}`}
              >
                {current.type}
              </span>
              <span className="font-mono text-xs text-slate-500">
                {relElapsed(current, first)}
              </span>
              <span className="text-sm text-slate-500">
                Event {index + 1} of {replay.event_count}
              </span>
            </div>

            <dl className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
              <div>
                <dt className="text-xs font-medium text-slate-500">State</dt>
                <dd className="font-mono text-xs text-clinical-ink">{current.state_id}</dd>
              </div>
              {current.target_state_id ? (
                <div>
                  <dt className="text-xs font-medium text-slate-500">Target State</dt>
                  <dd className="font-mono text-xs text-clinical-ink">{current.target_state_id}</dd>
                </div>
              ) : null}
              {current.transition_id ? (
                <div>
                  <dt className="text-xs font-medium text-slate-500">Transition</dt>
                  <dd className="font-mono text-xs text-clinical-ink">{current.transition_id}</dd>
                </div>
              ) : null}
              {Object.keys(current.payload).length > 0 ? (
                <div className="col-span-2">
                  <dt className="text-xs font-medium text-slate-500">Payload</dt>
                  <dd className="break-all font-mono text-xs text-clinical-ink">
                    {JSON.stringify(current.payload)}
                  </dd>
                </div>
              ) : null}
            </dl>
          </div>

          {/* Timeline list */}
          <ul className="max-h-72 divide-y divide-clinical-line overflow-y-auto">
            {replay.events.map((ev, i) => (
              <li
                key={ev.id}
                ref={i === index ? rowRef : null}
                className={`flex cursor-pointer items-center gap-3 px-6 py-2.5 transition ${
                  i === index
                    ? "bg-teal-50 ring-1 ring-inset ring-clinical-green/30"
                    : "hover:bg-slate-50"
                }`}
                onClick={() => { setPlaying(false); setIndex(i); }}
              >
                <span className="w-6 shrink-0 text-right font-mono text-xs text-slate-400">
                  {i + 1}
                </span>
                <span
                  className={`shrink-0 inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${badgeClass(ev.type)}`}
                >
                  {ev.type}
                </span>
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-600">
                  {ev.state_id}
                </span>
                {ev.target_state_id ? (
                  <span className="shrink-0 font-mono text-xs text-slate-400">
                    → {ev.target_state_id}
                  </span>
                ) : null}
                <span className="shrink-0 font-mono text-xs text-slate-400">
                  {relElapsed(ev, first)}
                </span>
              </li>
            ))}
          </ul>

          {/* Playback controls */}
          <div className="flex items-center justify-center gap-3 border-t border-clinical-line px-6 py-4">
            <button
              className="rounded-md border border-clinical-line bg-white px-4 py-2 text-sm font-semibold text-clinical-ink hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={index === 0}
              onClick={prev}
              type="button"
            >
              ← Prev
            </button>
            <button
              className={`rounded-md px-5 py-2 text-sm font-semibold text-white transition ${
                playing
                  ? "bg-amber-500 hover:bg-amber-600"
                  : "bg-clinical-green hover:bg-teal-700"
              } disabled:cursor-not-allowed disabled:opacity-40`}
              disabled={index >= replay.event_count - 1 && !playing}
              onClick={() => setPlaying((p) => !p)}
              type="button"
            >
              {playing ? "⏸ Pause" : "▶ Play"}
            </button>
            <button
              className="rounded-md border border-clinical-line bg-white px-4 py-2 text-sm font-semibold text-clinical-ink hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={index >= replay.event_count - 1}
              onClick={next}
              type="button"
            >
              Next →
            </button>
          </div>
        </>
      )}
    </section>
  );
}
