/**
 * Export / download tests.
 *
 * Covers:
 *  - Export CSV triggers GET /export/csv
 *  - Clinical Timeline triggers GET /export/clinical-csv
 *  - Export Excel Timeline triggers GET /export/clinical-xlsx
 *  - PDF Report triggers GET /report/pdf
 *  - Export buttons disabled before session starts
 *
 * Export buttons are always visible in the footer; they are disabled when
 * no session is active. Tests start a session first then click them.
 */

import { test, expect } from "@playwright/test";
import { setupPage, startSession, SESSION_ID } from "./helpers";

test.describe("Export downloads", () => {
  test("Export CSV button triggers GET /export/csv", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/export/csv`) &&
        !req.url().includes("clinical") &&
        req.method() === "GET"
      ),
      page.click("button:has-text('Export CSV')"),
    ]);

    expect(request.method()).toBe("GET");
    expect(request.url()).toContain("/export/csv");
  });

  test("Clinical Timeline button triggers GET /export/clinical-csv", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/export/clinical-csv`) &&
        req.method() === "GET"
      ),
      page.click("button:has-text('Clinical Timeline')"),
    ]);

    expect(request.method()).toBe("GET");
    expect(request.url()).toContain("clinical-csv");
  });

  test("Export Excel Timeline button triggers GET /export/clinical-xlsx", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/export/clinical-xlsx`) &&
        req.method() === "GET"
      ),
      page.click("button:has-text('Export Excel Timeline')"),
    ]);

    expect(request.method()).toBe("GET");
    expect(request.url()).toContain("clinical-xlsx");
  });

  test("PDF Report button triggers GET /report/pdf", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const [request] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes(`/sessions/${SESSION_ID}/report/pdf`) &&
        req.method() === "GET"
      ),
      page.click("button:has-text('PDF Report')"),
    ]);

    expect(request.method()).toBe("GET");
    expect(request.url()).toContain("report/pdf");
  });
});

test.describe("Export availability", () => {
  test("export buttons are disabled before session starts", async ({ page }) => {
    await setupPage(page);
    await page.goto("/");

    // Export CSV button exists but is disabled (no sessionId yet)
    const exportCsvBtn = page.locator("button:has-text('Export CSV')");
    await expect(exportCsvBtn).toBeVisible();
    await expect(exportCsvBtn).toBeDisabled();
  });

  test("export buttons become enabled after session starts", async ({ page }) => {
    await setupPage(page, { firstState: "baby_born" });
    await page.goto("/");
    await startSession(page);

    const exportCsvBtn = page.locator("button:has-text('Export CSV')");
    await expect(exportCsvBtn).toBeEnabled();
  });
});
