import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function openAppearance(page: Page): Promise<void> {
  await page.goto("/openmatb/appearance");
  await page.locator("#app-language").selectOption("en");
  await expect(page.getByRole("heading", { name: "MATB - FAC" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Visual profile" })).toHaveValue("matb-fac-modern@1.0.0");
}

test("appearance workbench follows the console Spanish default", async ({ page }) => {
  await page.goto("/openmatb/appearance");
  await expect(page.getByRole("heading", { name: "MATB - FAC" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Perfil visual" })).toHaveValue("matb-fac-modern@1.0.0");
  await expect(page.getByRole("button", { name: /^clonar$/i })).toBeVisible();
  await expect(page.getByText("Configuración del investigador")).toBeVisible();
  await expect(page.getByText(/Solo lectura aquí/)).toBeVisible();
});

test("appearance workbench is accessible and responsive at supported desktop sizes", async ({ page }, testInfo) => {
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    await openAppearance(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    const results = await new AxeBuilder({ page: page as never }).include(".fac-workbench").analyze();
    expect(
      results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? "")),
    ).toEqual([]);

    await page.screenshot({
      path: testInfo.outputPath(`openmatb-appearance-${viewport.width}x${viewport.height}.png`),
      fullPage: false,
      animations: "disabled",
      caret: "hide",
    });
  }
});

test("appearance profiles follow clone, save, validate, acknowledge, publish, and export", async ({ page }) => {
  await openAppearance(page);
  await expect(page.getByText("Published: clone to edit.")).toBeVisible();
  await page.getByRole("button", { name: /^clone$/i }).click();

  const profileId = `e2e-appearance-${Date.now()}`;
  await page.getByLabel("Profile ID").fill(profileId);
  await page.getByLabel("Semantic version").fill("1.0.0");
  await page.getByLabel("Display label").fill("E2E appearance profile");
  await page.getByRole("button", { name: /create draft/i }).click();
  await expect(page.getByText("Draft cloned.")).toBeVisible();

  await page.locator("#palette-app_background-text").fill("#F1F5F9");
  await expect(page.getByText(/unsaved changes/i)).toBeVisible();
  await page.getByRole("button", { name: /save draft/i }).click();
  await expect(page.getByText("Draft saved.")).toBeVisible();

  for (const warning of await page.locator(".fac-warning-check input").all()) await warning.check();
  if (await page.getByText(/unsaved changes/i).isVisible().catch(() => false)) {
    await page.getByRole("button", { name: /save draft/i }).click();
    await expect(page.getByText("Draft saved.")).toBeVisible();
  }
  await page.getByRole("button", { name: /^validate$/i }).click();
  await expect(page.getByText("Validation refreshed.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^publish$/i })).toBeEnabled();
  await page.getByRole("button", { name: /^publish$/i }).click();
  await expect(page.getByText("Profile published and immutable.")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /^export$/i }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`${profileId}-1.0.0.visual-profile.json`);

  await page.getByRole("combobox", { name: "CVD preview", exact: true }).selectOption("deuteranomaly");
  await page.getByLabel("CVD preview severity").fill("70");
  await expect(page.locator(".fac-cvd-stage")).toHaveAttribute("style", /filter/);
});
