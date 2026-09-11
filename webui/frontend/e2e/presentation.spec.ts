import { writeFileSync } from "node:fs";
import { test, expect, type Locator, type Page } from "@playwright/test";
const api = "http://127.0.0.1:8000";
async function settleInteractiveButton(page: Page, button: Locator) {
  await button.scrollIntoViewIfNeeded();
  await expect(button).toBeInViewport();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() =>
          requestAnimationFrame(() => resolve()),
        );
      }),
  );
}
async function activateInteractiveButton({
  page,
  button,
  completed,
  pending,
  timeout = 15000,
}: {
  page: Page;
  button: Locator;
  completed: () => Promise<boolean>;
  pending: () => Promise<boolean>;
  timeout?: number;
}) {
  const deadline = Date.now() + timeout;
  const remainingTimeout = () => Math.max(0, deadline - Date.now());
  const completedSoon = async (waitMs = 2000) => {
    const budget = Math.min(remainingTimeout(), waitMs);
    if (budget <= 0) return false;
    try {
      await expect.poll(completed, { timeout: budget }).toBe(true);
      return true;
    } catch {
      return false;
    }
  };
  await settleInteractiveButton(page, button);
  try {
    await button.click({ timeout: remainingTimeout() });
  } catch (error) {
    if (await completed()) return;
    throw error;
  }
  if (await completed()) return;
  if (await completedSoon()) return;
  if (!(await pending())) {
    await expect.poll(completed, { timeout: remainingTimeout() }).toBe(true);
    return;
  }
  await settleInteractiveButton(page, button);
  await button.focus();
  await button.press("Space", { timeout: remainingTimeout() });
  await expect.poll(completed, { timeout: remainingTimeout() }).toBe(true);
}
for (const block of ["LOW", "MEDIUM", "HIGH"] as const)
  test(`offline 3D ${block}: readiness, camera, pause and technical fallback`, async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(90000);
    page.setDefaultTimeout(8000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.route("https://**/*", (route) => route.abort());
    const scenes = await (await request.get(`${api}/simulation/scenes`)).json();
    expect(scenes.length).toBeGreaterThan(0);
    const scene = scenes[0];
    const preparedResponse = await request.post(
      `${api}/simulation/technical-sessions`,
      {
        data: {
          execution_purpose: "practice",
          scenario_id: "presentation_area_search",
          block_id: block,
          locale: "en",
          presentation: {
            version: 1,
            blocks: { [block]: "3d" },
            scene_id: scene.id,
            scene_sha256: scene.sha256,
            camera: "overview",
            ...(process.env.MATB_E2E_TRAFFIC_FIXTURE === "1"
              ? { traffic: { mode: "live", provider: "adsb.lol" } }
              : {}),
          },
        },
      },
    );
    expect(preparedResponse.status()).toBe(201);
    const prepared = await preparedResponse.json();
    const headers = { "X-Simulation-Controller": prepared.controller_lease };
    try {
      const premature = await request.post(
        `${api}/simulation/sessions/${prepared.id}/start`,
        { headers, data: { block_id: block } },
      );
      expect(premature.status()).toBe(409);
      await page.addInitScript(
        ({ id, lease }) =>
          sessionStorage.setItem(`matb.simulation.${id}.lease`, lease),
        { id: prepared.id, lease: prepared.controller_lease },
      );
      const ready = page.waitForResponse(
        (response) =>
          response.url().endsWith("/presentation") &&
          response.request().postDataJSON()?.kind === "ready" &&
          response.status() === 204,
      );
      await page.goto(`/mission?session=${prepared.id}&metrics=1`);
      await ready;
      await expect(
        page.getByTestId("mission-three-view").locator("canvas"),
      ).toBeVisible();
      await page.getByRole("button", { name: /start block/i }).click();
      await expect
        .poll(
          async () =>
            (
              await (
                await request.get(`${api}/simulation/sessions/${prepared.id}`)
              ).json()
            ).lifecycle,
        )
        .toBe("RUNNING");
      await expect(
        page.getByTestId("mission-three-view").locator("canvas"),
      ).toBeVisible();
      // Exercise live controls before visual capture: software rasterizers can
      // starve input while full-page captures resize/repaint the WebGL surface.
      if (process.env.MATB_E2E_TRAFFIC_FIXTURE === "1") {
        const observedTraffic = page.getByRole("region", {
          name: "Observed traffic",
        });
        await expect(observedTraffic).toContainText("FIXTURE01");
        const traffic = observedTraffic.getByRole("button", {
          name: /FIXTURE01/,
        });
        const selectionStarted = Date.now();
        let phaseStarted = selectionStarted;
        const selectionTiming = {
          phase: "scroll",
          scrollMs: 0,
          clickMs: 0,
          assertionMs: 0,
          completed: false,
        };
        try {
          // Scrolling can resize/repaint the software-rendered WebGL surface.
          // Settle it before spending the click's input/completion budget.
          await settleInteractiveButton(page, traffic);
          selectionTiming.scrollMs = Date.now() - phaseStarted;
          selectionTiming.phase = "click";
          phaseStarted = Date.now();
          await activateInteractiveButton({
            page,
            button: traffic,
            completed: async () =>
              (await traffic.getAttribute("aria-pressed")) === "true"
              && ((await observedTraffic.textContent()) ?? "").includes(
                "a12345",
              ),
            pending: async () =>
              (await traffic.getAttribute("aria-pressed")) !== "true",
          });
          selectionTiming.clickMs = Date.now() - phaseStarted;
          selectionTiming.phase = "assertions";
          phaseStarted = Date.now();
          await expect(traffic).toHaveAttribute("aria-pressed", "true");
          await expect(observedTraffic).toContainText("a12345");
          selectionTiming.assertionMs = Date.now() - phaseStarted;
          selectionTiming.completed = true;
        } finally {
          writeFileSync(
            testInfo.outputPath("traffic-selection-timing.json"),
            JSON.stringify(
              {
                block,
                ...selectionTiming,
                phaseElapsedMs: Date.now() - phaseStarted,
                totalMs: Date.now() - selectionStarted,
                clickTimeoutMs: 15000,
                physicalTimingQualified: false,
              },
              null,
              2,
            ),
          );
        }
      }
      await page.screenshot({
        path: testInfo.outputPath(`${block}-overview.png`),
        fullPage: false,
      });
      await page
        .getByRole("combobox", { name: "Camera", exact: true })
        .selectOption("follow");
      await page.screenshot({
        path: testInfo.outputPath(`${block}-follow.png`),
        fullPage: false,
      });
      await page
        .getByRole("combobox", { name: "Camera", exact: true })
        .selectOption("drone");
      await page.screenshot({
        path: testInfo.outputPath(`${block}-drone.png`),
        fullPage: false,
      });
      await page
        .getByRole("combobox", { name: "Camera", exact: true })
        .selectOption("overview");
      const state = await (
        await request.get(`${api}/simulation/sessions/${prepared.id}/state`)
      ).json();
      expect(Object.keys(state.aircraft)).toHaveLength(
        { LOW: 2, MEDIUM: 4, HIGH: 8 }[block],
      );
      await page.waitForTimeout(5000); // Intentional bounded render sampling, after initial shader warmup.
      const metrics = await page.evaluate(() =>
        Reflect.get(window, "__matbPresentationMetrics")?.(),
      );
      expect(metrics).toBeTruthy();
      writeFileSync(
        testInfo.outputPath("renderer-metrics.json"),
        JSON.stringify(
          {
            block,
            aircraft: Object.keys(state.aircraft).length,
            viewport: page.viewportSize(),
            browser: page.context().browser()?.version(),
            ...metrics,
          },
          null,
          2,
        ),
      );
      await testInfo.attach("renderer-metrics", {
        path: testInfo.outputPath("renderer-metrics.json"),
        contentType: "application/json",
      });
      await page
        .getByRole("combobox", { name: "Presentation", exact: true })
        .selectOption("2d");
      await expect(page.getByTestId("map-root")).toBeVisible();
      await page
        .getByRole("combobox", { name: "Presentation", exact: true })
        .selectOption("3d");
      await expect(
        page.getByRole("combobox", { name: "Camera", exact: true }),
      ).toBeEnabled();
      const rebuilt = await page.evaluate(() =>
        Reflect.get(window, "__matbPresentationMetrics")?.(),
      );
      expect(rebuilt.memory.geometries).toBeLessThanOrEqual(
        metrics.memory.geometries + 2,
      );
      const lifecycle = async () =>
        (
          await (
            await request.get(`${api}/simulation/sessions/${prepared.id}`)
          ).json()
        ).lifecycle;
      await activateInteractiveButton({
        page,
        button: page.getByRole("button", { name: /pause/i, exact: false })
          .first(),
        completed: async () => (await lifecycle()) === "PAUSED",
        pending: async () => false,
      });
      await expect
        .poll(lifecycle)
        .toBe("PAUSED");
      await expect(
        page.getByRole("combobox", { name: "Camera", exact: true }),
      ).toBeDisabled();
      await page.setViewportSize({ width: 390, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(390);
      await page.screenshot({
        path: testInfo.outputPath(`${block}-mobile.png`),
        fullPage: true,
      });
      expect(errors).toEqual([]);
    } finally {
      await request
        .post(`${api}/simulation/sessions/${prepared.id}/finish`, {
          headers,
          data: { disposition: "abort" },
        })
        .catch(() => {});
    }
  });

test("corrupt offline imagery cannot satisfy readiness", async ({
  page,
  request,
}) => {
  const scene = (
    await (await request.get(`${api}/simulation/scenes`)).json()
  )[0];
  const prepared = await (
    await request.post(`${api}/simulation/technical-sessions`, {
      data: {
        execution_purpose: "practice",
        scenario_id: "presentation_area_search",
        block_id: "LOW",
        locale: "en",
        presentation: {
          version: 1,
          blocks: { LOW: "3d" },
          scene_id: scene.id,
          scene_sha256: scene.sha256,
          camera: "overview",
        },
      },
    })
  ).json();
  const headers = { "X-Simulation-Controller": prepared.controller_lease };
  try {
    await page.addInitScript(
      ({ id, lease }) =>
        sessionStorage.setItem(`matb.simulation.${id}.lease`, lease),
      { id: prepared.id, lease: prepared.controller_lease },
    );
    await page.route("**/scenes/**/imagery.png", (route) =>
      route.fulfill({ status: 200, contentType: "image/png", body: "corrupt" }),
    );
    await page.goto(`/mission?session=${prepared.id}&metrics=1`);
    await expect(
      page.getByRole("alert").filter({ hasText: /checksum mismatch/ }),
    ).toBeVisible();
    expect(
      (
        await request.post(`${api}/simulation/sessions/${prepared.id}/start`, {
          headers,
          data: { block_id: "LOW" },
        })
      ).status(),
    ).toBe(409);
  } finally {
    await request
      .post(`${api}/simulation/sessions/${prepared.id}/finish`, {
        headers,
        data: { disposition: "abort" },
      })
      .catch(() => {});
  }
});

for (const version of [1, 2] as const)
  test(`3D SAGAT concealment and sealed public replay v${version}`, async ({
    page,
    request,
  }, testInfo) => {
    const { visibleProbe, resolveVisibleProbe } = await import("./fixtures");
    const acceptedCommands: string[] = [];
    page.on("response", (response) => {
      if (response.url().endsWith("/commands") && response.status() === 200) {
        acceptedCommands.push(response.request().postDataJSON()?.kind);
      }
    });
    const scene = (
      await (await request.get(`${api}/simulation/scenes`)).json()
    )[0];
    const response = await request.post(
      `${api}/simulation/technical-sessions`,
      {
        data: {
          execution_purpose: "practice",
          scenario_id: "e2e_area_search",
          block_id: "LOW",
          locale: "en",
          presentation: {
            version,
            controls: {
              smooth_camera: version === 2,
              contact_cycling: version === 2,
              adjustable_layers: version === 2,
            },
            blocks: { LOW: "3d" },
            scene_id: scene.id,
            scene_sha256: scene.sha256,
            camera: "overview",
            ...(process.env.MATB_E2E_TRAFFIC_FIXTURE === "1"
              ? { traffic: { mode: "live", provider: "adsb.lol" } }
              : {}),
          },
        },
      },
    );
    expect(response.status()).toBe(201);
    const prepared = await response.json();
    const headers = { "X-Simulation-Controller": prepared.controller_lease };
    try {
      await page.addInitScript(
        ({ id, lease }) =>
          sessionStorage.setItem(`matb.simulation.${id}.lease`, lease),
        { id: prepared.id, lease: prepared.controller_lease },
      );
      const ready = page.waitForResponse(
        (response) =>
          response.url().endsWith("/presentation") &&
          response.request().postDataJSON()?.kind === "ready" &&
          response.status() === 204,
      );
      await page.goto(`/mission?session=${prepared.id}`);
      await ready;
      await page.getByRole("button", { name: /start block/i }).click();
      let sawSagat = false,
        completed = false;
      const deadline = Date.now() + 90000;
      while (Date.now() < deadline) {
        const probe = await visibleProbe(page);
        if (probe === "SAGAT") {
          sawSagat = true;
          await expect(page.getByTestId("mission-three-view")).toHaveCount(0);
          await expect(
            page.getByRole("button", { name: /assign sector/i }),
          ).toHaveCount(0);
        }
        if (probe) {
          const resolved = await resolveVisibleProbe(page);
          if (resolved === "SAGAT") sawSagat = true;
          if (resolved === "POST_BLOCK") {
            completed = true;
            break;
          }
        } else await page.waitForTimeout(100);
      }
      if (!sawSagat) {
        const protocol = await (
          await request.get(`${api}/simulation/sessions/${prepared.id}`)
        ).json();
        await testInfo.attach("protocol-state", {
          body: JSON.stringify(protocol),
          contentType: "application/json",
        });
      }
      expect(sawSagat).toBe(true);
      expect(acceptedCommands).toContain("SUBMIT_SAGAT");
      expect(completed).toBe(true);
      const finished = await request.post(
        `${api}/simulation/sessions/${prepared.id}/finish`,
        { headers, data: { disposition: "complete" } },
      );
      expect(finished.status()).toBe(200);
      const debrief = await (
        await request.get(`${api}/simulation/sessions/${prepared.id}/debrief`)
      ).json();
      expect(debrief.deterministic_replay_verified).toBe(true);
      expect(debrief.frames.length).toBeGreaterThan(5);
      expect(debrief.presentation.scene_sha256).toBe(scene.sha256);
      if (process.env.MATB_E2E_TRAFFIC_FIXTURE === "1") {
        expect(debrief.traffic_frames.length).toBeGreaterThan(1);
        expect(
          (
            await request.post(`${api}/geography/captures/${prepared.id}`, {
              headers: { "X-Simulation-Controller": "wrong" },
              data: { title: "Denied" },
            })
          ).status(),
        ).toBe(403);
        const captured = await request.post(
          `${api}/geography/captures/${prepared.id}`,
          { headers, data: { title: "Synthetic acceptance fixture" } },
        );
        expect(captured.status()).toBe(201);
        const recording = await captured.json();
        expect(recording.sha256).toMatch(/^[a-f0-9]{64}$/);
        expect(
          (
            await (await request.get(`${api}/geography/recordings`)).json()
          ).some((r: { id: string }) => r.id === recording.id),
        ).toBe(true);
      }
      await page.goto(`/mission/debrief?session=${prepared.id}`);
      const slider = page.getByRole("slider", { name: /replay time/i });
      await expect(slider).toBeVisible();
      await slider.focus();
      await slider.press("End");
      await expect(
        page.getByTestId("mission-three-view").locator("canvas"),
      ).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("3d-replay.png"),
        fullPage: true,
      });
    } finally {
      await request
        .post(`${api}/simulation/sessions/${prepared.id}/finish`, {
          headers,
          data: { disposition: "abort" },
        })
        .catch(() => {});
    }
  });
