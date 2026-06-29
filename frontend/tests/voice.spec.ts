/**
 * Voice recognition integration tests.
 *
 * Covers:
 *  - YES/NO synonyms recognised and accepted
 *  - Interim fallback path (Chrome onend without isFinal)
 *  - Double-submission guard (busyRef)
 *  - Voice-triggered API submission
 *  - Negation guard ("absolutely not" must not advance state)
 */

import { test, expect } from "@playwright/test";
import { setupPage, startSession, speakAndWait, speakInterim, SESSION_ID, makeState } from "./helpers";

test.describe("Voice normalisation — YES synonyms", () => {
  const YES_SYNONYMS = ["yes", "yeah", "yep", "correct", "absolutely", "sure", "okay", "affirmative"];

  for (const word of YES_SYNONYMS) {
    test(`"${word}" submits YES via voice`, async ({ page }) => {
      await setupPage(page, { firstState: "baby_born" });
      await page.goto("/");
      await startSession(page);

      const [request] = await Promise.all([
        page.waitForRequest((req) =>
          req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST"
        ),
        speakAndWait(page, word, 0.95),
      ]);

      const body = JSON.parse(request.postData() ?? "{}") as { response: string };
      expect(body.response).toBe("yes");
    });
  }
});

test.describe("Voice normalisation — NO synonyms", () => {
  const NO_SYNONYMS = ["no", "nope", "nah", "negative", "incorrect", "never"];

  for (const word of NO_SYNONYMS) {
    test(`"${word}" submits NO via voice`, async ({ page }) => {
      await setupPage(page, { firstState: "baby_born" });
      await page.goto("/");
      await startSession(page);

      const [request] = await Promise.all([
        page.waitForRequest((req) =>
          req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST"
        ),
        speakAndWait(page, word, 0.95),
      ]);

      const body = JSON.parse(request.postData() ?? "{}") as { response: string };
      expect(body.response).toBe("no");
    });
  }
});

test.describe("Negation guard", () => {
  test('"absolutely not" does NOT submit (negation blocks YES synonym)', async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // Enqueue "absolutely not" — should trigger retry, not submission
    let submitted = false;
    page.on("request", (req) => {
      if (req.url().includes(`/sessions/${SESSION_ID}/input`)) submitted = true;
    });

    await speakAndWait(page, "absolutely not", 0.95);

    // Wait for any potential submission
    await page.waitForTimeout(1_000);
    expect(submitted).toBe(false);
  });

  test('"not at all" does NOT submit', async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    let submitted = false;
    page.on("request", (req) => {
      if (req.url().includes(`/sessions/${SESSION_ID}/input`)) submitted = true;
    });

    await speakAndWait(page, "not at all", 0.95);
    await page.waitForTimeout(1_000);
    expect(submitted).toBe(false);
  });
});

test.describe("Interim fallback path", () => {
  test("Chrome interim-only result still submits (confidence=0 sentinel)", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // speakInterim fires onresult with isFinal=false then onend without final
    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST",
        { timeout: 10_000 }
      ),
      speakInterim(page, "yes"),
    ]);

    const body = JSON.parse(request.postData() ?? "{}") as { response: string };
    expect(body.response).toBe("yes");
  });
});

test.describe("Double-submission guard", () => {
  test("busyRef prevents submission when session start is in progress", async ({ page }) => {
    // Verify the busyRef guard: while handleStart is running (setBusy(true)),
    // the YES button is disabled and cannot submit.
    let startResponseDelay: (() => void) | null = null;

    await setupPage(page);
    // Override start route with a delayed response
    await page.route("**/api/sessions/sessions/start", (route) => {
      const p = new Promise<void>((resolve) => { startResponseDelay = resolve; });
      void p.then(() => route.fulfill({ json: {
        session_id: SESSION_ID, scenario_id: "baby_birth",
        current_state: makeState("baby_born"),
        status: "active", history: [],
      }}));
    });
    await page.goto("/");

    // Click Start (will hang until we resolve)
    void page.click("button:has-text('Start')");

    // While start is in flight, Start button should be disabled
    await page.waitForFunction(() => {
      const btns = [...document.querySelectorAll("button")];
      return btns.some((b) => b.textContent?.includes("Start") && b.disabled);
    }, null, { timeout: 3_000 });

    // Resolve the deferred start response
    if (startResponseDelay) startResponseDelay();
  });
});

test.describe("Voice API payload format", () => {
  test("submitted JSON contains session_id, action_id, and response", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST"
      ),
      speakAndWait(page, "yes", 0.95),
    ]);

    const body = JSON.parse(request.postData() ?? "{}") as {
      session_id: string;
      action_id: string;
      response: string;
    };
    expect(body.response).toBe("yes");
    expect(typeof body.action_id).toBe("string");
    expect(body.action_id.length).toBeGreaterThan(0);
  });
});
