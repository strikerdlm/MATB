import { test, expect } from "@playwright/test";
import { writeFileSync } from "node:fs";

test("online Colombia basemap, imagery and relief", async ({
  page,
}, testInfo) => {
  test.skip(
    process.env.MATB_E2E_ONLINE_CHECK !== "1",
    "Opt-in public tile-service check",
  );
  test.setTimeout(60000);
  const network: unknown[] = [];
  const record = (value: unknown) => {
    network.push(value);
    writeFileSync(
      testInfo.outputPath("network.json"),
      JSON.stringify(network.slice(-100), null, 2),
    );
  };
  page.on("requestfailed", (r) => {
    if (r.url().startsWith("https:"))
      record({ url: r.url(), failure: r.failure()?.errorText });
  });
  page.on("response", (r) => {
    if (r.url().startsWith("https:"))
      record({ url: r.url(), status: r.status() });
  });
  page.on("console", (m) => {
    if (m.type() === "error") record({ console: m.text() });
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1920, height: 1080 });
  const tiles = page.waitForResponse(
    (r) =>
      r.url().includes("tiles.openfreemap.org/planet/") &&
      r.url().endsWith(".pbf") &&
      r.status() === 200,
  );
  await page.goto("/colombia?metrics=1");
  await page.locator("#app-language").selectOption("en");
  await tiles;
  await expect(page.getByTestId("colombia-map")).toHaveAttribute(
    "data-ready",
    "true",
  );
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          Reflect.get(window, "__matbGeographyMetrics")?.().queryOutline ?? 0,
      ),
    )
    .toBeGreaterThan(0);
  if (process.env.MATB_E2E_TRAFFIC_FIXTURE === "1") {
    await expect
      .poll(() =>
        page.evaluate(
          () => Reflect.get(window, "__matbGeographyMetrics")?.().observed ?? 0,
        ),
      )
      .toBeGreaterThan(0);
  }
  await expect(
    page.getByTestId("colombia-map").locator("canvas"),
  ).toBeVisible();
  await page.waitForTimeout(3000);
  await page.screenshot({
    path: testInfo.outputPath("colombia-national.png"),
    fullPage: true,
  });
  const imagery = page.waitForResponse(
    (r) => r.url().includes("gibs.earthdata.nasa.gov") && r.status() === 200,
  );
  await page
    .getByRole("checkbox", { name: "Satellite imagery · 250 m", exact: true })
    .check();
  await imagery;
  await page.waitForTimeout(2000);
  await page.screenshot({
    path: testInfo.outputPath("colombia-imagery.png"),
    fullPage: true,
  });
  await page
    .getByRole("checkbox", { name: "Satellite imagery · 250 m", exact: true })
    .uncheck();
  const terrain = page.waitForResponse(
    (r) =>
      r.url().includes("elevation-tiles-prod/terrarium") && r.status() === 200,
  );
  await page.getByRole("checkbox", { name: "Relief", exact: true }).check();
  await terrain;
  await page
    .getByRole("combobox", { name: "Region", exact: true })
    .selectOption("rionegro");
  await page.waitForTimeout(3000);
  await page.screenshot({
    path: testInfo.outputPath("antioquia-online.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

for (const id of [
  "villavicencio-v1",
  "popayan-v1",
  "cucuta-v1",
  "rionegro-v1",
  "minca-v1",
])
  test(`offline scene renders ${id}`, async ({ page, request }, testInfo) => {
    test.skip(
      process.env.MATB_E2E_REGION_CHECK !== "1",
      "Opt-in regional asset verification",
    );
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.route("https://**/*", (route) => route.abort());
    const api = "http://127.0.0.1:8000";
    const scene = (
      await (await request.get(`${api}/simulation/scenes`)).json()
    ).find((s: { id: string }) => s.id === id);
    expect(scene).toBeTruthy();
    const response = await request.post(
      `${api}/simulation/technical-sessions`,
      {
        data: {
          scenario_id: "presentation_area_search",
          block_id: "LOW",
          locale: "en",
          presentation: {
            version: 1,
            blocks: { LOW: "3d" },
            scene_id: id,
            scene_sha256: scene.sha256,
            camera: "overview",
          },
        },
      },
    );
    expect(response.status()).toBe(201);
    const prepared = await response.json();
    const headers = { "X-Simulation-Controller": prepared.controller_lease };
    try {
      await page.addInitScript(
        ({ id, lease }) =>
          sessionStorage.setItem(`matb.simulation.${id}.lease`, lease),
        { id: prepared.id, lease: prepared.controller_lease },
      );
      const ready = page.waitForResponse(
        (r) =>
          r.url().endsWith("/presentation") &&
          r.request().postDataJSON()?.kind === "ready" &&
          r.status() === 204,
      );
      await page.goto(`/mission?session=${prepared.id}&metrics=1`);
      await ready;
      await page.getByRole("button", { name: /start block/i }).click();
      await expect(
        page.getByTestId("mission-three-view").locator("canvas"),
      ).toBeVisible();
      await page.waitForTimeout(2000);
      await page.screenshot({
        path: testInfo.outputPath(`${id}.png`),
        fullPage: true,
      });
      const metrics = await page.evaluate(() =>
        Reflect.get(window, "__matbPresentationMetrics")?.(),
      );
      writeFileSync(
        testInfo.outputPath("renderer-metrics.json"),
        JSON.stringify(
          { scene: id, viewport: page.viewportSize(), ...metrics },
          null,
          2,
        ),
      );
      expect(errors).toEqual([]);
    } finally {
      const finished = await request.post(
        `${api}/simulation/sessions/${prepared.id}/finish`,
        {
          headers,
          data: { disposition: "abort" },
          maxRetries: 2,
        },
      );
      expect(finished.status(), await finished.text()).toBe(200);
    }
  });
