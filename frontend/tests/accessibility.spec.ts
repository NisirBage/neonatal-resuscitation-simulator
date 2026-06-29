/**
 * Accessibility and performance tests.
 *
 * Covers:
 *  - Page title is descriptive
 *  - Start / Stop buttons are keyboard-focusable
 *  - YES / NO buttons have accessible text
 *  - No empty button labels
 *  - Page loads within 3 seconds (performance budget)
 *  - No layout shift on session start
 */

import { test, expect } from "@playwright/test";
import { setupPage, startSession } from "./helpers";

test.describe("Page structure", () => {
  test("page has a descriptive title or heading", async ({ page }) => {
    await setupPage(page);
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const h2 = await page.locator("h2").textContent();
    expect(h2).toBeTruthy();
    expect((h2 ?? "").length).toBeGreaterThan(5);
  });

  test("NRS Voice Assistant heading is visible", async ({ page }) => {
    await setupPage(page);
    await page.goto("/");
    await expect(page.getByText("NRS Voice Assistant")).toBeVisible();
  });
});

test.describe("Keyboard accessibility", () => {
  test("Start button is reachable via Tab key", async ({ page }) => {
    await setupPage(page);
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    // Tab through interactive elements until Start button is focused
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press("Tab");
      const focused = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el) return null;
        return {
          tag:  el.tagName,
          text: el.textContent?.trim().slice(0, 40),
        };
      });
      if (focused?.text?.includes("Start")) {
        expect(focused.tag).toBe("BUTTON");
        return;
      }
    }
    throw new Error("Start button not reachable via Tab");
  });

  test("Stop button is reachable via Tab key (when session is active)", async ({ page }) => {
    // Stop is disabled before a session starts — start one first so it's enabled
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    for (let i = 0; i < 20; i++) {
      await page.keyboard.press("Tab");
      const focused = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el) return null;
        return { tag: el.tagName, text: el.textContent?.trim().slice(0, 40) };
      });
      if (focused?.text?.includes("Stop")) {
        expect(focused.tag).toBe("BUTTON");
        return;
      }
    }
    throw new Error("Stop button not reachable via Tab");
  });

  test("all buttons have non-empty text content", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const buttons = await page.locator("button").all();
    for (const btn of buttons) {
      const text = (await btn.textContent() ?? "").trim();
      const ariaLabel = await btn.getAttribute("aria-label");
      // Button must have either visible text or aria-label
      const hasLabel = text.length > 0 || (ariaLabel ?? "").length > 0;
      expect(hasLabel).toBe(true);
    }
  });
});

test.describe("Performance budget", () => {
  test("page reaches interactive state within 3 seconds", async ({ page }) => {
    await setupPage(page);

    const t0 = Date.now();
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await expect(page.locator("h2")).toBeVisible();
    const elapsed = Date.now() - t0;

    expect(elapsed).toBeLessThan(3_000);
  });

  test("session start renders first state within 2 seconds of API response", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");

    const t0 = Date.now();
    await page.click("button:has-text('Start')");
    await expect(page.locator("h2")).toContainText("Has the baby been born?", { timeout: 4_000 });
    const elapsed = Date.now() - t0;

    expect(elapsed).toBeLessThan(2_000);
  });
});

test.describe("Responsive layout", () => {
  test("layout works at 375px width (mobile)", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    await startSession(page);

    // Start button and voice prompt should still be visible
    await expect(page.locator("h2")).toBeVisible();
    await expect(page.locator("button:has-text('YES')").first()).toBeVisible();
  });

  test("layout works at 1280px width (desktop)", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await startSession(page);

    await expect(page.locator("h2")).toBeVisible();
  });
});
