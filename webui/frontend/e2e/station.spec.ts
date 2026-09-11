import { test, expect } from "@playwright/test";
import { approveStudyFixture, baseOccasion, post } from "./study-fixtures";
const api = "http://127.0.0.1:8000";
test("whole visit protects rating gaps and researcher explicitly drains queue", async ({
  page,
  request,
}) => {
  const participant = `P${((process.pid % 7000) + 1) * 60 + 49}`;
  await post(request, "/participants", {
    id: participant,
    enrollment_date: "2026-09-10",
  });
  const occasion = await baseOccasion(request);
  const assignment = await approveStudyFixture(request, participant, [
    { ...occasion, key: "baseline", locale: "en" },
  ]);
  const attempt = await post(
    request,
    `/assessments/occasions/${assignment.occasions.baseline}/attempts`,
    { execution_purpose: "study" },
  );
  await post(request, `/assessments/attempts/${attempt.id}/start`);
  const queued = await request.post(api + "/analysis/run", { data: {} });
  expect(queued.status()).toBe(202);
  const job = await queued.json();
  await post(request, `/assessments/attempts/${attempt.id}/interrupt`, {
    category: "operator_stop",
  });
  expect(
    (await (await request.get(api + "/station")).json()).reservation,
  ).not.toBeNull();
  expect(
    (await (await request.get(api + "/station/jobs/" + job.job_id)).json())
      .status,
  ).toBe("queued");
  await page.goto("/station");
  await page.locator("#app-language").selectOption("en");
  await expect(
    page.getByText("Visit protected: heavy work waits for explicit closure."),
  ).toBeVisible();
  await page
    .getByLabel("Researcher", { exact: true })
    .fill("Dr Browser Station");
  await page
    .getByLabel("Reason and verification", { exact: true })
    .fill("Browser stopped; ratings and recovery finished");
  await page.getByRole("button", { name: "Close visit", exact: true }).click();
  await expect
    .poll(async () => {
      const row = await (
        await request.get(api + "/station/jobs/" + job.job_id)
      ).json();
      return ["complete", "failed"].includes(row.status);
    })
    .toBe(true);
  expect(
    (await (await request.get(api + "/station")).json()).reservation,
  ).toBeNull();
  await page
    .getByRole("button", { name: "Begin maintenance", exact: true })
    .click();
  await expect(
    page.getByText("Maintenance active; acquisition is blocked."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "End maintenance", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (await (await request.get(api + "/station")).json()).maintenance,
    )
    .toBe(false);
});
