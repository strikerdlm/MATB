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
  await page.getByLabel("Execution ID", { exact: true }).fill(id);
  await page.getByRole("button", { name: "Reopen", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Export data, code and offline replay" }),
  ).toBeVisible();
  await page.locator("#app-language").selectOption("es-419");
  await expect(
    page.getByRole("heading", {
      name: "Análisis descriptivo del plan",
      exact: true,
    }),
  ).toBeVisible();
});
