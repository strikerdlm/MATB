import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const fixture of [
  { name: "desktop night English", width: 1440, height: 1000, day: false },
  { name: "desktop day English", width: 1440, height: 1000, day: true },
  { name: "tablet night English", width: 820, height: 1180, day: false },
] as const) {
  test(`has no serious or critical axe violations in ${fixture.name}`, async ({ page }) => {
    await page.setViewportSize({ width: fixture.width, height: fixture.height });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Mission safety strip" })).toBeVisible();
    if (fixture.day) {
      await page.getByRole("button", { name: "Toggle day and night theme" }).click();
      await expect(page.locator(".console-shell")).toHaveClass(/theme-day/);
    }

    const results = await new AxeBuilder({ page }).analyze();
    const materialViolations = results.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious");
    expect(materialViolations, JSON.stringify(materialViolations, null, 2)).toEqual([]);
  });
}
