import { test, expect } from "@playwright/test";

test.skip(
  process.env.MATB_E2E_TRAFFIC_FIXTURE !== "1",
  "Requires the explicit traffic test fixture",
);

test("Colombia regions, layers, offline-area handoff and provider outage", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`${page.url()}: ${e.message}`));
  // Deterministic map shell: browser acceptance does not depend on a tile service.
  await page.route("https://tiles.openfreemap.org/styles/liberty", (route) =>
    route.fulfill({
      json: {
        version: 8,
        sources: {},
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": "#d7e3e4" },
          },
        ],
      },
    }),
  );
  await page.route("https://gibs.earthdata.nasa.gov/**", (route) =>
    route.abort(),
  );
  await page.route(
    "https://s3.amazonaws.com/elevation-tiles-prod/**",
    (route) => route.abort(),
  );
  await page.goto("/colombia?metrics=1");
  await page.locator("#app-language").selectOption("en");
  await expect(
    page.getByTestId("colombia-map").locator("canvas"),
  ).toBeVisible();
  const region = page.getByRole("combobox", { name: "Region", exact: true });
  for (const name of [
    "Cauca",
    "Norte de Santander",
    "Antioquia",
    "Sierra Nevada de Santa Marta",
    "Sierra Nevada del Cocuy",
  ])
    await expect(
      region.locator("option").filter({ hasText: name }),
    ).toHaveCount(1);
  await region.selectOption("popayan");
  await expect(page.getByRole("spinbutton", { name: "Latitude" })).toHaveValue(
    "2.4448",
  );
  await expect(page.getByRole("spinbutton", { name: "Longitude" })).toHaveValue(
    "-76.6147",
  );
  for (const label of [
    "Roads",
    "Rivers and water",
    "Settlements",
    "Administrative boundaries",
    "Airports and heliports",
  ]) {
    await page.getByRole("checkbox", { name: label, exact: true }).uncheck();
    await page.getByRole("checkbox", { name: label, exact: true }).check();
  }
  await page.getByRole("checkbox", { name: "Relief", exact: true }).check();
  await page.getByRole("checkbox", { name: "Relief", exact: true }).uncheck();
  await expect(
    page.getByRole("region", { name: "Observed traffic" }),
  ).toContainText("FIXTURE01");
  await expect(page.getByTestId("colombia-map")).toHaveAttribute(
    "data-ready",
    "true",
  );
  await expect
    .poll(() =>
      page.evaluate(
        () => Reflect.get(window, "__matbGeographyMetrics")?.().observed ?? 0,
      ),
    )
    .toBeGreaterThan(0);
  await page.getByRole("button", { name: /FIXTURE01/ }).click();
  await expect(
    page.getByRole("region", { name: "Observed traffic" }),
  ).toContainText("a12345");
  await page.screenshot({
    path: testInfo.outputPath("colombia-controls.png"),
    fullPage: true,
  });
  await page.route("**/geography/traffic?**", (route) =>
    route.fulfill({
      json: {
        provider: "adsb.lol",
        status: "unavailable",
        sampled_at: Date.now() / 1000,
        tracks: [],
      },
    }),
  );
  await page
    .getByRole("checkbox", { name: "Live aircraft traffic", exact: true })
    .uncheck();
  await page
    .getByRole("checkbox", { name: "Live aircraft traffic", exact: true })
    .check();
  await expect(
    page.getByRole("region", { name: "Observed traffic" }),
  ).toContainText("Source unavailable");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: testInfo.outputPath("colombia-mobile.png"),
    fullPage: true,
  });
  const card = page.locator("article").filter({
    has: page.getByRole("heading", { name: "Popayán", exact: true }),
  });
  await card.getByRole("link", { name: "Technical test" }).click();
  await expect(
    page.getByRole("combobox", { name: /local scene/i }),
  ).toHaveValue("popayan-v1");
  expect(errors).toEqual([]);
});
