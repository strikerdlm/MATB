import { test, expect, chromium } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fixture, SUITE } from "./openmatb-fixtures";

test.use({ viewport: null, deviceScaleFactor: async ({}, provide) => { await provide(undefined); } });

for (const locale of ["en", "es-419"] as const) {
  test(`actual 200 percent browser zoom (${locale})`, async ({}, info) => {
    test.skip(process.platform !== "linux" || !fs.existsSync("/usr/bin/Xvfb"), "Requires Linux Xvfb/XTest for real OS browser shortcuts");
    const display = 200 + process.pid % 20000;
    const displayName = `:${display}`;
    const xvfb = spawn("/usr/bin/Xvfb", [displayName, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"]);
    const browserEnv = { ...process.env, DISPLAY: displayName };
    let browser;
    try {
      await expect.poll(() => fs.existsSync(`/tmp/.X11-unix/X${display}`)).toBe(true);
      browser = await chromium.launch({ headless: false, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ?? "/opt/google/chrome/chrome",
        env: browserEnv, args: ["--no-sandbox", "--window-size=1366,900"] });
      const context = await browser.newContext({ viewport: null, baseURL: "http://127.0.0.1:3100" });
      const page = await context.newPage();
      const state = await fixture(page, locale);
      await page.goto("/openmatb/setup?purpose=practice");
      await expect(page.locator("#om-display")).toHaveValue("1");
      const before = await page.evaluate(() => ({ dpr: devicePixelRatio, width: innerWidth }));
      execFileSync("python3", [path.join(__dirname, "support/browser-zoom.py")], { env: browserEnv });
      await expect.poll(() => page.evaluate(() => devicePixelRatio)).toBe(before.dpr * 2);
      const after = await page.evaluate(() => ({ dpr: devicePixelRatio, width: innerWidth }));
      expect(after.width).toBeLessThanOrEqual(Math.ceil(before.width / 2));
      await info.attach("actual-browser-zoom", { contentType: "application/json", body: JSON.stringify({ before, after, zoom: "200%", method: "XTest browser shortcuts" }) });
      for (const [name, url, ready] of [
        ["preparation", "/openmatb/setup?purpose=practice", "#om-display"],
        ["questionnaire", `/openmatb/participant?session=${SUITE}`, "input[type=range]"],
        ["receipt", `/openmatb/session?session=${SUITE}`, "article"],
        ["evidence", "/evidence?purpose=all", "form[role=search]"],
      ]) {
        if (name === "receipt") state.current = { ...state.current, lifecycle: "COMPLETE", active_block: null, active_block_instance_id: null };
        await page.goto(url);
        await expect(page.locator(ready).first()).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        expect(await page.evaluate(() => devicePixelRatio)).toBe(before.dpr * 2);
        // Playwright's fullPage CSS clip crops an actual browser-zoom capture.
        // CDP contentSize is in display-independent pixels, matching this clip.
        const cdp = await context.newCDPSession(page);
        const metrics = await cdp.send("Page.getLayoutMetrics");
        const capture = await cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
          clip: { x: 0, y: 0, width: metrics.contentSize.width, height: metrics.contentSize.height, scale: 1 } });
        fs.writeFileSync(info.outputPath(`${name}-zoom-200.png`), Buffer.from(capture.data, "base64"));
        await cdp.detach();
      }
    } finally {
      await browser?.close();
      xvfb.kill("SIGTERM");
    }
  });
}
