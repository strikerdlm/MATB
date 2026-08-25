import { readFileSync } from "node:fs";
import { request } from "node:https";
import { expect, test, type Page } from "@playwright/test";
import { e2eNowUtc as nowUtc, missionFixture } from "./mission-fixture.js";

const password = "correct horse battery staple";
const clientCertificatePath = "/tmp/sms-console-e2e-client.crt";
const clientKeyPath = "/tmp/sms-console-e2e-client.key";
const certificateAuthorityPath = "/tmp/sms-console-e2e-ca.crt";
const mission = missionFixture("mission-1");

async function login(page: Page, userId: string): Promise<void> {
  await page.getByLabel("User ID").fill(userId);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText(userId, { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Missions" })).toBeVisible();
}
async function createMission(page: Page, missionId: string, state: "Draft" | "UnderReview" = "Draft", aircraftId = "aircraft-1"): Promise<void> {
  await page.getByText("Create mission", { exact: true }).first().click(); await page.getByLabel("Mission JSON").fill(JSON.stringify(missionFixture(missionId, state, aircraftId))); await page.getByRole("button", { name: "Create mission" }).click(); await expect(page.getByText(missionId, { exact: true })).toBeVisible();
}
async function lock(page: Page): Promise<void> { await page.getByRole("button", { name: "Lock", exact: true }).click(); await expect(page.getByRole("heading", { name: "Sign in to operational console" })).toBeVisible(); }
async function reauthenticate(page: Page): Promise<void> { const field = page.getByLabel("Re-authentication password"); await field.fill(password); await page.getByRole("button", { name: "Re-authenticate", exact: true }).click(); await expect(field).toHaveValue(""); await expect(page.getByText("Connected to Edge API", { exact: true })).toBeVisible(); }
async function checklistAndGate(page: Page, userId: string, gate: string): Promise<void> {
  await login(page, userId); await expect(page.getByRole("button", { name: "Re-authenticate", exact: true })).toBeVisible(); await reauthenticate(page);
  await page.getByLabel("Item ID").fill(`${gate}-preflight`); await page.getByLabel("Reason", { exact: true }).first().fill(`${gate} evidence reviewed`); await page.getByRole("button", { name: "Respond to item" }).click(); await expect(page.getByText(`${gate}-preflight`, { exact: true })).toBeVisible();
  const card = page.locator(".gate-live").filter({ has: page.getByRole("heading", { name: gate, exact: true }) }); await card.getByLabel("Decision").selectOption("accept"); await card.getByLabel("Reason").fill(`${gate} accountable decision`); await card.getByRole("button", { name: "Record gate" }).click(); await expect(card.getByRole("status").first()).toContainText("accept"); await lock(page);
}

async function ingestTelemetry(revisionId: string, sequence: number, aircraftId = "aircraft-1"): Promise<number> {
  const payload = JSON.stringify({ revisionId, sequence, event: { eventId: `telemetry-e2e-${aircraftId}-${sequence}`, aircraftId, observedAtUtc: nowUtc, position: { lat: 4.7, lon: -74.1, altitudeMslM: 1300 + sequence }, energy: { stateOfChargePercent: Math.max(0, 73 - sequence) }, platform: { propulsion: "normal", gnss: "normal", c2Link: "normal" }, sourcePackageIds: ["policy-console-e2e"] } });
  return new Promise((resolve, reject) => {
    const operation = request({ hostname: "127.0.0.1", port: 4173, path: "/api/telemetry/ingest", method: "POST", cert: readFileSync(clientCertificatePath), key: readFileSync(clientKeyPath), ca: readFileSync(certificateAuthorityPath), rejectUnauthorized: true, headers: { "content-type": "application/json", "content-length": Buffer.byteLength(payload) } }, (response) => { response.resume(); response.once("end", () => resolve(response.statusCode ?? 0)); });
    operation.once("error", reject); operation.end(payload);
  });
}

test("uses authenticated HTTPS and mTLS Edge state through create, revision, isolation, gates, export and restart", async ({ page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = []; const pageErrors: string[] = []; const failedResponses: { path: string; status: number }[] = []; let expectedResourceErrorUntil = 0;
  page.on("console", (message) => { if (message.type() !== "error") return; if (Date.now() <= expectedResourceErrorUntil && /^Failed to load resource: the server responded with a status of 409/.test(message.text())) return; consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => pageErrors.push(error.message)); page.on("response", (response) => { if (response.status() >= 400) failedResponses.push({ path: decodeURIComponent(new URL(response.url()).pathname), status: response.status() }); });
  await page.setViewportSize({ width: 1440, height: 1000 }); await page.goto("/"); await expect(page).toHaveTitle(/FAC ISR SMS/i); await login(page, "commander-1");
  await expect(page.getByText("No assigned missions", { exact: true })).toBeVisible(); await page.getByText("Create mission", { exact: true }).first().click(); await page.getByLabel("Mission JSON").fill(JSON.stringify(mission)); await page.getByRole("button", { name: "Create mission" }).click();
  await expect(page.getByText("mission-1", { exact: true })).toBeVisible(); await expect(page.getByText(/Revision 0 · Draft/)).toBeVisible(); await expect(page.locator(".gate-live")).toHaveCount(4); await expect(page.getByText("policy-console-e2e", { exact: true })).toBeVisible();
  expect(await ingestTelemetry("mission-1:r0", 1)).toBe(202); await expect(page.getByText(/sequence 1/)).toBeVisible();
  await page.getByText("Create material revision").click(); await page.getByLabel("Revision change JSON").fill("{"); await page.getByRole("button", { name: "Submit revision" }).click(); const revisionError = page.getByRole("alert", { name: "Revision JSON must be valid" }); await expect(revisionError).toBeVisible(); await expect(revisionError).toBeFocused();
  await page.getByLabel("Revision change JSON").fill(JSON.stringify({ expectedRevisionId: "mission-1:r0", change: { field: "route", previous: mission.route, next: { ...mission.route, routeHash: "route-hash-2" } } })); await page.getByRole("button", { name: "Submit revision" }).click(); await expect(page.getByText(/Revision 1 · Planned/)).toBeVisible(); await expect(page.getByText("No authorized telemetry records received")).toBeVisible();
  expect(await ingestTelemetry("mission-1:r1", 2)).toBe(202); await expect(page.getByText(/sequence 2/)).toBeVisible();
  await page.getByLabel("Item ID").fill("premature-commander-preflight"); await page.getByLabel("Reason", { exact: true }).first().fill("commander evidence reviewed"); await page.getByRole("button", { name: "Respond to item" }).click(); await expect(page.getByText("premature-commander-preflight", { exact: true })).toBeVisible();
  const commander = page.locator(".gate-live").filter({ has: page.getByRole("heading", { name: "commander", exact: true }) }); await commander.getByLabel("Decision").selectOption("accept"); await commander.getByLabel("Reason").fill("premature commander decision"); expectedResourceErrorUntil = Date.now() + 2_000; const blockedResponse = page.waitForResponse((response) => decodeURIComponent(new URL(response.url()).pathname) === "/api/revisions/mission-1:r1/gates/commander"); await commander.getByRole("button", { name: "Record gate" }).click(); expect((await blockedResponse).status()).toBe(409); await expect(page.getByText(/commander acceptance requires all other gates/i)).toBeVisible(); await page.waitForTimeout(100); expectedResourceErrorUntil = 0; await lock(page);
  await checklistAndGate(page, "maintainer-1", "maintenance"); await checklistAndGate(page, "operator-1", "operator"); await checklistAndGate(page, "safety-1", "safety"); await checklistAndGate(page, "commander-1", "commander");
  await login(page, "commander-1"); await reauthenticate(page); await page.getByRole("button", { name: "Request signed export" }).click(); await expect(page.getByText("Ed25519", { exact: true })).toBeVisible(); await expect(page.getByText("console-e2e-export", { exact: true })).toBeVisible();

  let releaseDelayed!: () => void; let delayedCaptured!: () => void; const releaseDelayedPromise = new Promise<void>((resolve) => { releaseDelayed = resolve; }); const delayedCapturedPromise = new Promise<void>((resolve) => { delayedCaptured = resolve; });
  await page.route("**/api/missions", async (route) => { const response = await route.fetch(); delayedCaptured(); await releaseDelayedPromise; await route.fulfill({ response }); }, { times: 1 });
  await page.getByLabel("Re-authentication password").fill(password); await page.getByRole("button", { name: "Re-authenticate", exact: true }).click(); await delayedCapturedPromise; await lock(page); await login(page, "administrator-1"); releaseDelayed(); await page.waitForTimeout(250);
  await expect(page.getByText("administrator-1", { exact: true })).toBeVisible(); await expect(page.getByText("No assigned missions", { exact: true })).toBeVisible(); await expect(page.getByText("console-e2e-export", { exact: true })).toHaveCount(0); await expect(page.getByText(/sequence 2/)).toHaveCount(0); await lock(page); await login(page, "commander-1");

  const revisionBefore = await page.getByText(/Revision 1 · Planned/).innerText(); const gatesBefore = await page.locator(".gate-live > .live-status").allTextContents(); const auditFacts = page.getByTestId("audit-facts"); const auditBefore = await auditFacts.textContent(); const auditHashBefore = await auditFacts.locator("code").textContent(); expect(gatesBefore).toEqual(["accept", "accept", "accept", "accept"]); expect(await auditFacts.locator(".live-status").textContent()).toBe("healthy"); expect(await auditFacts.locator("p").textContent()).toMatch(/^[1-9]\d* events$/); expect(auditHashBefore).toMatch(/^[a-f0-9]{64}$/); await lock(page);
  const restart = await page.request.post("/__test/restart"); expect(restart.status()).toBe(202); await page.waitForTimeout(350); await expect.poll(async () => { try { return (await page.request.get("/healthz")).status(); } catch { return 0; } }, { timeout: 15_000 }).toBe(200); await login(page, "commander-1");
  expect(await page.getByText(/Revision 1 · Planned/).innerText()).toBe(revisionBefore); expect(await page.locator(".gate-live > .live-status").allTextContents()).toEqual(gatesBefore); expect(await page.getByTestId("audit-facts").textContent()).toBe(auditBefore); expect(await page.getByTestId("audit-facts").locator("code").textContent()).toBe(auditHashBefore); expect(await ingestTelemetry("mission-1:r1", 3)).toBe(202); await expect(page.getByText(/sequence 3/)).toBeVisible();
  expect(await page.locator("vite-error-overlay, nextjs-portal").count()).toBe(0); expect((await page.locator("body").innerText()).length).toBeGreaterThan(500); await page.screenshot({ path: "/tmp/sms-console-review2-desktop-en.png", fullPage: false });
  expect(failedResponses).toEqual([{ path: "/api/revisions/mission-1:r1/gates/commander", status: 409 }]); expect(consoleErrors).toEqual([]); expect(pageErrors).toEqual([]);
});

test("localizes the complete operational surface and retains reduced-motion, keyboard and tablet behavior", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); await page.setViewportSize({ width: 820, height: 1180 }); await page.goto("/"); await login(page, "commander-1"); await createMission(page, "mission-es"); await page.getByRole("button").filter({ hasText: "mission-es" }).click(); await page.route("**/api/missions", async (route) => { const response = await route.fetch(); const body = await response.json(); await route.fulfill({ response, json: { ...body, missions: body.missions.map((item: { missionId: string; currentRevision: Record<string, unknown> }) => item.missionId === "mission-es" ? { ...item, currentRevision: { ...item.currentRevision, state: "UnderReview" } } : item) } }); }, { times: 1 }); await reauthenticate(page); await page.getByRole("button", { name: "Change language" }).click();
  for (const name of ["Misiones", "Revisión actual", "Franja de seguridad de misión", "Lista de verificación por ítems", "Cuatro aprobaciones separadas por rol", "Telemetría de solo lectura", "Paquetes, disponibilidad, auditoría y exportación"]) await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("En revisión", { exact: true }).first()).toBeVisible(); expect(await page.locator("body").innerText()).not.toMatch(/Missions|Current revision|Itemized checklist|Four role-separated gates|Read-only telemetry|Package, readiness, audit and export|UnderReview/); for (const raw of ["ready", "pass", "accept", "active", "healthy", "operator", "maintenance", "safety", "commander"]) await expect(page.getByText(raw, { exact: true })).toHaveCount(0); await page.getByRole("button", { name: "Alternar tema diurno y nocturno" }).click(); await expect(page.locator(".console-shell")).toHaveClass(/theme-day/); await page.keyboard.press("Tab"); await expect(page.locator(":focus-visible")).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true); expect(await page.locator("vite-error-overlay, nextjs-portal").count()).toBe(0); await page.screenshot({ path: "/tmp/sms-console-review2-tablet-es.png", fullPage: false });
});

