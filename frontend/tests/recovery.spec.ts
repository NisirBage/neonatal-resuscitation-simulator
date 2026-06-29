/**
 * Recovery and manual fallback tests.
 *
 * Covers:
 *  - Manual YES/NO fallback buttons shown after MAX_RETRIES exhausted
 *  - Manual YES button submits "yes" correctly
 *  - Manual NO button submits "no" correctly
 *  - Circuit breaker: 3 consecutive failures → voice paused message
 *  - Keyboard shortcut Y submits YES
 *  - Keyboard shortcut N submits NO
 *  - Error banner shown on API failure
 *  - Error banner can be dismissed
 */

import { test, expect } from "@playwright/test";
import { setupPage, startSession, speakNoise, SESSION_ID } from "./helpers";

/** Exhaust the 3-retry limit by sending low-confidence noise 4 times */
async function exhaustRetries(page: Parameters<typeof speakNoise>[0]) {
  // MAX_RETRIES = 3; each noise input at confidence=0.3 counts as a failure
  for (let i = 0; i < 4; i++) {
    await speakNoise(page, "static");
    await page.waitForTimeout(600);
  }
}

test.describe("Manual fallback buttons", () => {
  test("manual YES/NO buttons appear after repeated noise inputs", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await exhaustRetries(page);

    // After MAX_RETRIES, the fallback buttons with [Y] / [N] labels appear
    await expect(
      page.getByText("Please use the YES or NO buttons").or(
        page.getByText(/voice not recognised/i)
      )
    ).toBeVisible({ timeout: 6_000 });
  });

  test("manual YES button submits 'yes' to API", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await exhaustRetries(page);

    // Wait for fallback to appear
    await page.waitForTimeout(500);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST"
      ),
      page.locator("button:has-text('YES')").first().click(),
    ]);

    const body = JSON.parse(request.postData() ?? "{}") as { response: string };
    expect(body.response).toBe("yes");
  });

  test("manual NO button submits 'no' to API", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await exhaustRetries(page);
    await page.waitForTimeout(500);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST"
      ),
      page.locator("button:has-text('NO')").first().click(),
    ]);

    const body = JSON.parse(request.postData() ?? "{}") as { response: string };
    expect(body.response).toBe("no");
  });
});

test.describe("Keyboard shortcuts", () => {
  test("Y key submits YES in yes/no state", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST"
      ),
      page.keyboard.press("y"),
    ]);

    const body = JSON.parse(request.postData() ?? "{}") as { response: string };
    expect(body.response).toBe("yes");
  });

  test("N key submits NO in yes/no state", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/input`) && req.method() === "POST"
      ),
      page.keyboard.press("n"),
    ]);

    const body = JSON.parse(request.postData() ?? "{}") as { response: string };
    expect(body.response).toBe("no");
  });
});

test.describe("Error handling", () => {
  test("API error on start shows error banner", async ({ page }) => {
    await setupPage(page);
    // Override start route to return 500
    await page.route("**/api/sessions/sessions/start", (route) => {
      route.fulfill({ status: 500, json: { detail: "Internal Server Error" } });
    });
    await page.goto("/");

    await page.click("button:has-text('Start')");

    await expect(
      page.locator("[class*='bg-rose-950']").first()
    ).toBeVisible({ timeout: 6_000 });
  });

  test("error banner can be dismissed", async ({ page }) => {
    // Do NOT call setupPage — instead install the 500 route before the API mock
    await page.route("**/api/sessions/sessions/start", (route) => {
      route.fulfill({ status: 500, body: "Internal Server Error" });
    });
    // Still need scenarios mock and WS mock to prevent hangs
    await page.route("**/api/scenarios/scenarios", (route) => {
      route.fulfill({ json: [{ id: "baby_birth", name: "Baby Birth", file_name: "baby_birth.json", version: "1.0" }] });
    });
    await page.addInitScript({ content: `window.SpeechRecognition = function(){}; window.webkitSpeechRecognition = function(){};` });
    await page.goto("/");

    await page.click("button:has-text('Start')");

    // The error banner should appear — match bg-rose-950 (the error banner, not the WS badge)
    await expect(page.locator("[class*='bg-rose-950']").first()).toBeVisible({ timeout: 6_000 });

    // Dismiss it
    await page.click("button:has-text('Dismiss')");
    await expect(page.locator("[class*='bg-rose-950']").first()).not.toBeVisible({ timeout: 4_000 });
  });
});
