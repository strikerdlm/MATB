import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import dgram from "node:dgram";

function telemetryPacket(index: number): Buffer {
  const buffer = Buffer.alloc(97);
  for (let value = 0; value < 20; value += 1) {
    buffer.writeFloatLE(value === 0 ? index / 60 : value, value * 4);
  }
  buffer.writeUInt8(4, 80);
  for (let motor = 0; motor < 4; motor += 1) buffer.writeFloatLE(1000 + motor, 81 + motor * 4);
  return buffer;
}

async function primeTelemetry(): Promise<void> {
  const socket = dgram.createSocket("udp4");
  await new Promise<void>((resolve, reject) => {
    socket.once("error", reject);
    let sent = 0;
    for (let index = 0; index < 24; index += 1) {
      socket.send(telemetryPacket(index), 9001, "127.0.0.1", (error) => {
        if (error) reject(error);
        sent += 1;
        if (sent === 24) { socket.close(); resolve(); }
      });
    }
  });
}

test("Liftoff setup keeps lease private and completes the phase workflow", async ({ page, request }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await request.post("http://127.0.0.1:8000/participants", {
    data: { id: "P01", enrollment_date: "2026-08-18" },
  });
  await request.put("http://127.0.0.1:8000/participants/P01/study-context", {
    data: {
      task_sequence: "MATB_LIFTOFF",
      prior_fpv_hours: 10,
      gaming_hours_per_week: 2,
    },
  });
  await primeTelemetry();

  await page.goto("/liftoff/setup");
  await page.locator("#app-language").selectOption("en");
  await expect(page.getByText("Telemetry ready", { exact: false })).toBeVisible();
  expect((await new AxeBuilder({ page: page as never }).analyze()).violations).toEqual([]);
  await page.getByLabel("Participant").selectOption("P01");
  await page.getByLabel("Visit").selectOption("1");
  await page.getByRole("button", { name: /Prepare Liftoff session/i }).click();
  await expect(page).toHaveURL(/\/liftoff\/session\?session=/);
  const currentUrl = page.url();
  expect(currentUrl).not.toContain("secret");
  expect(await page.evaluate(() => Object.keys(sessionStorage).some((key) => key.startsWith("matb.liftoff.") && key.endsWith(".lease")))).toBe(true);
  expect((await new AxeBuilder({ page: page as never }).analyze()).violations).toEqual([]);

  page.on("dialog", (dialog) => void dialog.accept());
  for (const action of [
    /Start baseline/i,
    /Finish baseline/i,
    /Start FPV task/i,
    /Finish FPV task/i,
    /Start recovery/i,
    /Finish recovery/i,
  ]) {
    await page.getByRole("button", { name: action }).click();
  }
  await expect(page).toHaveURL(/\/liftoff\/debrief\?session=/);
  await page.getByLabel("Valid lap times").fill("61.2, 63.0, 60.8");
  await page.getByLabel("Result screenshot").setInputFiles({
    name: "result.png",
    mimeType: "image/png",
    buffer: Buffer.from("89504e470d0a1a0a73796e746865746963", "hex"),
  });
  await page.getByRole("button", { name: /Seal session/i }).click();
  await expect(page.getByText("Sealed evidence", { exact: false })).toBeVisible();
  expect((await new AxeBuilder({ page: page as never }).analyze()).violations).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