test("makes safe mode read-only and explains every blocked unsafe action", async ({ page }) => {
  await page.goto("/"); await login(page, "commander-1"); await createMission(page, "mission-safe-view"); await lock(page); await page.route("**/readyz", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ status: "not_ready", technicalReady: false, operationalReady: false, checks: { database: { status: "pending", detail: "read-only safe mode" } } }) })); await login(page, "commander-1"); await page.getByRole("button").filter({ hasText: "mission-safe-view" }).click(); await expect(page.getByText("Read-only safe mode", { exact: true })).toBeVisible(); await page.getByText("Create material revision").click();
  for (const name of ["Submit revision", "Respond to item", "Record gate", "Re-authenticate", "Request signed export"]) await expect(page.getByRole("button", { name, exact: true }).first()).toBeDisabled();
  await expect(page.locator(".state-block:visible").filter({ hasText: "Read-only safe mode: state-changing actions are disabled" }).first()).toBeVisible(); await page.screenshot({ path: "/tmp/sms-console-review2-safe-mode.png", fullPage: false });
});

test("enters read-only safe mode immediately after a stable runtime persistence failure", async ({ page }) => {
  await page.goto("/"); await login(page, "commander-1"); await createMission(page, "mission-safe-runtime"); await page.getByRole("button").filter({ hasText: "mission-safe-runtime" }).click();
  await page.route("**/api/revisions/mission-safe-runtime%3Ar0/checklist-responses", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "SAFE_MODE_DATABASE_FAILURE", message: "package writes are disabled while the local database is unavailable" }) }), { times: 1 });
  await page.getByLabel("Item ID").fill("runtime-safe-mode"); await page.getByLabel("Reason", { exact: true }).first().fill("runtime failure"); await page.getByRole("button", { name: "Respond to item" }).click();
  await expect(page.getByText("Read-only safe mode", { exact: true })).toBeVisible(); await expect(page.getByRole("button", { name: "Respond to item" })).toBeDisabled(); await expect(page.getByRole("button", { name: "Re-authenticate" })).toBeDisabled();
});

