/**
 * Voice reliability layer E2E tests.
 *
 * Covers:
 *  - High confidence (≥ 0.80) → accepted immediately, no confirmation prompt
 *  - Medium confidence (0.60–0.79) → confirmation prompt shown
 *  - Low confidence (< 0.60) → retry, no submission
 *  - confidence=0 interim fallback → accepted (bypasses threshold check)
 *  - MAX_RETRIES reached → manual fallback shown
 *  - Reliability state resets on FSM state transition
 */

import { test, expect } from "@playwright/test";
import { setupPage, startSession, speakAndWait, speakInterim, speakNoise, SESSION_ID } from "./helpers";

test.describe("High confidence path", () => {
  test("confidence=0.95 is accepted immediately without confirmation", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const submitted: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes(`/sessions/${SESSION_ID}/input`)) {
        submitted.push(req.url());
      }
    });

    await speakAndWait(page, "yes", 0.95);
    await page.waitForTimeout(1_500);

    // Should have been submitted — no confirmation required
    expect(submitted.length).toBe(1);
    // No "Is that correct?" prompt should appear
    await expect(page.getByText(/is that correct/i)).not.toBeVisible();
  });
});

test.describe("Medium confidence path", () => {
  test("confidence=0.70 triggers confirmation prompt", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await speakAndWait(page, "yes", 0.70);

    // The reliability layer should speak "I heard YES. Is that correct?"
    // The mic label will show "Confirming…" while waiting for confirmation
    await expect(
      page.getByText("Confirming…").or(page.getByText(/is that correct/i))
    ).toBeVisible({ timeout: 6_000 });
  });

  test("confirming YES after medium confidence completes submission", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // First: medium confidence result
    await speakAndWait(page, "yes", 0.70);
    // Wait for confirming state
    await page.waitForTimeout(1_000);

    // Second: confirm with high-confidence "yes"
    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST",
        { timeout: 10_000 }
      ),
      speakAndWait(page, "yes", 0.95),
    ]);

    const body = JSON.parse(request.postData() ?? "{}") as { response: string };
    expect(body.response).toBe("yes");
  });
});

test.describe("Low confidence path", () => {
  test("confidence=0.30 triggers retry, does NOT submit", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    let submitted = false;
    page.on("request", (req) => {
      if (req.url().includes(`/sessions/${SESSION_ID}/input`)) submitted = true;
    });

    await speakNoise(page, "yes");
    await page.waitForTimeout(1_500);

    expect(submitted).toBe(false);
  });
});

test.describe("Interim fallback (confidence=0 sentinel)", () => {
  test("interim-only result is accepted immediately", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

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

test.describe("MAX_RETRIES exhaustion", () => {
  test("3 low-confidence results → manual fallback visible", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // 3 low-confidence inputs to exhaust MAX_RETRIES
    for (let i = 0; i < 4; i++) {
      await speakNoise(page, "static");
      await page.waitForTimeout(600);
    }

    // Fallback text or buttons should appear
    const fallback = page.getByText(/voice not recognised/i)
      .or(page.getByText(/use the buttons/i))
      .or(page.getByText(/please use the YES/i));
    await expect(fallback).toBeVisible({ timeout: 6_000 });
  });
});

test.describe("Reliability state reset on FSM transition", () => {
  test("retry count resets after state transition", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // Exhaust retries at first state
    for (let i = 0; i < 4; i++) {
      await speakNoise(page, "static");
      await page.waitForTimeout(600);
    }

    // Transition to next state — reliability should reset
    setState("put_on_mothers_chest");
    await ws.sendEvent("fsm.state_transition");

    await page.waitForTimeout(1_000);

    // Manual fallback should be gone (new state, reset)
    await expect(page.getByText(/voice not recognised/i)).not.toBeVisible({ timeout: 4_000 });
  });
});
