import { expect, test as base } from "@playwright/test";
import type { Page } from "@playwright/test";

export const test = base;
export { expect };

export type TestLocale = "en" | "es-CO";

/** Select only controls rendered by the researcher setup screen. */
export async function selectSetup(
  page: Page,
  participant: string,
  scenario: string,
  locale: TestLocale = "en",
): Promise<void> {
  await expect(page.locator("#mission-participant")).toBeVisible();
  await page.locator("#mission-participant").selectOption(participant);
  await expect(page.locator("#mission-visit")).toBeEnabled();
  await page.locator("#mission-visit").selectOption("1");
  await page.locator("#mission-scenario").selectOption(scenario);
  await page.locator("#mission-language").selectOption(locale);
}

async function submitIsa(page: Page): Promise<void> {
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(/ISA \/ response required/i);
  const rating = dialog.locator('input[name="isa-rating"]').first();
  await expect(rating).toBeAttached();
  await rating.check({ force: true });
  const submit = dialog.getByRole("button", { name: /submit rating/i });
  await expect(submit).toBeEnabled();
  await submit.click();
  // The protocol replaces the ISA probe with the next gate asynchronously.
  // Do not let the polling loop submit the still-mounted old form again.
  await expect.poll(() => visibleProbe(page), { timeout: 10_000 }).not.toBe("ISA");
}

async function submitSagat(page: Page): Promise<void> {
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(/situation awareness/i);
  // The freeze must conceal the operational display while the answer is
  // collected.  These assertions guard against accidentally scoring from
  // the live map or fleet panel.
  await expect(page.locator('[data-testid="map-root"]')).toHaveCount(0);
  await expect(page.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /alerts/i })).toHaveCount(0);
  const answer = dialog.locator('input[name="sagat-answer"]').first();
  await expect(answer).toBeAttached();
  await answer.check({ force: true });
  const submit = dialog.getByRole("button", { name: /submit answer/i });
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect.poll(() => visibleProbe(page), { timeout: 10_000 }).not.toBe("SAGAT");
}

async function submitPostBlock(page: Page): Promise<void> {
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(/post-block measures/i);
  const tlx = dialog.locator('input[type="range"]');
  // Six NASA-TLX dimensions and one Bedford value must all emit a change;
  // leaving the browser defaults untouched would not populate the reducer.
  await expect(tlx).toHaveCount(7);
  for (let index = 0; index < 7; index += 1) {
    const slider = tlx.nth(index);
    await slider.focus();
    await slider.press("Home");
    const target = index === 6 ? 5 : 4;
    const minimum = index === 6 ? 1 : 0;
    for (let step = minimum; step < target; step += 1) await slider.press("ArrowRight");
  }
  await dialog.getByRole("button", { name: /submit measures/i }).click();
  await expect(dialog).toBeHidden();
}

async function visibleProbe(page: Page): Promise<"ISA" | "SAGAT" | "POST_BLOCK" | null> {
  const dialog = page.getByRole("dialog");
  if (!(await dialog.isVisible().catch(() => false))) return null;
  const text = await dialog.innerText().catch(() => "");
  if (/ISA \/ response required/i.test(text)) return "ISA";
  if (/post-block measures/i.test(text)) return "POST_BLOCK";
  if (/situation awareness/i.test(text)) return "SAGAT";
  return null;
}

async function resolveVisibleProbe(page: Page): Promise<"ISA" | "SAGAT" | "POST_BLOCK" | null> {
  const kind = await visibleProbe(page);
  if (kind === "ISA") await submitIsa(page);
  else if (kind === "SAGAT") await submitSagat(page);
  else if (kind === "POST_BLOCK") await submitPostBlock(page);
  return kind;
}

async function assignActiveFleet(page: Page): Promise<void> {
  for (const aircraftId of ["UAS-01", "UAS-02"]) {
    // The accelerated fixture can reach its one-second ISA boundary while a
    // local browser is settling a command click.  Drain that visible gate and
    // continue assigning the remaining fleet before the SAGAT boundary.
    while (true) {
      const kind = await visibleProbe(page);
      if (kind === null) break;
      // Leave the post-block gate mounted for completeBlock's final loop;
      // that loop owns the two-scale submission and its completion boundary.
      if (kind === "POST_BLOCK") return;
      await resolveVisibleProbe(page);
    }
    const row = page.getByRole("listitem", { name: new RegExp(`^${aircraftId}\\b`, "i") });
    await expect(row).toBeVisible();
    try {
      await row.click({ timeout: 5_000 });
    } catch (error) {
      const probe = await visibleProbe(page);
      if (probe && probe !== "POST_BLOCK") {
        await resolveVisibleProbe(page);
        await row.click({ timeout: 5_000 });
      } else if (probe === "POST_BLOCK") {
        return;
      } else {
        throw error;
      }
    }
    while (true) {
      const probe = await visibleProbe(page);
      if (probe) {
        if (probe === "POST_BLOCK") return;
        await resolveVisibleProbe(page);
        continue;
      }
      const assign = page.getByRole("button", { name: /assign sector/i });
      await expect(assign).toBeEnabled();
      try {
        await assign.click({ timeout: 5_000 });
        break;
      } catch (error) {
        const probe = await visibleProbe(page);
        if (probe && probe !== "POST_BLOCK") continue;
        if (probe === "POST_BLOCK") return;
        throw error;
      }
    }
    await expect.poll(async () => {
      if (await visibleProbe(page)) return "probe";
      const rowText = await row.innerText().catch(() => "");
      return /transit|search|hold/i.test(rowText) ? "assigned" : "waiting";
    }, { timeout: 5_000 }).toMatch(/assigned|probe/);
  }
}

/**
 * Start one expected block, assign its complete synthetic fleet, and answer
 * every protocol gate through the rendered controls.  No lifecycle or
 * questionnaire endpoint is called by this helper.
 */
export async function completeBlock(
  page: Page,
  blockId: "PRACTICE" | "LOW" | "MEDIUM" | "HIGH",
): Promise<void> {
  const start = page.getByRole("button", { name: /start block/i });
  await expect(start).toBeVisible({ timeout: 20_000 });
  await expect(start).toBeEnabled();
  await start.click();
  await expect(page.locator("header")).toContainText(blockId);
  // The start handler refreshes the authoritative snapshot after the
  // lifecycle response.  Wait for that refresh/busy state before issuing the
  // first fleet command; otherwise a command can race the PREPARED→RUNNING
  // transition and be rejected by the backend.
  await expect(page.locator(".simulation-console")).toHaveAttribute("aria-busy", "false");
  await assignActiveFleet(page);

  // The short fixture has one ISA gate, one SAGAT freeze, and the two
  // post-block scales.  Waiting on each dialog keeps this deterministic while
  // still exercising the real accelerated WebSocket/tick path.
  while (true) {
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 20_000 });
    const kind = await resolveVisibleProbe(page);
    if (kind === "POST_BLOCK") break;
    if (kind === null) throw new Error("active protocol dialog has no recognized probe kind");
  }
}
