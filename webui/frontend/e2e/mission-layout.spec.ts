import { expect, test } from "@playwright/test";

const api = "http://127.0.0.1:8000";

for (const [width, height] of [[390, 844], [1024, 768], [1279, 768], [1280, 720], [1366, 768], [1920, 1080]]) {
  test(`LOW and HIGH keep the map visible at ${width}×${height}`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height });
    const positions: number[] = [];
    const heights: number[] = [];
    for (const block of ["LOW", "HIGH"]) {
      const response = await request.post(`${api}/simulation/technical-sessions`, {
        data: { execution_purpose: "practice", scenario_id: "reference_area_search", block_id: block, locale: "en" },
      });
      expect(response.status(), await response.text()).toBe(201);
      const session = await response.json();
      const headers = { "X-Simulation-Controller": session.controller_lease };
      await page.addInitScript(({ id, lease }) => sessionStorage.setItem(`matb.simulation.${id}.lease`, lease), { id: session.id, lease: session.controller_lease });
      try {
        expect((await request.post(`${api}/simulation/sessions/${session.id}/start`, { headers, data: { block_id: block } })).status()).toBe(200);
        expect((await request.post(`${api}/simulation/sessions/${session.id}/pause`, { headers, data: { reason: "layout_check" } })).status()).toBe(200);
        await page.goto(`/mission?session=${session.id}`);
        const map = page.getByTestId("map-root");
        await expect(map).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: testInfo.outputPath(`${block}-${width}.png`), fullPage: true });
        const bounds = await map.boundingBox();
        expect(bounds).not.toBeNull();
        positions.push(bounds!.y);
        heights.push(bounds!.height);
        await testInfo.attach(`${block}-geometry`, { body: JSON.stringify({ block, width, height, map: bounds }), contentType: "application/json" });
        const sizes = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: innerWidth }));
        expect.soft(sizes.scroll, `${block} horizontal overflow`).toBeLessThanOrEqual(sizes.viewport);
        expect.soft(bounds!.y, `${block} map begins in the initial viewport`).toBeLessThan(450);
        expect.soft(bounds!.height, `${block} map height stays bounded`).toBeLessThanOrEqual(1000);
        expect.soft(bounds!.y + bounds!.height / 2, `${block} map center is on screen`).toBeLessThan(height);
        const fleet = page.getByRole("list").filter({ has: page.getByRole("button", { name: /UAS-0/ }) });
        await expect(fleet.getByRole("button")).toHaveCount(block === "HIGH" ? 8 : 2);
        // Keyboard focus must scroll to every aircraft within the bounded fleet.
        await fleet.getByRole("button").last().focus();
        await expect(fleet.getByRole("button").last()).toBeInViewport();
      } finally {
        await request.post(`${api}/simulation/sessions/${session.id}/finish`, { headers, data: { disposition: "abort" } });
      }
    }
    expect.soft(Math.abs(heights[1] - heights[0]), "workload must not stretch the map").toBeLessThanOrEqual(2);
    expect(Math.abs(positions[1] - positions[0]), "workload must not push the map down").toBeLessThanOrEqual(2);
  });
}

test("expanded swarm controls and 3D viewport remain accessible", async ({ page, request }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const scene = (await (await request.get(`${api}/simulation/scenes`)).json())[0];
  const response = await request.post(`${api}/simulation/technical-sessions`, { data: {
    execution_purpose: "practice", scenario_id: "swarm_visual_test", block_id: "HIGH", locale: "en",
    presentation: { version: 3, blocks: { HIGH: "3d" }, scene_id: scene.id, scene_sha256: scene.sha256, camera: "swarm", controls: { smooth_camera: true, contact_cycling: true, adjustable_layers: true } },
  } });
  expect(response.status(), await response.text()).toBe(201);
  const session = await response.json();
  await page.addInitScript(({ id, lease }) => sessionStorage.setItem(`matb.simulation.${id}.lease`, lease), { id: session.id, lease: session.controller_lease });
  try {
    const ready = page.waitForResponse(r => r.url().endsWith("/presentation") && r.request().postDataJSON()?.kind === "ready" && r.status() === 204);
    await page.goto(`/mission?session=${session.id}`);
    await ready;
    await page.getByRole("button", { name: /start block/i }).click();
    const control = page.getByRole("region", { name: "Swarm control" });
    await expect(control).toContainText("8 members");
    await page.locator("summary").filter({ hasText: /^Visit sequence$/ }).click();
    await control.locator("summary").click();
    await control.getByRole("button", { name: "Detach", exact: true }).last().focus();
    await expect(control.getByRole("button", { name: "Detach", exact: true }).last()).toBeInViewport();
    const clipping = await page.getByTestId("mission-three-view").evaluate(element => {
      const panel = element.closest(".mission-panel")!;
      return { content: panel.scrollHeight, visible: panel.clientHeight };
    });
    expect(clipping.content, "3D panel must not clip its viewport or footer").toBeLessThanOrEqual(clipping.visible + 1);
    await page.screenshot({ path: testInfo.outputPath("swarm-expanded-1280.png"), fullPage: true });
  } finally {
    await request.post(`${api}/simulation/sessions/${session.id}/finish`, { headers: { "X-Simulation-Controller": session.controller_lease }, data: { disposition: "abort" } });
  }
});
