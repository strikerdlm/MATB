import { expect, test, type TestInfo } from "@playwright/test";
import path from "node:path";
import { exerciseMissionTabs } from "./fixtures";

const BACKEND_ORIGIN = "http://127.0.0.1:8000";

function visualPath(testInfo: TestInfo, fileName: string): string {
  const outputDirectory = process.env.MATB_VISUAL_OUTPUT_DIR;
  return outputDirectory ? path.join(outputDirectory, fileName) : testInfo.outputPath(fileName);
}

test("Spanish MATB - FAC frontend launches a segregated HIGH technical test", async ({ page, request }, testInfo) => {
  let sessionId: string | null = null;
  let lease: string | null = null;
  await page.goto("/mission/test");
  await expect(page.getByRole("heading", { name: "Pruebas MATB - FAC" })).toBeVisible();
  await expect(page.getByText("Author: Diego L Malpica H - ASTRA - DIMAE")).toBeVisible();
  await expect(page.locator("#technical-scenario")).not.toHaveValue("");
  await page.locator("#technical-scenario").selectOption("e2e_ui_area_search");

  const highProfile = page.getByRole("radio", { name: /Alta HIGH/ });
  await highProfile.locator("..").click();
  await expect(highProfile).toBeChecked();

  const acknowledgement = page.getByRole("checkbox", { name: /prueba técnica interactiva/i });
  await acknowledgement.locator("..").click();
  await expect(acknowledgement).toBeChecked();
  await expect(page.getByRole("button", { name: /Iniciar prueba interactiva.*Alta.*HIGH/i })).toBeEnabled();
  await page.screenshot({ path: visualPath(testInfo, "matb-fac-tests-desktop.png"), fullPage: true });

  try {
    await page.getByRole("button", { name: /Iniciar prueba interactiva.*Alta.*HIGH/i }).click();
    await expect(page).toHaveURL(/\/mission\?session=sim-/);
    sessionId = new URL(page.url()).searchParams.get("session");
    expect(sessionId).toBeTruthy();
    lease = await page.evaluate((id) => sessionStorage.getItem(`matb.simulation.${id}.lease`), sessionId);
    expect(lease).toBeTruthy();
    await expect(page.locator("header")).toContainText(/modo técnico/i);
    await expect(page.locator("header")).toContainText("No apto para análisis de participantes");
    await expect(page.locator(".simulation-console")).toHaveAttribute("data-console-profile", "supported");
    await expect(page.getByTestId("map-root")).toBeVisible();
    await page.getByRole("button", { name: "Pausar", exact: true }).click();
    await expect(page.locator("header")).toContainText("Pausada");
    await page.setViewportSize({ width: 1366, height: 768 });
    await exerciseMissionTabs(page, "es-CO");
    for (const [width, height] of [[1280, 720], [1366, 768], [1920, 1080]]) {
      await page.setViewportSize({ width, height });
      const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
      expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
      await expect(page.getByRole("tab", { name: "Contactos", exact: true })).toBeVisible();
      await page.screenshot({ path: visualPath(testInfo, `mission-console-v1-${width}x${height}-es.png`), fullPage: true });
    }

    const view = await request.get(`${BACKEND_ORIGIN}/simulation/sessions/${sessionId}`);
    expect(view.status()).toBe(200);
    expect(await view.json()).toMatchObject({
      participant_id: null,
      visit_id: null,
      visit_ordinal: null,
      session_mode: "interactive_technical",
      record_class: "technical_only",
      selected_block_id: "HIGH",
    });
  } finally {
    if (!sessionId || !lease) return;
    await request.post(`${BACKEND_ORIGIN}/simulation/sessions/${sessionId}/finish`, {
      headers: { "X-Simulation-Controller": lease },
      data: { disposition: "abort", reason: "e2e_cleanup" },
    }).catch(() => undefined);
  }
});

test("MATB - FAC technical launcher remains operable on a mobile viewport", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/mission/test");
  await expect(page.locator("#technical-scenario")).not.toHaveValue("");
  const highProfile = page.getByRole("radio", { name: /Alta HIGH/ });
  await highProfile.locator("..").click();
  await expect(highProfile).toBeChecked();
  const acknowledgement = page.getByRole("checkbox", { name: /prueba técnica interactiva/i });
  await acknowledgement.locator("..").click();
  await expect(acknowledgement).toBeChecked();
  await expect(page.getByRole("button", { name: /Iniciar prueba interactiva.*Alta.*HIGH/i })).toBeEnabled();
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
  await page.screenshot({ path: visualPath(testInfo, "matb-fac-tests-mobile.png"), fullPage: true });
});
