import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repository = path.resolve(__dirname, "../../..");
const python = process.env.MATB_PYTHON || "python";

test("scientific capture upload, metric evidence and offline export", async ({ page, request }, info) => {
  const root = info.outputPath("synthetic-reference"); fs.mkdirSync(root, { recursive: true });
  execFileSync(python, ["-c", `from pathlib import Path
import sys
from matb_integration.evidence.reference import synthetic_capture
bundle = synthetic_capture(Path(sys.argv[1]), identity='browser-reference')
for role, content in bundle.items():
    (Path(sys.argv[1]) / (role + '.upload')).write_bytes(content)
`, root], { cwd: repository, env: { ...process.env, PYTHONPATH: repository, PYTHONDONTWRITEBYTECODE: "1" } });
  const created = await request.post("http://127.0.0.1:8000/participants", { data: { id: "P01", enrollment_date: "2026-09-09" } });
  expect([200, 201, 409]).toContain(created.status());
  await page.goto("/upload");
  await page.getByLabel(/Tipo de registro|Record type/).selectOption("evidence");
  await expect(page.locator("#evidence-capture_manifest")).toBeVisible();
  for (const role of ["capture_manifest", "scenario_manifest", "events", "timing"]) {
    await page.locator(`#evidence-${role}`).setInputFiles(path.join(root, `${role}.upload`));
  }
  await page.getByRole("button", { name: /Importar evidencia|Import evidence/ }).click();
  await expect(page.locator("button[data-metric=track_rmse_deviation]")).toBeVisible();
  await page.locator("button[data-metric=track_rmse_deviation]").click();
  await page.getByRole("button", { name: /track.sample · center_deviation/ }).first().click();
  await expect(page.getByText(/software_receipt · software · python.perf_counter/)).toBeVisible();
  await page.locator("button[data-metric=comm_d_prime]").click();
  await expect(page.getByText("physical_audio_onset_not_qualified", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /comm_d_prime/ })).toBeDisabled();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /Exportar evidencia verificable|Export verifiable evidence/ }).click();
  const download = await downloadPromise;
  const archive = info.outputPath("evidence.zip"); await download.saveAs(archive);
  const verified = JSON.parse(execFileSync(python, ["-m", "matb_integration.evidence", archive], {
    cwd: repository, env: { ...process.env, PYTHONPATH: repository, PYTHONDONTWRITEBYTECODE: "1" }, encoding: "utf8",
  }));
  expect(verified.verified).toBe(true);
  await info.attach("offline-recomputation", { body: JSON.stringify(verified), contentType: "application/json" });
  await page.screenshot({ path: info.outputPath("metric-evidence.png"), fullPage: true });
  await page.goto("/evidence");
  await page.getByRole("button", { name: /P01 · REFERENCE/ }).click();
  await expect(page.locator("button[data-metric=track_rmse_deviation]")).toBeVisible();
  await page.locator("button[data-metric=sysmon_hit_rate]").click();
  await page.getByRole("button", { name: /sysmon.opportunity.closed/ }).first().click();
  await expect(page.getByRole("region", { name: /Revisión de evento|Event review/ })).toBeVisible();
  await expect(page.getByText(/exposición visual original no está disponible|Original visual exposure is unavailable/)).toBeVisible();
  await page.screenshot({ path: info.outputPath("event-workspace-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("tab", { name: /Evidencia|Evidence/ })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("event-workspace-mobile.png"), fullPage: true });
});
