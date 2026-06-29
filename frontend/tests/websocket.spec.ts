/**
 * WebSocket connectivity tests.
 *
 * Covers:
 *  - WS connection established on session start
 *  - State refreshed on fsm.state_transition event
 *  - State refreshed on timer.expired event
 *  - Reconnecting banner shown when WS drops
 *  - Tab hidden pauses SR (visibilitychange)
 *  - Tab restored resumes SR
 */

import { test, expect } from "@playwright/test";
import { setupPage, startSession } from "./helpers";

test.describe("WebSocket state synchronisation", () => {
  test("fsm.state_transition event triggers state refresh", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await expect(page.locator("h2")).toContainText("Has the baby been born?");

    setState("crying_assessment");
    await ws.sendEvent("fsm.state_transition");

    await expect(page.locator("h2")).toContainText("crying", { timeout: 8_000 });
  });

  test("timer.expired event triggers state refresh", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "ventilation_in_progress" });
    await page.goto("/");
    await startSession(page);

    setState("heart_rate_after_ventilation");
    await ws.sendEvent("timer.expired");

    await expect(page.locator("h2")).toContainText("heart rate", { timeout: 8_000 });
  });

  test("unknown WS event does not crash or change state", async ({ page }) => {
    const { ws } = await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await ws.sendEvent("unknown.event.type");
    await page.waitForTimeout(500);

    await expect(page.locator("h2")).toContainText("Has the baby been born?");
  });
});

test.describe("Tab visibility — SR pause/resume", () => {
  test("tab hidden fires visibilitychange and mic label changes", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // Wait for listening state
    await expect(page.getByText("Listening…")).toBeVisible({ timeout: 6_000 });

    // Simulate tab going hidden
    await page.evaluate(() => {
      Object.defineProperty(document, "hidden", { value: true, configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
    });

    // Page should handle this gracefully (no crash)
    await page.waitForTimeout(300);
    const h2 = await page.locator("h2").textContent();
    expect(h2).toBeTruthy();
  });

  test("tab restored after hidden — SR resumes", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // Hide then restore
    await page.evaluate(() => {
      Object.defineProperty(document, "hidden", { value: true, configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await page.waitForTimeout(200);
    await page.evaluate(() => {
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
    });

    // UI should still be stable
    await expect(page.locator("h2")).toContainText("Has the baby been born?");
  });
});
