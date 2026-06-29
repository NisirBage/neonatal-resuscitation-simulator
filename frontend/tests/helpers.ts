/**
 * Shared test helpers for the NRS Playwright E2E suite.
 *
 * Provides:
 *  - Mock API fixtures (REST + WebSocket)
 *  - SpeechRecognition / SpeechSynthesis injection
 *  - Common UI actions (start session, click YES/NO)
 *
 * All REST calls go to http://localhost:8000 (VITE_API_BASE_URL default).
 * page.route() intercepts them regardless of CORS.
 */

import type { Page, Route, WebSocketRoute } from "@playwright/test";
import { SPEECH_RECOGNITION_MOCK } from "../mocks/speechRecognition";
import { SPEECH_SYNTHESIS_MOCK } from "../mocks/speechSynthesis";

// ── Scenario / session fixtures ───────────────────────────────────────────────

export const SCENARIO_ID = "baby_birth";
export const SESSION_ID  = "test-session-e2e-001";

/** Minimal scenario list returned by GET /api/scenarios/scenarios */
export const SCENARIO_LIST = [
  { id: "baby_birth", name: "Baby Birth — Neonatal Resuscitation", file_name: "baby_birth.json", version: "1.0" },
];

/** Build a minimal CurrentState object matching the server schema */
export function makeState(id: string, overrides: Record<string, unknown> = {}) {
  const STATE_NAMES: Record<string, string> = {
    baby_born:                    "Baby Born",
    put_on_mothers_chest:         "Placed on Mother's Chest",
    crying_assessment:            "Crying Assessment",
    apnea_assessment:             "Apnea Assessment",
    heart_rate_assessment:        "Heart Rate Assessment",
    ventilation_path:             "Ventilation Path",
    ventilation_in_progress:      "Ventilation in Progress",
    heart_rate_after_ventilation: "Heart Rate After Ventilation",
    ventilation_corrective_steps: "Corrective Steps",
    continue_ventilation_15s:     "Continue Ventilation (15 s)",
    routine_care:                 "Routine Care",
    simulation_complete:          "Simulation Complete",
  };

  const PROMPTS: Record<string, string> = {
    baby_born:                    "Has the baby been born?",
    put_on_mothers_chest:         "Has the baby been placed on the mother's chest?",
    crying_assessment:            "Is the baby crying?",
    apnea_assessment:             "Is the baby apneic?",
    heart_rate_assessment:        "Is the heart rate above 100 bpm?",
    ventilation_path:             "Start positive-pressure ventilation — are you ready to begin?",
    ventilation_in_progress:      "Provide 30 seconds of positive-pressure ventilation.",
    heart_rate_after_ventilation: "Is the heart rate increasing?",
    ventilation_corrective_steps: "Apply corrective ventilation steps. Done?",
    continue_ventilation_15s:     "Continue ventilation for 15 seconds and stop.",
    routine_care:                 "Routine care. Simulation complete.",
    simulation_complete:          "Simulation complete. Well done.",
  };

  // ActionSummary shape: { id, type, prompt, options, transcript_required, metadata }
  // Dashboard checks: a.type === "yes_no" && !a.metadata.fallback_only
  const yesNoAction = (id: string) => ({
    id,
    type: "yes_no" as const,
    prompt: null,
    options: ["yes", "no"],
    transcript_required: false,
    metadata: {},
  });

  const ACTIONS: Record<string, ReturnType<typeof yesNoAction>[]> = {
    baby_born:                    [yesNoAction("confirm_birth")],
    put_on_mothers_chest:         [yesNoAction("placed_on_chest")],
    crying_assessment:            [yesNoAction("is_baby_crying")],
    apnea_assessment:             [yesNoAction("is_apneic")],
    heart_rate_assessment:        [yesNoAction("hr_above_100")],
    ventilation_path:             [yesNoAction("start_ventilation")],
    ventilation_in_progress:      [yesNoAction("acknowledge_ventilation")],
    heart_rate_after_ventilation: [yesNoAction("hr_increasing")],
    ventilation_corrective_steps: [yesNoAction("corrective_steps_done")],
    continue_ventilation_15s:     [yesNoAction("continue_ventilation")],
    routine_care:                 [],
    simulation_complete:          [],
  };

  const TERMINAL = new Set(["routine_care", "simulation_complete"]);

  return {
    id,
    name:        STATE_NAMES[id] ?? id,
    description: PROMPTS[id] ?? id,
    actions: ACTIONS[id] ?? [],
    transitions: [],
    metadata: {
      voice_prompt: PROMPTS[id] ?? id,
      terminal:     TERMINAL.has(id),
    },
    timers: [],
    ...overrides,
  };
}

