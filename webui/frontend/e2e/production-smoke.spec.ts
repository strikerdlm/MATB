import { test, expect } from "@playwright/test";

test("production pages reject framing and load without browser errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const route of ["/start", "/participants", "/station", "/mission/setup", "/study"]) {
    const response = await page.goto(route);
    expect(response?.status()).toBe(200);
    const headers = response!.headers();
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    await expect(page.locator("main")).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("invalid queued analysis is a readable validation error", async ({ page }) => {
  await page.goto("/study/analysis");
  const result = await page.evaluate(async () => {
    const config = await (await fetch("/api/runtime-config")).json();
    const backend = new URL(location.origin);
    backend.port = String(config.backend_port);
    const response = await fetch(`${backend.origin}/study/analyses`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{",
    });
    return { status: response.status, body: await response.json() };
  });
  expect(result.status).toBe(422);
  expect(result.body.detail.code).toBe("invalid_request");
});
