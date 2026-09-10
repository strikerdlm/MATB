import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import {
  abortMission,
  expect,
  exerciseMissionTabs,
  openRunningMission,
  type OpenMission,
  test,
  waitForOperationalView,
} from "./fixtures";

async function focusByKeyboard(page: Page, pattern: RegExp): Promise<void> {
  for (let index = 0; index < 100; index += 1) {
    const active = await page.evaluate(() => {
      const element = document.activeElement;
      return { button: element?.matches("button, [role=button]") ?? false, label: element?.getAttribute("aria-label") ?? "", text: element?.textContent ?? "" };
    });
    if (active.button && pattern.test(`${active.label} ${active.text}`)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`keyboard focus did not reach ${pattern}`);
}

test("live mission has no serious axe violations and works by keyboard", async ({ page, request }, testInfo) => {
  let mission: OpenMission | null = null;
  try {
    mission = await openRunningMission(page, request, testInfo, "e2e_ui_area_search", 0);
    await waitForOperationalView(page);
    await expect(page.locator('[data-testid="map-root"]')).toBeVisible({ timeout: 20_000 });
    const nextBlock = page.getByRole("button", { name: /start block/i });
    if (await nextBlock.isVisible().catch(() => false)) {
      await nextBlock.click();
      // Enter the second block immediately after its authoritative snapshot;
      // the fixture's one-second ISA boundary must not be allowed to turn a
      // keyboard-navigation assertion into a probe-scoring test.
      await expect(page.locator('[data-testid="map-root"]')).toBeVisible();
    }

    const results = await new AxeBuilder({ page: page as never }).include(".simulation-console").analyze();
    expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""))).toEqual([]);

    await exerciseMissionTabs(page);

    await page.keyboard.press("Tab");
    await focusByKeyboard(page, /UAS-01/i);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Hold", exact: true })).toBeEnabled();
    await focusByKeyboard(page, /hold/i);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("status").filter({ hasText: /command accepted/i })).toBeVisible();
  } finally {
    if (mission) await abortMission(request, mission);
  }
});

test("reduced motion removes operational sweep and control transitions", async ({ page, request }, testInfo) => {
  let mission: OpenMission | null = null;
  try {
    await page.emulateMedia({ reducedMotion: "reduce" });
    mission = await openRunningMission(page, request, testInfo, "e2e_ui_area_search", 1);
    await waitForOperationalView(page);
    await expect(page.locator(".signal-sweep")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /finish session/i })).toHaveCSS("transition-duration", "0s");
  } finally {
    if (mission) await abortMission(request, mission);
  }
});
