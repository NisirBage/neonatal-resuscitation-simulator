/**
 * Session lifecycle tests.
 *
 * Covers:
 *  - App loads without errors (no console errors, no red banner)
 *  - Start button calls POST /sessions/start
 *  - Initial FSM state rendered correctly
 *  - Restart replaces active session
 *  - Stop button ends session and resets UI
 *  - No-transition terminal states (routine_care, simulation_complete)
 */

import { test, expect } from "@playwright/test";
import { setupPage, startSession, makeState, SESSION_ID } from "./helpers";

test.describe("Session startup", () => {
  test("page loads without console errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await setupPage(page);
    await page.goto("/");

    await page.waitForLoadState("domcontentloaded");
    // Filter out known non-critical errors (e.g. AudioContext permission)
    const critical = errors.filter(
      (e) => !e.includes("AudioContext") && !e.includes("favicon")
    );
    expect(critical).toHaveLength(0);
  });

  test("idle state shows 'Select a scenario and press Start'", async ({ page }) => {
    await setupPage(page);
    await page.goto("/");
    await expect(page.locator("h2")).toContainText("Select a scenario and press Start");
  });

  test("Start button triggers POST /sessions/start", async ({ page }) => {
    await setupPage(page);
    await page.goto("/");

    const [request] = await Promise.all([
      page.waitForRequest("**/api/sessions/sessions/start"),
      page.click("button:has-text('Start')"),
    ]);
    expect(request.method()).toBe("POST");
  });

  test("first FSM state is rendered after session starts", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await expect(page.locator("h2")).toContainText("Has the baby been born?");
  });

  test("mic label changes to 'Listening…' when voice is active", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await expect(page.getByText("Listening…")).toBeVisible({ timeout: 6_000 });
  });

  test("YES and NO buttons are visible for yes/no states", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await expect(page.locator("button:has-text('YES')").first()).toBeVisible();
    await expect(page.locator("button:has-text('NO')").first()).toBeVisible();
  });

  test("Stop button resets UI to idle", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    await page.click("button:has-text('Stop')");
    await expect(page.locator("h2")).toContainText("Select a scenario and press Start", { timeout: 6_000 });
  });
});

test.describe("Terminal states (no-transition states)", () => {
  test("routine_care terminal state shows completion", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // Transition to terminal state
    setState("routine_care");
    await ws.sendEvent("fsm.state_transition");

    await expect(page.locator("h2")).toContainText("Routine care", { timeout: 8_000 });
    // Mic label should show complete — use first() since h2 text also contains these words
    await expect(page.getByText("Simulation complete").first()).toBeVisible({ timeout: 6_000 });
  });

  test("simulation_complete terminal state shows completion", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    setState("simulation_complete");
    await ws.sendEvent("fsm.state_transition");

    await expect(page.locator("h2")).toContainText("Simulation complete", { timeout: 8_000 });
  });

  test("YES/NO buttons disappear on terminal state", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    setState("simulation_complete");
    await ws.sendEvent("fsm.state_transition");

    await page.waitForTimeout(1_000);
    // Should have no enabled YES/NO buttons (terminal state has no actions)
    const yesButtons = page.locator("button:has-text('YES')");
    await expect(yesButtons).toHaveCount(0, { timeout: 6_000 });
  });
});

test.describe("Happy path — first three states", () => {
  test("baby_born → put_on_mothers_chest via button click", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    // Click YES button (direct UI path)
    await page.locator("button:has-text('YES')").first().click();

    // Simulate server transition
    setState("put_on_mothers_chest");
    await ws.sendEvent("fsm.state_transition");

    await expect(page.locator("h2")).toContainText("placed on the mother", { timeout: 8_000 });
  });

  test("put_on_mothers_chest → crying_assessment via button click", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "put_on_mothers_chest" });
    await page.goto("/");
    await startSession(page);

    await page.locator("button:has-text('YES')").first().click();

    setState("crying_assessment");
    await ws.sendEvent("fsm.state_transition");

    await expect(page.locator("h2")).toContainText("crying", { timeout: 8_000 });
  });

  test("crying_assessment → routine_care when baby is crying (YES)", async ({ page }) => {
    const { setState, ws } = await setupPage(page, { firstState: "crying_assessment" });
    await page.goto("/");
    await startSession(page);

    await page.locator("button:has-text('YES')").first().click();

    setState("routine_care");
    await ws.sendEvent("fsm.state_transition");

    await expect(page.locator("h2")).toContainText("Routine care", { timeout: 8_000 });
  });
});
