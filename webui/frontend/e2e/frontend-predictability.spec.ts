import { test, expect, type Page, type TestInfo } from "@playwright/test";
import { fixture, SUITE, BLOCK, NEXT_BLOCK, DRAFT } from "./openmatb-fixtures";

const labels = {
  en: ["Mental demand", "Physical demand", "Temporal demand", "Performance", "Effort", "Frustration"],
  "es-419": ["Demanda mental", "Demanda física", "Demanda temporal", "Rendimiento", "Esfuerzo", "Frustración"],
};
async function screenshot(page: Page, info: TestInfo, name: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true, animations: "disabled" });
}

for (const locale of ["en", "es-419"] as const) {
  const english = locale === "en";
  test(`workspace choice is explicit and remembered within the tab (${locale})`, async ({ page }) => {
    await page.addInitScript(value => localStorage.setItem("matb-fac.locale", value), locale);
    await page.goto("/");
    await page.getByRole("button", { name: english ? /^Researcher/ : /^Investigador/ }).click();
    await expect(page).toHaveURL(/\/tracker$/);
    expect(await page.evaluate(() => sessionStorage.getItem("matb.navigation.role"))).toBe("researcher");
    await page.reload();
    const switcher = page.getByRole("navigation", { name: english ? "Switch workspace" : "Cambiar espacio de trabajo" });
    await switcher.getByRole("link", { name: english ? "Participant" : "Participante", exact: true }).click();
    await expect(page).toHaveURL(/\/start$/);
    expect(await page.evaluate(() => sessionStorage.getItem("matb.navigation.role"))).toBe("participant");
    expect(new URL(page.url()).searchParams.has("purpose")).toBe(false);
  });
  test(`midpoint, draft reload, failed save and next-block isolation (${locale})`, async ({ page }) => {
    const state = await fixture(page, locale);
    await page.goto(`/openmatb/participant?session=${SUITE}`);
    const save = page.getByRole("button", { name: english ? "Save ratings and continue" : "Guardar escalas y continuar", exact: true });
    await expect(save).toBeDisabled();
    for (const label of labels[locale]) await page.getByRole("button", { name: english ? `Use 50 for ${label}` : `Usar 50 para ${label}`, exact: true }).click();
    await page.getByRole("radio").first().check();
    await expect(save).toBeEnabled();
    await page.reload();
    await expect(page.getByText(english ? /Draft restored/ : /Se restauró el borrador/)).toBeVisible();
    await expect(save).toBeEnabled();
    for (const label of labels[locale]) await expect(page.getByRole("slider", { name: label, exact: true })).toHaveValue("50");
    state.failSave = true;
    await save.click();
    await expect(page.getByRole("alert").filter({ hasText: "Save unavailable" })).toBeVisible();
    expect(await page.evaluate(key => sessionStorage.getItem(key), DRAFT)).not.toBeNull();
    state.failSave = false;
    await save.click();
    await expect(page.getByRole("heading", { name: english ? "Ready to continue" : "Listo para continuar" })).toBeVisible();
    expect(state.submissions).toHaveLength(2);
    expect(state.submissions[1]).toEqual({ block_instance_id: BLOCK, nasa_tlx: { mental_demand: 50, physical_demand: 50, temporal_demand: 50, performance: 50, effort: 50, frustration: 50 }, bedford: 1 });
    expect(await page.evaluate(key => sessionStorage.getItem(key), DRAFT)).toBeNull();
    state.current = { ...state.current, lifecycle: "AWAITING_SCALE", active_block: "MEDIUM", active_block_instance_id: NEXT_BLOCK };
    await expect(save).toBeDisabled();
    await expect(page.getByRole("button", { name: english ? "Use 50 for Mental demand" : "Usar 50 para Demanda mental", exact: true })).toBeVisible();
  });

  test(`preparation preserves choices through recheck and a blocked popup (${locale})`, async ({ page, request, context }) => {
    const state = await fixture(page, locale);
    const participant = english ? "P890001" : "P890002";
    const created = await request.post("http://127.0.0.1:8000/participants", { data: { id: participant, enrollment_date: "2026-09-10" } });
    expect([201, 409]).toContain(created.status());
    await page.goto("/openmatb/setup?purpose=practice");
    await page.locator("#om-participant").selectOption(participant);
    await page.locator("#om-visit").selectOption("2");
    await page.locator("#om-equipment").check();
    await page.getByRole("button", { name: english ? "Check again" : "Comprobar de nuevo", exact: true }).click();
    await expect(page.locator("#om-visit")).toHaveValue("2");
    await expect(page.locator("#om-display")).toHaveValue("1");
    await page.evaluate(() => {
      const original = window.open;
      window.open = () => null;
      window.addEventListener("restore-test-popup", () => { window.open = original; }, { once: true });
    });
    await page.getByRole("button", { name: english ? "Create session and open instructions" : "Crear sesión y abrir instrucciones", exact: true }).click();
    await expect(page).toHaveURL(/participant_window=blocked/);
    await expect(page.getByRole("button", { name: english ? "Reopen participant instructions" : "Reabrir instrucciones del participante" })).toBeVisible();
    expect(state.preparations).toHaveLength(1);
    expect(state.preparations[0]).toMatchObject({ execution_purpose: "practice", participant_id: participant, visit_ordinal: 2, display_index: 1 });
    expect(state.starts).toBe(0);
    await page.evaluate(() => window.dispatchEvent(new Event("restore-test-popup")));
    const popupPromise = context.waitForEvent("page");
    await page.getByRole("button", { name: english ? "Reopen participant instructions" : "Reabrir instrucciones del participante" }).click();
    await (await popupPromise).close();
    await expect(page.getByRole("button", { name: english ? "Reopen participant instructions" : "Reabrir instrucciones del participante" })).toHaveCount(0);
  });

  test(`failed and historical receipts preserve distinct save outcomes (${locale})`, async ({ page }) => {
    const state = await fixture(page, locale);
    state.current.lifecycle = "FAILED";
    const record = { session_id: SUITE, participant_id: "P01", visit_ordinal: 1, execution_purpose: "study", lifecycle: "FAILED", historical: false,
      block_order: state.current.block_order, attempts: [{ block_instance_id: BLOCK, profile: "LOW", task_status: "failed", artifact_status: "partial", ratings_status: "saved", legacy_import_status: "failed", evidence_status: "unavailable", capture_id: null, qualification: null }] };
    await page.route(`**/openmatb/sessions/${SUITE}/receipt`, route => route.fulfill({ json: record }));
    await page.goto(`/openmatb/session?session=${SUITE}`);
    const receipt = page.getByRole("region", { name: english ? "Session receipt" : "Comprobante de la sesión" });
    await expect(receipt).toBeVisible();
    const outcomes = receipt.locator("dl > div");
    await expect(outcomes.filter({ has: page.getByText(english ? "Ratings" : "Escalas", { exact: true }) }).locator("dd")).toHaveText(english ? "Saved" : "Guardado");
    await expect(outcomes.filter({ has: page.getByText(english ? "Study import" : "Importación al estudio", { exact: true }) }).locator("dd")).toHaveText(english ? "Failed" : "Error");
    await expect(outcomes.filter({ has: page.getByText(english ? "Native files" : "Archivos nativos", { exact: true }) }).locator("dd")).toHaveText(english ? "Incomplete" : "Incompleto");
    await expect(outcomes.filter({ has: page.getByText(english ? "Physical timing" : "Tiempo físico", { exact: true }) }).locator("dd")).toHaveText(english ? "Not assessed" : "Sin evaluar");
    expect(await page.locator('[aria-current="step"]').count()).toBe(0);
    record.historical = true; record.attempts = [];
    await page.reload();
    await expect(receipt.getByText(english ? /Detailed save states were not recorded/ : /Los estados detallados de guardado no se registraron/)).toBeVisible();
    await expect(receipt.locator("article")).toHaveCount(0);
  });

  test(`opening, connection recovery, popup recovery and practice continuity (${locale})`, async ({ page, context }) => {
    const state = await fixture(page, locale);
    state.current.lifecycle = "STARTING";
    await page.goto(`/openmatb/participant?session=${SUITE}`);
    await expect(page.getByRole("heading", { name: english ? "Opening the native task window" : "Abriendo la ventana de la tarea nativa" })).toBeVisible();
    state.current.lifecycle = "RUNNING";
    await expect(page.getByRole("heading", { name: english ? "OpenMATB running" : "OpenMATB en ejecución" })).toBeVisible();
    state.failPoll = true;
    const connectionError = page.getByRole("alert").filter({ hasText: "Connection interrupted" });
    await expect(connectionError).toBeVisible();
    state.failPoll = false;
    await expect(connectionError).toHaveCount(0);
    state.current = { ...state.current, execution_purpose: "practice", lifecycle: "COMPLETE", block_order: ["PRACTICE"], current_block_index: 1, active_block: null, active_block_instance_id: null };
    await page.goto(`/openmatb/session?session=${SUITE}&purpose=study&participant_window=blocked`);
    await expect(page.getByRole("region", { name: english ? "Session receipt" : "Comprobante de la sesión" })).toBeVisible();
    const popupPromise = context.waitForEvent("page");
    await page.getByRole("button", { name: english ? "Reopen participant instructions" : "Reabrir instrucciones del participante" }).click();
    const popup = await popupPromise;
    await popup.close();
    await expect(page.getByRole("button", { name: english ? "Reopen participant instructions" : "Reabrir instrucciones del participante" })).toHaveCount(0);
    expect(state.starts).toBe(0);
    await expect(page.getByRole("link", { name: english ? "Review this session" : "Revisar esta sesión" })).toHaveAttribute("href", `/evidence?session=${SUITE}&purpose=all`);
    await page.getByRole("link", { name: english ? "Prepare a new session" : "Preparar una sesión nueva" }).click();
    await expect(page).toHaveURL(/purpose=practice/);
    await expect(page.getByText(english ? "Practice is saved separately and does not complete a study visit." : "La práctica se guarda por separado y no completa una visita de estudio.", { exact: true })).toBeVisible();
  });

  for (const [width, height] of [[1280, 720], [1366, 768], [1920, 1080], [768, 1024], [390, 844]]) {
    test(`researcher and questionnaire layout ${locale} ${width}x${height}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height });
      const state = await fixture(page, locale);
      await page.goto("/openmatb/setup?purpose=practice");
      await expect(page.locator("#om-display")).toHaveValue("1");
      await expect(page.getByRole("button", { name: english ? "Create session and open instructions" : "Crear sesión y abrir instrucciones" })).toBeDisabled();
      await page.getByRole("button", { name: english ? "Select a participant" : "Seleccione un participante" }).click();
      await expect(page.locator("#om-participant")).toBeFocused();
      expect(await page.locator("#om-station").evaluate(element => Boolean(element.compareDocumentPosition(document.querySelector("#om-participant")!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
      await screenshot(page, info, "preparation");
      await page.goto(`/openmatb/participant?session=${SUITE}`);
      await expect(page.getByRole("region", { name: english ? "Workload questionnaire" : "Cuestionario de carga de trabajo" })).toBeVisible();
      await screenshot(page, info, "questionnaire");
      state.current = { ...state.current, lifecycle: "COMPLETE", active_block: null, active_block_instance_id: null };
      await page.goto(`/openmatb/session?session=${SUITE}`);
      await expect(page.getByRole("region", { name: english ? "Session receipt" : "Comprobante de la sesión" })).toBeVisible();
      await screenshot(page, info, "receipt");
      await page.goto("/evidence?purpose=all");
      await expect(page.getByRole("heading", { name: english ? "Scientific evidence" : "Evidencia científica", exact: true })).toBeVisible();
      await screenshot(page, info, "evidence-list");
    });
  }
}
