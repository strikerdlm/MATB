import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "./fixtures";

const BACKEND_ORIGIN = "http://127.0.0.1:8000";

test("participant follows KSS before the bilingual fast-check PVT", async ({ page, request }, testInfo) => {
  const number = ((process.pid % 8_000) + 1) * 60 + 48;
  const participant = `P${String(number).padStart(2, "0")}`;
  const created = await request.post(`${BACKEND_ORIGIN}/participants`, {
    data: { id: participant, enrollment_date: "2026-09-04" },
  });
  expect(created.status()).toBe(201);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/start");
  await page.locator("#app-language").selectOption("en");
  await expect(page.getByRole("heading", { name: /choose your experiment/i })).toBeVisible();
  const sequence = page.getByRole("list", { name: /experiment steps/i }).locator("li");
  await expect(sequence).toHaveCount(5);
  const accessibility = await new AxeBuilder({ page: page as never }).analyze();
  expect(accessibility.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("participant-start-desktop.png"), fullPage: true, animations: "disabled" });

  await page.goto("/pvt?fast=1#kss");
  await page.locator("#pvt-participant").selectOption(participant);
  await expect(page.locator("#pvt-visit")).toBeEnabled();
  await expect(page.locator("#pvt-visit")).not.toHaveValue("");
  await page.getByRole("button", { name: /continue to KSS/i }).click();
  await expect(page.getByRole("heading", { name: /Karolinska Sleepiness Scale/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /PVT instructions/i })).toHaveCount(0);
  await page.getByRole("radio", { name: /neither alert nor sleepy/i }).check();
  await page.getByRole("button", { name: /confirm KSS and view PVT instructions/i }).click();
  await expect(page.getByRole("heading", { name: /PVT instructions/i })).toBeVisible();
  await page.getByRole("button", { name: /I am ready/i }).click();
  await page.getByRole("button", { name: /start PVT practice/i }).click();

  for (let attempt = 0; attempt < 14; attempt += 1) {
    await page.keyboard.press("Space");
    await page.waitForTimeout(1_000);
  }
  await expect(page.getByRole("heading", { name: /KSS and PVT complete/i })).toBeVisible({ timeout: 15_000 });
});

test("Spanish participant sequence remains usable on a mobile viewport", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/start");
  await page.locator("#app-language").selectOption("es-419");
  await expect(page.getByRole("heading", { name: /elija su experimento/i })).toBeVisible();
  await page.getByText("Menú de experimentos", { exact: true }).click();
  const sequence = page.getByRole("list", { name: /pasos del experimento/i }).locator("li");
  await expect(sequence).toHaveCount(5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("participant-start-mobile-es.png"), fullPage: true, animations: "disabled" });
});
