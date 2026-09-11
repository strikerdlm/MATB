import { test, expect } from "@playwright/test";
import { approveStudyFixture, baseOccasion, post } from "./study-fixtures";

test("constrained bilingual authoring and frozen-language assigned PVT entry", async ({
  page,
  request,
}) => {
  await page.goto("/study");
  await page.locator("#app-language").selectOption("en");
  await page
    .getByRole("button", { name: "Load template", exact: true })
    .click();
  await expect(
    page.getByLabel("Preparation rule", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Freeze with approval", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Author preparation", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("combobox", { name: "Demonstration required", exact: true }),
  ).toHaveValue("");
  await page.locator("#app-language").selectOption("es-419");
  await expect(
    page.getByRole("combobox", { name: "Demostración requerida", exact: true }),
  ).toBeVisible();
  const participant = `P${((process.pid % 8000) + 1) * 60 + 1}`;
  await post(request, "/participants", {
    id: participant,
    enrollment_date: "2026-09-10",
  });
  const occasion = await baseOccasion(request);
  const assignment = await approveStudyFixture(request, participant, [
    { ...occasion, key: "baseline", locale: "en" },
  ]);
  const reopened = await post(
    request,
    `/study/versions/${assignment.version_id}/clone`,
    {},
  );
  await page.goto("/study");
  await page.locator("#app-language").selectOption("en");
  await page
    .getByRole("combobox", { name: "Saved draft", exact: true })
    .selectOption(reopened.id);
  await page
    .getByRole("button", { name: "Open saved draft", exact: true })
    .click();
  await page
    .getByLabel("Title", { exact: true })
    .fill("Saved and reopened browser draft");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByText("Draft saved", { exact: true })).toBeVisible();
  await page.goto("/start");
  await page.goto("/study");
  await page
    .getByRole("combobox", { name: "Saved draft", exact: true })
    .selectOption(reopened.id);
  await page
    .getByRole("button", { name: "Open saved draft", exact: true })
    .click();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
    "Saved and reopened browser draft",
  );
  await page
    .getByLabel("Title", { exact: true })
    .fill("Edited after reopening");
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(
    page.getByText("Validation passed", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Rehearse", exact: true }).click();
  await expect(
    page.getByText("Synthetic rehearsal completed; this is not approval.", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByLabel("Named researcher", { exact: true })
    .fill("Dr Browser Reopen");
  await page
    .getByLabel("Reason and review attestation", { exact: true })
    .fill("Review isolated reopening fixture");
  await page
    .getByRole("button", { name: "Freeze with approval", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(
              `http://127.0.0.1:8000/study/drafts/${reopened.id}`,
            )
          ).json()
        ).frozen_version_id,
    )
    .toBeTruthy();
  const history = await (
    await request.get(
      `http://127.0.0.1:8000/study/drafts/${reopened.id}/history`,
    )
  ).json();
  expect(history.validations).toHaveLength(1);
  expect(history.approval).toBeTruthy();
  await page.locator("#app-language").selectOption("es-419");
  const attempt = await post(
    request,
    `/assessments/occasions/${assignment.occasions.baseline}/attempts`,
    { execution_purpose: "study" },
  );
  await page.goto(
    `/pvt?purpose=study&attempt=${attempt.id}&participant=${participant}&visit=${assignment.visit_id}`,
  );
  // Researcher preference remains Spanish while participant instructions use frozen English.
  await expect(page.locator("#app-language")).toHaveValue("es-419");
  await expect(
    page.getByRole("button", { name: "Continue to KSS", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Continue to KSS", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Karolinska Sleepiness Scale",
      exact: true,
    }),
  ).toBeVisible();
  const detail = await (
    await request.get(
      `http://127.0.0.1:8000/assessments/attempts/${attempt.id}`,
    )
  ).json();
  expect(detail.acquisition_state).toBe("started");
  expect(detail.assignment_context.locale).toBe("en");
  await page.screenshot({
    path: "/tmp/task3-assigned-pvt.png",
    fullPage: true,
  });
  await page.goto("/station");
  await expect
    .poll(
      async () =>
        (await (await request.get("http://127.0.0.1:8000/station")).json())
          .reservation?.uncertain,
    )
    .toBe(true);
  await post(request, "/station/recover-idle", {
    actor: "Dr Registry Fixture",
    reason:
      "Browser left assigned measurement; researcher verifies station idle",
  });
  expect(
    (await (await request.get("http://127.0.0.1:8000/station")).json())
      .reservation,
  ).toBeNull();
});
