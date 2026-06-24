import type { ActionSummary, CurrentState } from "../types";

interface ActionPanelProps {
  busy: boolean;
  currentState: CurrentState | null;
  onSubmitAction: (action: ActionSummary, response: string) => Promise<void>;
  onTriggerTimer: (timerId: string) => Promise<void>;
  response: string;
  setResponse: (response: string) => void;
  selectedActionId: string;
  setSelectedActionId: (actionId: string) => void;
  speechError: string | null;
  speechSupported: boolean;
  listening: boolean;
  onStartListening: () => void;
  onStopListening: () => void;
}

export function ActionPanel({
  busy,
  currentState,
  onSubmitAction,
  onTriggerTimer,
  response,
  setResponse,
  selectedActionId,
  setSelectedActionId,
  speechError,
  speechSupported,
  listening,
  onStartListening,
  onStopListening
}: ActionPanelProps) {
  const studentActions = currentState?.actions.filter((action) => action.type !== "audio") ?? [];
  const selectedAction = studentActions.find((action) => action.id === selectedActionId);

  return (
    <section className="rounded-lg border border-clinical-line bg-white p-6 shadow-soft">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-clinical-ink">Student Actions</h2>
        <button
          className="rounded-md border border-clinical-line px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!speechSupported}
          onClick={listening ? onStopListening : onStartListening}
          type="button"
        >
          {listening ? "Stop Voice" : "Use Voice"}
        </button>
      </div>

      {speechError ? <p className="mt-3 text-sm text-clinical-rose">{speechError}</p> : null}

      <div className="mt-5 space-y-3">
        {studentActions.map((action) => (
          <button
            className={`w-full rounded-md border px-4 py-3 text-left transition ${
              selectedActionId === action.id
                ? "border-clinical-green bg-teal-50"
                : "border-clinical-line bg-white hover:bg-slate-50"
            }`}
            key={action.id}
            onClick={() => {
              setSelectedActionId(action.id);
              setResponse("");
            }}
            type="button"
          >
            <span className="block text-sm font-semibold text-clinical-ink">{action.id}</span>
            <span className="mt-1 block text-sm text-slate-600">
              {action.prompt ?? action.type}
            </span>
          </button>
        ))}
        {currentState && studentActions.length === 0 ? (
          <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-600">
            This state has no student actions.
          </p>
        ) : null}
      </div>

      {selectedAction ? (
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void onSubmitAction(selectedAction, response);
          }}
        >
          {selectedAction.type === "yes_no" ? (
            <div className="grid grid-cols-2 gap-3">
              {selectedAction.options.map((option) => (
                <button
                  className={`rounded-md border px-4 py-3 text-sm font-semibold transition ${
                    response === option
                      ? "border-clinical-green bg-clinical-green text-white"
                      : "border-clinical-line text-slate-700 hover:bg-slate-50"
                  }`}
                  key={option}
                  onClick={() => setResponse(option)}
                  type="button"
                >
                  {option.toUpperCase()}
                </button>
              ))}
            </div>
          ) : (
            <textarea
              className="min-h-28 w-full rounded-md border border-clinical-line p-3 text-sm text-clinical-ink outline-none transition focus:border-clinical-green focus:ring-2 focus:ring-teal-100"
              onChange={(event) => setResponse(event.target.value)}
              placeholder="Enter or dictate response"
              value={response}
            />
          )}

          <button
            className="w-full rounded-md bg-clinical-green px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={busy || response.trim().length === 0}
            type="submit"
          >
            Submit Response
          </button>
        </form>
      ) : null}

      <div className="mt-6 border-t border-clinical-line pt-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-600">Timers</h3>
        <div className="mt-3 space-y-2">
          {currentState?.timers.map((timer) => (
            <button
              className="w-full rounded-md border border-clinical-line px-4 py-3 text-left text-sm font-medium text-clinical-ink transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy}
              key={timer.id}
              onClick={() => void onTriggerTimer(timer.id)}
              type="button"
            >
              Trigger {timer.id} ({timer.duration_seconds}s)
            </button>
          ))}
          {currentState && currentState.timers.length === 0 ? (
            <p className="text-sm text-slate-500">No timers for this state.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
