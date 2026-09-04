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
  await expect(page.getByRole("heading", { name: /welcome to your MATB-FAC mission/i })).toBeVisible();

  const sequence = page.getByRole("navigation", { name: /workflow order/i }).locator("ol > li");
  await expect(sequence).toHaveCount(9);
  await expect(sequence.nth(0)).toContainText("Welcome & Participant ID");
  await expect(sequence.nth(1)).toContainText("Karolinska Sleepiness Scale");
  await expect(sequence.nth(2)).toContainText("PVT");
  await expect(sequence.nth(8)).toContainText("Complete visit");

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
  await page.getByRole("button", { name: /save KSS and view PVT instructions/i }).click();
  await expect(page.getByRole("heading", { name: /PVT instructions/i })).toBeVisible();
  await page.getByRole("button", { name: /I am ready/i }).click();
  await page.getByRole("button", { name: /start 10-minute PVT/i }).click();

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
  await expect(page.getByRole("heading", { name: /bienvenido a su misión MATB-FAC/i })).toBeVisible();
  const sequence = page.getByRole("navigation", { name: /orden del flujo/i }).locator("ol > li");
  await expect(sequence).toHaveCount(9);
  await expect(sequence.nth(1)).toContainText("Escala de Somnolencia KSS");
  await expect(sequence.nth(2)).toContainText("PVT · Vigilancia psicomotora");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("participant-start-mobile-es.png"), fullPage: true, animations: "disabled" });
});
