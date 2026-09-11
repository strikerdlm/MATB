import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { approveStudyFixture, baseOccasion, post } from "./study-fixtures";
import { studyParticipantId } from "./study-participant-id";

for (const locale of ["en", "es-419"] as const) {
  test(`study backup keyboard and empty restore (${locale})`, async ({
    page,
    request,
  }, info) => {
    test.setTimeout(120000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const participant = studyParticipantId("restore", locale, info);
    const created = await request.post("http://127.0.0.1:8000/participants", {
      data: { id: participant, enrollment_date: "2026-09-10" },
    });
    expect(created.status(), await created.text()).toBe(201);
    await approveStudyFixture(request, participant, [
      { ...(await baseOccasion(request)), key: "baseline" },
    ]);
    await post(request, "/station/maintenance", {
      actor: "Dr Browser Restore",
      reason: "Empty synthetic restore",
      enabled: true,
    });
    try {
      await page.goto("/study/restore");
      await page.locator("#app-language").selectOption(locale);
      const english = locale === "en";
      const researcher = page.getByLabel(
        english ? "Researcher" : "Investigador",
        { exact: true },
      );
      const reason = page.getByLabel(english ? "Reason" : "Motivo", {
        exact: true,
      });
      const download = page.getByRole("button", {
        name: english
          ? "Download verified backup"
          : "Descargar copia verificada",
        exact: true,
      });
      await expect(download).toBeDisabled();
      await researcher.fill("Dr Browser Restore");
      await researcher.press("Tab");
      await expect(reason).toBeFocused();
      await reason.fill("Software-only empty workspace restoration");
      await reason.press("Tab");
      await expect(download).toBeFocused();
      for (const viewport of [
        { width: 1280, height: 720 },
        { width: 1366, height: 768 },
        { width: 1920, height: 1080 },
        { width: 640, height: 900 },
      ]) {
        await page.setViewportSize(viewport);
        await expect(download).toBeEnabled();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        await page.screenshot({
          path: info.outputPath(`restore-${viewport.width}.png`),
          fullPage: true,
        });
      }
      const [archive] = await Promise.all([
        page.waitForEvent("download"),
        (async () => {
          const response = page.waitForResponse(
            (r) =>
              r.url().endsWith("/station/backups") &&
              r.request().method() === "POST",
          );
          await download.press("Enter");
          const result = await response;
          expect(
            result.status(),
            result.ok() ? undefined : await result.text(),
          ).toBe(200);
        })(),
      ]);
      const archivePath = info.outputPath("whole-study.zip");
      await archive.saveAs(archivePath);
      await expect(
        page.getByRole("status").filter({
          hasText: english ? "Verified backup" : "Copia verificada",
        }),
      ).toBeVisible();
      const repository = path.resolve(__dirname, "../../..");
      const result = execFileSync(
        process.env.MATB_PYTHON ?? "python",
        [
          path.join(repository, "tools/study_workspace.py"),
          "restore",
          archivePath,
          info.outputPath("restored study ñ"),
          "--study-id",
          "researcher-study",
        ],
        { cwd: repository, encoding: "utf-8", timeout: 60000 },
      );
      const report = JSON.parse(result);
      expect(report.status).toBe("restored_in_maintenance");
      expect(report.files_verified).toBeGreaterThan(0);
      await info.attach("restoration-report", {
        body: result,
        contentType: "application/json",
      });
      expect(errors).toEqual([]);
    } finally {
      await post(request, "/station/maintenance", {
        actor: "Dr Browser Restore",
        reason: "Rehearsal complete",
        enabled: false,
      });
    }
  });
}
