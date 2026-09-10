import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {approveStudyFixture,baseOccasion,post} from './study-fixtures';
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
  await primeTelemetry();

  const original=await baseOccasion(request);
  const configuration={liftoff_build:'fixture-build',track_id:'astra-neutral-time-trial-v1',drone_id:'astra-standard-quad-v1',flight_mode:'acro',camera_angle_deg:25,fov_deg:110,rates_profile:'astra-v1',controller_model:'research-rc',controller_firmware:'fixture-firmware',resolution:'1920x1080',refresh_rate_hz:120,graphics_preset:'medium',damage_enabled:false,battery_enabled:false,telemetry_profile:'liftoff-telemetry-all-v1'};
  const assignment=await approveStudyFixture(request,'P16',[{...original,visit_ordinal:16,key:'liftoff',instrument:'liftoff',config:{binding_id:'liftoff-telemetry-all-v1',input_mapping:'liftoff-telemetry-all-v1',configuration,scoring:'liftoff-current'}}],[{ordinal:1,code:'T0',scheduled_day:0},{ordinal:16,code:'CUSTOM16',scheduled_day:44}]);
  const task=await post(request,`/assessments/occasions/${assignment.occasions.liftoff}/attempts`,{execution_purpose:'study'});
  await page.goto(`/liftoff/setup?purpose=study&attempt=${task.id}`);
  await page.locator("#app-language").selectOption("en");
  await expect(page.getByText("Telemetry ready", { exact: false })).toBeVisible();
  expect((await new AxeBuilder({ page: page as never }).analyze()).violations).toEqual([]);
  await expect(page.getByLabel("Participant")).toHaveValue("P16");
  await expect(page.getByLabel("Visit")).toHaveValue("16");
  await page.getByRole("button", { name: /Prepare Liftoff session/i }).click();
  await expect(page).toHaveURL(/\/liftoff\/session\?session=/);
  const currentUrl = page.url();
  expect(currentUrl).not.toContain("secret");
  expect(await page.evaluate(() => Object.keys(sessionStorage).some((key) => key.startsWith("matb.liftoff.") && key.endsWith(".lease")))).toBe(true);
  await expect(page.getByRole("button", { name: /Start baseline/i })).toBeVisible();
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
  await page.getByLabel(/sleepiness.*1.*9/i).fill("3");
  for (const label of ["Mental demand", "Physical demand", "Temporal demand", "Performance", "Effort", "Frustration"]) await page.getByLabel(label, { exact: true }).fill("25");
  await page.getByRole("button", { name: /Seal session/i }).click();
  await expect(page.getByText("Sealed evidence", { exact: false })).toBeVisible();
  expect((await new AxeBuilder({ page: page as never }).analyze()).violations).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
