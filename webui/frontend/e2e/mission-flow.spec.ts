import { completeBlock, expect, selectSetup, test } from "./fixtures";

test("researcher completes the full native sUAS protocol", async ({ page, request }, testInfo) => {
  // Keep the participant in the first Latin-square row (LOW/MEDIUM/HIGH)
  // while ensuring retries receive a fresh pseudonym in the isolated DB.
  const participantNumber = ((process.pid % 9_999) + 1) * 60 + testInfo.retry * 6;
  const participant = `P${String(participantNumber).padStart(2, "0")}`;
  const participantResponse = await request.post("http://127.0.0.1:8000/participants", {
    data: { id: participant, enrollment_date: "2026-08-01" },
  });
  expect(participantResponse.status()).toBe(201);

  await page.goto("/mission/setup");
  await expect(page).toHaveTitle(/MATB Research Console/i);
  await selectSetup(page, participant, "e2e_area_search", "en");
  await page.getByRole("checkbox", { name: /research instrument/i }).check();
  await page.getByRole("button", { name: /prepare session/i }).click();

  await expect(page).toHaveURL(/\/mission\?session=sim-/);
  await completeBlock(page, "PRACTICE");
  await completeBlock(page, "LOW");
  await completeBlock(page, "MEDIUM");
  await completeBlock(page, "HIGH");

  // Protocol completion leaves the controller paused so the researcher can
  // inspect the final state; finish is an explicit UI lifecycle action.
  await page.getByRole("button", { name: /finish session/i }).click();
  await page.getByRole("group", { name: /finish this session/i }).getByRole("button", { name: /confirm/i }).click();

  await expect(page).toHaveURL(/\/mission\/debrief\?session=sim-/);
  await expect(page.getByText(/deterministic replay verified/i)).toBeVisible();
  await expect(page.getByText(/descriptive feedback only/i)).toBeVisible();
});
