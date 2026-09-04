import { abortMission, expect, openRunningMission, type OpenMission, test, waitForOperationalView } from "./fixtures";

// The committed reference is rendered on Linux. Windows ClearType changes
// glyph-edge pixels without changing geometry, so retain a narrow
// platform-specific allowance while keeping the Linux CI threshold strict.
const screenshotDiffRatio = process.platform === "win32" ? 0.05 : 0.01;

async function settleForScreenshot(page: Parameters<typeof openRunningMission>[0]): Promise<void> {
  await waitForOperationalView(page);
  const pause = page.getByRole("button", { name: /pause/i });
  if (await pause.isVisible().catch(() => false)) {
    await pause.click();
    await expect(page.locator("header")).toContainText(/paused/i);
  }
}

test("1280px mission layout stays operable without horizontal overflow", async ({ page, request }, testInfo) => {
  let mission: OpenMission | null = null;
  try {
    await page.setViewportSize({ width: 1280, height: 720 });
    mission = await openRunningMission(page, request, testInfo, "e2e_ui_area_search", 3);
    await settleForScreenshot(page);
    const dimensions = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    }));
    expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
    const map = await page.locator('[data-testid="map-root"]').boundingBox();
    expect(map).not.toBeNull();
    expect(map!.width).toBeGreaterThanOrEqual(640);
    expect(map!.height).toBeGreaterThanOrEqual(420);
    const contactsTab = page.getByRole("tab", { name: /contacts/i });
    await contactsTab.focus();
    await expect(contactsTab).toBeFocused();
    await contactsTab.press("Enter");
    await expect(page.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "mission-contacts-tab");
    await expect(page).toHaveScreenshot("mission-1280x720-linux.png", {
      fullPage: true,
      animations: "disabled",
      mask: [page.getByTestId("mission-clock")],
      maxDiffPixelRatio: screenshotDiffRatio,
    });
  } finally {
    if (mission) await abortMission(request, mission);
  }
});

test("1920px mission layout keeps the three-column operations view", async ({ page, request }, testInfo) => {
  let mission: OpenMission | null = null;
  try {
    await page.setViewportSize({ width: 1920, height: 1080 });
    mission = await openRunningMission(page, request, testInfo, "e2e_ui_area_search", 4);
    await settleForScreenshot(page);
    const operations = page.getByRole("main", { name: /mission operations/i });
    await expect(operations).toBeVisible();
    await expect(operations.locator(":scope > *")).toHaveCount(3);
    const mapPanel = page.getByRole("region", { name: /mission map/i });
    const map = await mapPanel.boundingBox();
    expect(map).not.toBeNull();
    expect(map!.width).toBeGreaterThanOrEqual(900);
    await expect(page).toHaveScreenshot("mission-1920x1080-linux.png", {
      fullPage: true,
      animations: "disabled",
      mask: [page.getByTestId("mission-clock")],
      maxDiffPixelRatio: screenshotDiffRatio,
    });
  } finally {
    if (mission) await abortMission(request, mission);
  }
});
