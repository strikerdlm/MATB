import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
for (const fixture of [{ name: "desktop", width: 1440, height: 1000 }, { name: "tablet", width: 820, height: 1180 }] as const) {
  test(`has no serious or critical axe violations in authenticated ${fixture.name}`, async ({ page }) => {
    await page.setViewportSize({ width: fixture.width, height: fixture.height }); await page.goto("/"); await page.getByLabel("User ID").fill("operator-1"); await page.getByLabel("Password").fill("correct horse battery staple"); await page.getByRole("button", { name: "Sign in", exact: true }).click(); await expect(page.getByRole("heading", { name: "Missions" })).toBeVisible(); const results = await new AxeBuilder({ page }).analyze(); expect(results.violations.filter(({ impact }) => impact === "critical" || impact === "serious"), JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
}
