import { abortMission, expect, openRunningMission, type OpenMission, test, waitForOperationalView } from "./fixtures";

const BACKEND_ORIGIN = "http://127.0.0.1:8000";

test("observer mode is read-only and controller disconnect pauses the session", async ({ page, browser, request }, testInfo) => {
  let mission: OpenMission | null = null;
  const observerContext = await browser.newContext();
  const observer = await observerContext.newPage();
  let replacement: typeof page | null = null;
  try {
    mission = await openRunningMission(page, request, testInfo, "e2e_ui_area_search", 2);
    await waitForOperationalView(page);
    await observer.goto(`/mission?session=${encodeURIComponent(mission.sessionId)}`);
    await expect(observer.locator("header")).toContainText(/observer/i);
    await expect(observer.getByRole("button", { name: /finish session/i })).toBeDisabled();
    await expect(observer.locator('[data-testid="map-root"]')).toBeVisible({ timeout: 20_000 });

    await test.step("Disconnect the original controller", () => page.close(), { timeout: 15_000 });
    await expect.poll(async () => {
      const response = await request.get(`${BACKEND_ORIGIN}/simulation/sessions/${encodeURIComponent(mission!.sessionId)}`);
      const body = await response.json() as { lifecycle?: string };
      return body.lifecycle ?? "unknown";
    }, { timeout: 20_000 }).toBe("PAUSED");
    await expect(observer.locator("header")).toContainText(/paused/i);

    // A lease is intentionally scoped to sessionStorage, so a fresh page
    // needs the saved controller credential explicitly (the same handoff a
    // recovery shell would perform).  It must never be copied into the URL.
    replacement = await test.step("Open the replacement controller", () => page.context().newPage(), { timeout: 15_000 });
    await replacement.addInitScript(({ sessionId, lease }) => {
      sessionStorage.setItem(`matb.simulation.${sessionId}.lease`, lease);
    }, { sessionId: mission.sessionId, lease: mission.lease });
    await test.step("Load the replacement mission", () => replacement!.goto(
      `/mission?session=${encodeURIComponent(mission!.sessionId)}`,
      { waitUntil: "domcontentloaded", timeout: 15_000 },
    ));
    await expect(replacement.locator("header")).toContainText(/live|paused/i);
    const resume = replacement.getByRole("button", { name: /resume/i });
    if (await resume.isVisible().catch(() => false)) {
      await expect(resume).toBeEnabled();
      await resume.click();
      await expect(replacement.locator("header")).toContainText(/running/i);
    } else {
      // A short fixture may reach a protocol gate during teardown.  The
      // reconnect still has to expose the gate and remain controller-owned.
      await expect(replacement.getByRole("dialog")).toBeVisible();
    }
  } finally {
    // Release the backend session before browser teardown, even after a page
    // operation times out, so following tests can create their own mission.
    if (mission) await abortMission(request, mission);
    await replacement?.close().catch(() => undefined);
    await observerContext.close().catch(() => undefined);
  }
});
