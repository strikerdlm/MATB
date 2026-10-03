import { expect, test } from "@playwright/test";

for (const mode of ["reload", "missing-lease", "blocked-start"] as const) {
  test(`synthetic Polar controls: ${mode}`, async ({ page }, testInfo) => {
    let capture: Record<string, unknown> | null = mode === "missing-lease" ? sample("capturing") : null;
    let stopCount = 0;
    await page.route("**/physiology/polar-h10/v1/**", async route => {
      const path = new URL(route.request().url()).pathname.split("/v1")[1];
      let body: unknown = {};
      let status = 200;
      if (path === "/connection") body = { connected: true, device_alias: "Synthetic H10", capabilities: null };
      else if (path === "/captures/active") body = capture?.lifecycle === "capturing" ? capture : null;
      else if (path === "/captures") {
        const request = route.request().postDataJSON();
        expect(request.matb_session_kind).toBe("generic");
        expect(request.matb_session_id).toBeUndefined();
        capture = sample("created"); body = { capture, controller_lease: "synthetic-controller" }; status = 201;
      } else if (path.endsWith("/start")) {
        if (mode === "blocked-start") { status = 409; body = { detail: { code: "station_visit_reserved" } }; }
        else { capture = sample("capturing"); body = capture; }
      } else if (path.endsWith("/stop")) {
        expect(route.request().headers()["x-polar-controller"]).toBe("synthetic-controller");
        stopCount++; capture = sample("complete"); body = capture;
      } else if (path.endsWith("/analysis")) body = { capture_id: "synthetic-capture", valid: false, reason: "synthetic_no_signals", workload_responses: [] };
      else if (path.endsWith("/control")) {
        expect(route.request().headers()["x-polar-controller"]).toBe("synthetic-controller"); body = capture;
      } else body = capture;
      await route.fulfill({ status, json: body });
    });
    await page.goto("/physiology/polar-h10?purpose=practice&locale=en");
    if (mode === "missing-lease") {
      await expect(page.getByText("synthetic-capture", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: /Stop and finalize|Detener y finalizar/ })).toBeDisabled();
    } else {
      await page.getByLabel(/Pseudonym|Pseudónimo/).fill("P01");
      await page.getByRole("button", { name: /^(Prepare|Preparar)$/ }).click();
      await page.getByRole("button", { name: /Start recording|Iniciar grabación/ }).click();
      if (mode === "blocked-start") await expect(page.getByRole("alert").filter({ hasText: /Another visit owns|Otra visita ocupa/ })).toBeVisible();
      else {
        await expect(page.getByRole("button", { name: /Stop and finalize|Detener y finalizar/ })).toBeEnabled();
        await page.reload();
        await expect(page.getByRole("button", { name: /Stop and finalize|Detener y finalizar/ })).toBeEnabled();
        await expect(page.getByRole("button", { name: /Stop and finalize|Detener y finalizar/ })).toBeInViewport();
        await page.screenshot({ path: testInfo.outputPath("polar-restored-stop.png"), fullPage: true });
        await page.getByRole("button", { name: /Stop and finalize|Detener y finalizar/ }).click();
        await expect(page.getByText(/complete · ECG/)).toBeVisible();
        expect(stopCount).toBe(1);
        await expect(page.getByRole("button", { name: /Download bundle|Descargar paquete/ })).toHaveCount(0);
      }
    }
    await expect(page.getByText(/AI \/ IA/)).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`polar-${mode}.png`), fullPage: true });
  });
}
function sample(lifecycle: string) {
  return { capture_id: "synthetic-capture", participant_pseudonym: "P01", execution_purpose: "practice", matb_session_kind: "generic", matb_session_id: "synthetic-capture", lifecycle, requested_settings: { ecg_sample_rate_hz: 130, acc_sample_rate_hz: 50, acc_range_g: 2 }, artifact_state: lifecycle === "complete" ? "finalized" : "none", incomplete_reasons: [], gap_count: 0 };
}
