import { expect, test } from "@playwright/test";

test("renders the mission workspace and preserves bilingual day/night interaction", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");

  await expect(page).toHaveTitle(/FAC ISR SMS/i);
  await expect(page.getByRole("heading", { name: "Mission safety strip" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Offline map workspace" })).toBeVisible();
  await expect(page.locator(".console-shell")).toHaveClass(/theme-night/);

  await page.getByRole("button", { name: "Change language" }).click();
  await expect(page.getByRole("heading", { name: "Franja de seguridad de misión" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Telemetría de solo lectura" })).toBeVisible();

  await page.getByRole("button", { name: "Toggle day and night theme" }).click();
  await expect(page.locator(".console-shell")).toHaveClass(/theme-day/);
  expect(consoleErrors).toEqual([]);
});

test("keeps tablet navigation, touch targets, and content within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/");

  await expect(page.getByRole("navigation", { name: "Mission navigation" })).toBeVisible();
  const dimensions = await page.locator(".nav-item, .locale-toggle, .theme-toggle").evaluateAll((elements) => elements.map((element) => {
    const rectangle = element.getBoundingClientRect();
    return { width: rectangle.width, height: rectangle.height };
  }));
  expect(dimensions.every(({ width, height }) => width >= 44 && height >= 44), JSON.stringify(dimensions, null, 2)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);

  await page.getByRole("button", { name: "Research" }).click();
  await expect(page.getByRole("heading", { name: "MATB workload and interface study" })).toBeVisible();
  await expect(page.getByText("Participant code only", { exact: false })).toBeVisible();
});

test("honors reduced-motion preference and retains visible keyboard focus", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");

  const transitionSeconds = await page.locator(".toggle-track span").evaluate((element) => Number.parseFloat(getComputedStyle(element).transitionDuration));
  expect(transitionSeconds).toBeLessThanOrEqual(0.00001);

  await page.keyboard.press("Tab");
  const focused = page.locator(":focus-visible");
  await expect(focused).toBeVisible();
  expect(await focused.evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe("none");
});
