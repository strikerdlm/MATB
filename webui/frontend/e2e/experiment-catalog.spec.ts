import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const locale of ["es-419", "en"] as const) {
  for (const width of [1440, 390]) {
    test(`catalog explains six families in ${locale} at ${width}px`, async ({ page }, info) => {
      const apiReads: string[] = [];
      page.on("request", (request) => { if (new URL(request.url()).port === "8000") apiReads.push(new URL(request.url()).pathname); });
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/start");
      await page.locator("#app-language").selectOption(locale);
      await expect(page.getByRole("heading", { name: locale === "en" ? "Choose your experiment" : "Elija su experimento" })).toBeVisible();
      await expect.poll(() => apiReads.includes("/experiments/catalog")).toBe(true);
      expect(apiReads.filter((path) => path !== "/experiments/catalog")).toEqual([]);
      expect(apiReads.filter((path) => path === "/experiments/catalog")).toHaveLength(1);
      const cards = page.locator("button[aria-pressed]");
      await expect(cards).toHaveCount(6);
      for (let index = 0; index < 6; index++) {
        await cards.nth(index).click();
        const details = page.locator("#experiment-details");
        await expect(details).toBeFocused();
        await expect(details.locator("dt")).toHaveCount(5);
        const practice = details.getByRole("radio", { name: locale === "en" ? /^Practice/ : /^Practicar/ });
        if (index === 0) {
          await expect(practice).not.toBeChecked();
          await expect(details.getByRole("radio", { name: locale === "en" ? /Join my study/ : /Participar en mi estudio/ })).not.toBeChecked();
          await practice.check();
        } else {
          await expect(practice).toBeChecked();
        }
      }
      await page.getByRole("radio", { name: locale === "en" ? /Join my study/ : /Participar en mi estudio/ }).check();
      await page.locator("#app-language").selectOption(locale === "en" ? "es-419" : "en");
      await expect(page.getByRole("radio", { name: locale === "en" ? /Participar en mi estudio/ : /Join my study/ })).toBeChecked();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const audit = await new AxeBuilder({ page: page as never }).analyze();
      expect(audit.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
      await page.screenshot({ path: info.outputPath(`catalog-${locale}-${width}.png`), fullPage: true, animations: "disabled" });
      await info.attach("initial-loading", { contentType: "application/json", body: JSON.stringify(await page.evaluate(() => ({
        navigation: performance.getEntriesByType("navigation")[0].toJSON(),
        scripts: performance.getEntriesByType("resource").filter((entry) => (entry as PerformanceResourceTiming).initiatorType === "script").map((entry) => entry.toJSON()),
      }))) });
    });
  }
}

test("unavailable experiment remains visible with a next action", async ({ page }) => {
  await page.route("**/experiments/catalog", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.experiments = body.experiments.map((entry: { id: string }) => entry.id === "openmatb" ? { ...entry, component_available: false, unavailable_reason: "component_not_enabled" } : entry);
    await route.fulfill({ response, json: body });
  });
  await page.goto("/start?experiment=openmatb");
  await page.locator("#app-language").selectOption("en");
  await expect(page.getByText(/ask the researcher to enable it/i)).toBeVisible();
  await expect(page.getByRole("link", { name: "Prepare experiment" })).toHaveCount(0);
});

test("cognitive battery is reachable and practice is preserved", async ({ page }) => {
  await page.goto("/start?experiment=screen");
  await page.locator("#app-language").selectOption("en");
  await page.getByRole("radio", { name: /^Practice/ }).check();
  await page.getByRole("link", { name: "Prepare experiment" }).click();
  await expect(page).toHaveURL(/\/screen\?purpose=practice/);
  await expect(page.getByRole("heading", { name: "Tests" })).toBeVisible();
  await expect(page.getByText("Practice", { exact: true })).toBeVisible();
  await expect(page.getByText("Practice is saved separately and does not complete a study visit.")).toBeVisible();
  await page.locator("#app-language").selectOption("es-419");
  await expect(page.getByRole("heading", { name: "Pruebas" })).toBeVisible();
});

test("OpenMATB language changes preserve setup choices", async ({ page, request }) => {
  const participant = `P${(process.pid % 50000) + 600000}`;
  expect((await request.post("http://127.0.0.1:8000/participants", { data: { id: participant, enrollment_date: "2026-09-04" } })).status()).toBe(201);
  await page.route("**/openmatb/displays", route => route.fulfill({ json: [
    { index: 0, label: "Display 1", width: 1920, height: 1080, x: 0, y: 0 },
    { index: 1, label: "Display 2", width: 1920, height: 1080, x: 1920, y: 0 },
  ] }));
  await page.goto("/openmatb/setup?purpose=practice");
  await page.locator("#om-participant").selectOption(participant);
  await page.locator("#om-visit").selectOption("2");
  await page.locator("#om-display").selectOption("0");
  await page.getByText("Ver configuración", { exact: true }).click();
  await page.locator("#om-theme").selectOption("cockpit@1.0.0");
  await page.locator("#app-language").selectOption("en");
  await expect(page.locator("#om-protocol")).toHaveValue("matb-fac-en@1.0.0");
  await expect(page.locator("#om-visit")).toHaveValue("2");
  await expect(page.locator("#om-display")).toHaveValue("0");
  await page.locator("#app-language").selectOption("es-419");
  await expect(page.locator("#om-theme")).toHaveValue("cockpit@1.0.0");
  await expect(page.locator("#om-visit")).toHaveValue("2");
});

test("all four cognitive tasks save practice without entering the study cohort", async ({ page, request }) => {
  const participant = `P${(process.pid % 50000) + 700000}`;
  await request.post("http://127.0.0.1:8000/participants", { data: { id: participant, enrollment_date: "2026-09-04" } });
  await page.goto("/screen?purpose=practice");
  await page.locator("#app-language").selectOption("en");
  await page.locator("#screen-participant").selectOption(participant);
  await page.getByRole("button", { name: "View instructions and begin" }).click();
  await page.clock.install();
  for (const title of ["Simple reaction time", "Choice reaction time", "Working memory (2-back)", "Mouse tracking"]) {
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Start", exact: true }).click();
    await page.clock.runFor(20000);
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.clock.runFor(40000);
  }
  await expect(page.getByRole("heading", { name: "Responses saved" })).toBeVisible();
  await expect(page.getByText("Practice completed. These results are not included in the study.")).toBeVisible();
  const summary = await (await request.get("http://127.0.0.1:8000/screen")).json();
  expect(summary.screens.some((row: { participant_id: string }) => row.participant_id === participant)).toBe(false);
});
