import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "./core-fixtures";

test("experiment designer compiles a real deterministic scenario accessibly", async ({ page }, testInfo) => {
  await page.goto("/experiments");

  await expect(page.getByRole("heading", { name: "Experiment Designer" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Experiment timeline" })).toBeVisible();
  await expect(page.getByText("engineering presets until human calibration", { exact: false })).toBeVisible();

  const results = await new AxeBuilder({ page: page as never }).analyze();
  expect(
    results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? "")),
  ).toEqual([]);

  await page.getByRole("button", { name: /compile & validate/i }).click();
  await expect(page.getByText(/^[a-f0-9]{64}$/)).toHaveCount(2);
  await expect(page.getByText("Compiled OpenMATB scenario")).toBeVisible();

  await page.screenshot({
    path: testInfo.outputPath("experiment-designer-desktop.png"),
    fullPage: true,
    caret: "initial",
  });
});

test("experiment designer keeps controls and content inside a mobile viewport", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/experiments");

  await expect(page.getByRole("heading", { name: "Experiment Designer" })).toBeVisible();
  await expect(page.getByRole("button", { name: /add event/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /compile & validate/i })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.screenshot({
    path: testInfo.outputPath("experiment-designer-mobile.png"),
    fullPage: true,
    caret: "initial",
  });
});
