import { test, expect } from "@playwright/test";
import { approveStudyFixture, baseOccasion, post } from "./study-fixtures";
test("explicit descriptive freeze and reopen retain an incomplete denominator", async ({
  page,
  request,
}) => {
  const participant = `P${((process.pid % 7000) + 1) * 60 + 45}`;
  await post(request, "/participants", {
    id: participant,
    enrollment_date: "2026-09-10",
  });
  const occasion = await baseOccasion(request);
  const assignment = await approveStudyFixture(request, participant, [
    { ...occasion, key: "baseline", locale: "en" },
  ]);
  await page.goto("/study/analysis");
  await page.locator("#app-language").selectOption("en");
  await page
    .getByLabel("Frozen plan", { exact: true })
    .selectOption(assignment.version_id);
  await page
    .getByLabel("Researcher", { exact: true })
    .fill("Dr Browser Descriptive");
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Isolated incomplete denominator check");
  await page
    .getByRole("button", { name: "Inspect eligibility", exact: true })
    .click();
  await expect(page.getByText(/Included in denominator/)).toBeVisible();
  await page
    .getByRole("button", {
      name: "Execute and freeze description",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("link", { name: "Export data, code and offline replay" }),
  ).toBeVisible();
  const id = await page
    .getByLabel("Execution ID", { exact: true })
    .inputValue();
  expect(id).toBeTruthy();
  await expect(page).toHaveURL(new RegExp(`execution=${id}`));
  const stored = await (
    await request.get(`http://127.0.0.1:8000/study/analyses/${id}`)
  ).json();
  expect(stored.result.outcomes.observed.denominator).toBe(1);
  expect(stored.result.outcomes.observed.observed).toBe(0);
  await page.reload();
  await expect(
    page.getByRole("button", {
      name: "Execute and freeze description",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Frozen eligibility and selection", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Execution ID", { exact: true }).fill(id);
  await page.getByRole("button", { name: "Reopen", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Export data, code and offline replay" }),
  ).toBeVisible();
  const otherParticipant = `P${Number(participant.slice(1)) + 1}`;
  await post(request, "/participants", {
    id: otherParticipant,
    enrollment_date: "2026-09-10",
  });
  const other = await approveStudyFixture(request, otherParticipant, [
    { ...occasion, key: "baseline", locale: "en" },
  ]);
  // Reopen after a different plan has been explicitly previewed.
  await page.reload();
  await page
    .getByRole("button", { name: "Start a new analysis", exact: true })
    .click();
  await page
    .getByLabel("Frozen plan", { exact: true })
    .selectOption(other.version_id);
  await page.getByLabel("Researcher", { exact: true }).fill("Dr Other Plan");
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Different request state");
  await page
    .getByRole("button", { name: "Inspect eligibility", exact: true })
    .click();
  await expect(page.getByText(/Included in denominator/)).toBeVisible();
  await page.getByLabel("Execution ID", { exact: true }).fill(id);
  await page.getByRole("button", { name: "Reopen", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Execute and freeze description",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Start a new analysis", exact: true })
    .click();
  await expect(page.getByLabel("Frozen plan", { exact: true })).toHaveValue("");
  await page
    .getByLabel("Frozen plan", { exact: true })
    .selectOption(other.version_id);
  await page.getByLabel("Researcher", { exact: true }).fill("Dr Fresh Plan");
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Fresh explicit preview");
  const submitted = page.waitForRequest(
    (req) =>
      req.method() === "POST" && req.url().endsWith("/study/analyses/preview"),
  );
  await page
    .getByRole("button", { name: "Inspect eligibility", exact: true })
    .click();
  expect((await submitted).postDataJSON()).toEqual({
    version_id: other.version_id,
    actor: "Dr Fresh Plan",
    reason: "Fresh explicit preview",
    attempts: {},
    native_metric_ids: {},
    qualification_ids: {},
    hcf_attempts: {},
  });
  await page.locator("#app-language").selectOption("es-419");
  await expect(
    page.getByRole("heading", {
      name: "Análisis descriptivo del plan",
      exact: true,
    }),
  ).toBeVisible();
});