test("recovers the login form after authenticated bootstrap disconnects", async ({ page }) => {
  await page.route("**/api/missions", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "EDGE_UNAVAILABLE", message: "Edge unavailable" }) }), { times: 1 }); await page.goto("/"); await page.getByLabel("User ID").fill("operator-1"); await page.getByLabel("Password").fill(password); await page.getByRole("button", { name: "Sign in", exact: true }).click(); await expect(page.getByRole("heading", { name: "Sign in to operational console" })).toBeVisible(); await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled(); await expect(page.getByText("Edge API disconnected", { exact: true })).toBeVisible();
});

test("keeps sign-in disabled until an old-session lock is confirmed", async ({ page }) => {
  await page.goto("/"); await login(page, "operator-1"); await page.route("**/api/auth/lock", (route) => route.abort("failed"), { times: 1 }); await page.getByRole("button", { name: "Lock", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sign in to operational console" })).toBeVisible(); await expect(page.getByText("operator-1", { exact: true })).toHaveCount(0); await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeDisabled(); await expect(page.getByText("Lock could not be confirmed — sign-in remains disabled", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Retry lock" }).click(); await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled(); await expect(page.getByText("Locked", { exact: true })).toBeVisible();
});

test("expires an open console at the real server idle deadline without probe keepalive", async ({ page }) => {
  expect((await page.request.post("/__test/clock", { data: { nowUtc } })).status()).toBe(204); await page.goto("/"); await login(page, "commander-1"); await createMission(page, "mission-expiry", "Draft", "aircraft-expiry"); await page.getByRole("button").filter({ hasText: "mission-expiry" }).click(); expect(await ingestTelemetry("mission-expiry:r0", 1, "aircraft-expiry")).toBe(202); await expect(page.getByText(/sequence 1/)).toBeVisible();
  const passiveExpiry = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/auth/status" && response.status() === 401); expect((await page.request.post("/__test/clock", { data: { nowUtc: "2026-08-25T12:15:00.000Z" } })).status()).toBe(204); await passiveExpiry; await expect(page.getByRole("heading", { name: "Sign in to operational console" })).toBeVisible(); await expect(page.getByText("Session expired — sign in again", { exact: true })).toBeVisible(); await expect(page.getByText(/sequence 1/)).toHaveCount(0);
});
