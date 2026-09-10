import { test, expect } from "@playwright/test";
const api = "http://127.0.0.1:8000";

test("v2 records camera, layer and contact actions and replays offline", async ({ page, request }) => {
  const errors: string[] = [];
  await page.setViewportSize({ width: 1920, height: 1080 });
  page.on("pageerror", e => errors.push(e.message));
  const exposures: Record<string, unknown>[] = [];
  const failures: string[] = [];
  page.on("response", async response => {
    if (response.url().endsWith("/presentation")) {
      if (response.status() === 204) exposures.push(response.request().postDataJSON());
      else failures.push(`${response.status()}: ${await response.text()}`);
    }
  });
  await page.route("https://**/*", route => route.abort());
  const scene = (await (await request.get(`${api}/simulation/scenes`)).json())[0];
  const response = await request.post(`${api}/simulation/technical-sessions`, { data: {
      execution_purpose: "practice",
    scenario_id: "presentation_area_search", block_id: "LOW", locale: "en",
    presentation: { version: 2, scene_id: scene.id, scene_sha256: scene.sha256, blocks: { LOW: "3d" }, camera: "overview",
      controls: { smooth_camera: true, contact_cycling: true, adjustable_layers: true },
      ...(process.env.MATB_E2E_TRAFFIC_FIXTURE === "1" ? { traffic: { mode: "live", provider: "adsb.lol" } } : {}) },
  } });
  expect(response.status()).toBe(201);
  const prepared = await response.json();
  const headers = { "X-Simulation-Controller": prepared.controller_lease };
  try {
    await page.addInitScript(({ id, lease }) => sessionStorage.setItem(`matb.simulation.${id}.lease`, lease), { id: prepared.id, lease: prepared.controller_lease });
    await page.goto(`/mission?session=${prepared.id}`);
    await expect.poll(() => exposures.some(e => e.kind === "ready")).toBe(true);
    await page.getByRole("button", { name: /start block/i }).click();
    await expect(page.getByRole("button", { name: "Next", exact: true })).toBeEnabled();
    await expect.poll(() => exposures.filter(e => e.kind === "ready").length).toBeGreaterThanOrEqual(2);
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByRole("combobox", { name: "Camera", exact: true }).selectOption("follow");
    await expect(page.getByRole("combobox", { name: "Camera", exact: true })).toHaveValue("follow");
    await expect.poll(() => exposures.some(e => e.kind === "transition_end")).toBe(true);
    if (process.env.MATB_E2E_TRAFFIC_FIXTURE === "1") {
      await expect(page.getByRole("region", { name: "Observed traffic" })).toContainText("FIXTURE01");
      await page.getByRole("combobox", { name: "Category", exact: true }).selectOption("observed");
      await page.getByRole("button", { name: "Next", exact: true }).click();
      await expect(page.getByRole("region", { name: "Contact navigation" })).toContainText("a12345");
      await expect(page.getByRole("combobox", { name: "Camera", exact: true })).toHaveValue("follow");
      await expect(page.locator('select option[value="drone"]')).toHaveJSProperty("disabled", true);
      await expect.poll(() => exposures.some(e => e.kind === "navigate" && (e.resolved as { observed_id?: string })?.observed_id === "a12345")).toBe(true);
    }
    await page.getByRole("checkbox", { name: "routes", exact: true }).uncheck();
    await expect.poll(() => exposures.some(e => e.kind === "layers")).toBe(true);
    await page.getByRole("checkbox", { name: "roads", exact: true }).uncheck();
    await expect.poll(() => exposures.some(e => e.kind === "geography")).toBe(true);
    await page.getByRole("combobox", { name: "Presentation", exact: true }).selectOption("2d");
    await expect(page.getByTestId("map-root")).toBeVisible();
    await page.getByRole("button", { name: /zoom in/i }).click();
    await expect.poll(() => exposures.some(e => e.kind === "map_view")).toBe(true);
    expect(errors).toEqual([]);
    expect(failures).toEqual([]);
    await page.getByRole("button", { name: "Finish session", exact: true }).click();
    await page.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect.poll(async () => (await (await request.get(`${api}/simulation/sessions/${prepared.id}`)).json()).lifecycle).toBe("FINISHED");
    const debrief = await (await request.get(`${api}/simulation/sessions/${prepared.id}/debrief`)).json();
    expect(debrief.presentation.version).toBe(2);
    const recorded = debrief.presentation_events.filter((e: { version: number }) => e.version === 2);
    expect(recorded.length).toBeGreaterThan(5);
    expect(recorded.some((e: { resolved: { operational_layers: { routes: boolean } } }) => !e.resolved.operational_layers.routes)).toBe(true);
    await page.goto(`/mission/debrief?session=${prepared.id}`);
    const slider = page.getByRole("slider", { name: /replay time/i });
    await expect(slider).toBeVisible();
    await slider.press("End");
    await expect(page.getByTestId("map-root")).toBeVisible();
    await expect(page.getByRole("button", { name: /zoom in/i })).toBeDisabled();
    await slider.press("Home");
    expect(errors).toEqual([]);
  } finally {
    await request.post(`${api}/simulation/sessions/${prepared.id}/finish`, { headers, data: { disposition: "abort" } }).catch(() => {});
  }
});