/** A full start-session response (matches SessionResponse / SessionStateResponse) */
export function makeStartResponse(firstState = "baby_born") {
  return {
    session_id:    SESSION_ID,
    scenario_id:   SCENARIO_ID,
    current_state: makeState(firstState),
    status:        "active",
    history:       [],
  };
}

// ── API route mocking ─────────────────────────────────────────────────────────

/**
 * Install all REST API mocks on the page.
 * Must be called before page.goto().
 *
 * Returns a `setState` function that tests can call to update what
 * GET /sessions/{id} returns (simulating a FSM transition).
 */
export async function setupApiMocks(page: Page, options: {
  firstState?: string;
  inputResponse?: Record<string, unknown>;
} = {}) {
  const firstState = options.firstState ?? "baby_born";
  let currentStateId = firstState;

  // Scenario list
  await page.route("**/api/scenarios/scenarios", (route: Route) => {
    route.fulfill({ json: SCENARIO_LIST });
  });

  // Start session
  await page.route("**/api/sessions/sessions/start", (route: Route) => {
    if (route.request().method() === "POST") {
      currentStateId = firstState;
      route.fulfill({ json: makeStartResponse(firstState) });
    } else {
      route.continue();
    }
  });

  // Stop session
  await page.route(`**/api/sessions/sessions/${SESSION_ID}/stop`, (route: Route) => {
    route.fulfill({ json: { ok: true } });
  });

  // Submit input — must return a valid SessionResponse (submitResponse reads current_state.id)
  // Return a "next" state to simulate a successful FSM transition.
  const NEXT_STATE: Record<string, string> = {
    baby_born:                    "put_on_mothers_chest",
    put_on_mothers_chest:         "crying_assessment",
    crying_assessment:            "apnea_assessment",
    apnea_assessment:             "heart_rate_assessment",
    heart_rate_assessment:        "simulation_complete",
    ventilation_path:             "ventilation_in_progress",
    ventilation_in_progress:      "heart_rate_after_ventilation",
    heart_rate_after_ventilation: "simulation_complete",
    ventilation_corrective_steps: "heart_rate_after_ventilation",
    continue_ventilation_15s:     "simulation_complete",
  };
  await page.route(`**/api/sessions/sessions/${SESSION_ID}/input`, (route: Route) => {
    if (options.inputResponse) {
      route.fulfill({ json: options.inputResponse });
    } else {
      const nextId = NEXT_STATE[currentStateId] ?? "simulation_complete";
      route.fulfill({ json: {
        session_id:    SESSION_ID,
        scenario_id:   SCENARIO_ID,
        current_state: makeState(nextId),
        status:        "active",
        history:       [],
      }});
    }
  });

  // Get session (used after WS event to refresh state)
  await page.route(`**/api/sessions/sessions/${SESSION_ID}`, (route: Route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ json: makeStartResponse(currentStateId) });
    } else {
      route.continue();
    }
  });

  // Session metrics
  await page.route(`**/api/sessions/sessions/${SESSION_ID}/metrics`, (route: Route) => {
    route.fulfill({ json: { total_attempts: 1, accuracy: 1.0 } });
  });

  // Exports
  await page.route(`**/api/sessions/sessions/${SESSION_ID}/export/clinical-csv`, (route: Route) => {
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/csv" },
      body: "timestamp,state_id,action_id,response\n2024-01-01T00:00:00Z,baby_born,confirm_birth,yes\n",
    });
  });
  await page.route(`**/api/sessions/sessions/${SESSION_ID}/export/clinical-xlsx`, (route: Route) => {
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      body: Buffer.from("PK\x03\x04"),
    });
  });
  await page.route(`**/api/sessions/sessions/${SESSION_ID}/report/pdf`, (route: Route) => {
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/pdf" },
      body: Buffer.from("%PDF-1.4\n"),
    });
  });
  await page.route(`**/api/sessions/sessions/${SESSION_ID}/export/csv`, (route: Route) => {
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/csv" },
      body: "session_id,state_id\n" + SESSION_ID + ",baby_born\n",
    });
  });

  const setState = (stateId: string) => { currentStateId = stateId; };
  return { setState };
}

// ── WebSocket mock ────────────────────────────────────────────────────────────

/**
 * Intercept the student WebSocket and return a handle that lets tests
 * send server-side events to the page.
 *
 * Usage:
 *   const ws = await setupWebSocketMock(page);
 *   await ws.sendEvent("fsm.state_transition");
 */
export async function setupWebSocketMock(page: Page): Promise<{
  sendEvent: (type: string, data?: Record<string, unknown>) => Promise<void>;
}> {
  let wsRouteRef: WebSocketRoute | null = null;

  await page.routeWebSocket("**/api/ws/sessions/**", (ws: WebSocketRoute) => {
    wsRouteRef = ws;
    // Accept the connection (don't forward to server)
    ws.onMessage(() => {
      // Client messages (ping / keepalive) — ignore
    });
  });

  const sendEvent = async (type: string, data: Record<string, unknown> = {}) => {
    if (!wsRouteRef) throw new Error("WebSocket not yet connected");
    await wsRouteRef.send(JSON.stringify({ type, ...data }));
  };

  return { sendEvent };
}

// ── Browser API mocks ─────────────────────────────────────────────────────────

/** Inject SpeechRecognition and SpeechSynthesis mocks before page load */
export async function injectVoiceMocks(page: Page) {
  await page.addInitScript({ content: SPEECH_RECOGNITION_MOCK });
  await page.addInitScript({ content: SPEECH_SYNTHESIS_MOCK });
}

// ── Composite setup ───────────────────────────────────────────────────────────

/** Full setup: inject mocks + install API routes. Returns control handles. */
export async function setupPage(page: Page, options: {
  firstState?: string;
} = {}) {
  await injectVoiceMocks(page);
  const { setState } = await setupApiMocks(page, options);
  const ws = await setupWebSocketMock(page);
  return { setState, ws };
}

// ── UI helpers ────────────────────────────────────────────────────────────────

/** Click Start and wait for the first FSM state prompt to appear in h2 */
export async function startSession(page: Page) {
  await page.click("button:has-text('Start')");
  // Wait until the idle placeholder is replaced by an actual state prompt
  await page.waitForFunction(() => {
    const h2 = document.querySelector("h2");
    if (!h2) return false;
    const text = h2.textContent ?? "";
    return text.length > 5 && !text.includes("Select a scenario");
  }, null, { timeout: 10_000 });
}

/** Simulate a recognised speech result then wait for API call */
export async function speakAndWait(page: Page, transcript: string, confidence = 0.95) {
  await page.evaluate(
    ([t, c]) => (window as unknown as { __speechMock: { enqueueResult: (t: string, c: number) => void } }).__speechMock.enqueueResult(t, c as number),
    [transcript, confidence] as [string, number],
  );
}

/** Simulate low-confidence noise input */
export async function speakNoise(page: Page, transcript = "static") {
  await page.evaluate(
    (t) => (window as unknown as { __speechMock: { enqueueBackgroundNoise: (t: string) => void } }).__speechMock.enqueueBackgroundNoise(t),
    transcript,
  );
}

/** Simulate the Chrome interim-fallback path (no isFinal=true) */
export async function speakInterim(page: Page, transcript: string) {
  await page.evaluate(
    (t) => (window as unknown as { __speechMock: { enqueueInterim: (t: string) => void } }).__speechMock.enqueueInterim(t),
    transcript,
  );
}
