import { readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const smsRoot = process.cwd();
const historical = join(smsRoot, "docs/release/history/0.1.0");

describe("release evidence lifecycle", () => {
  it("exposes independent CI, technical-release, and operational-readiness gates", async () => {
    const packageJson = JSON.parse(await readFile(join(smsRoot, "package.json"), "utf8"));
    expect(packageJson.scripts).toMatchObject({
      "verify:ci": "node scripts/verify-ci.mjs",
      "verify:technical-release": "node scripts/verify-technical-release.mjs",
      "verify:operational": "node scripts/verify-operational-readiness.mjs",
    });
  });

  it("keeps stale 0.1.0 evidence only in the historical, not-current archive", async () => {
    const manifest = JSON.parse(await readFile(join(historical, "release-manifest.json"), "utf8"));
    const archiveNotice = await readFile(join(historical, "README.md"), "utf8");
    expect(manifest.releaseId).toBe("fac-isr-sms@0.1.0");
    expect(archiveNotice).toContain("HISTORICAL — NOT CURRENT RELEASE EVIDENCE");
    await expect(stat(join(smsRoot, "docs/release/release-manifest.json"))).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("keeps the RC operational record blocked while technical readiness is evaluated separately", async () => {
    const record = JSON.parse(await readFile(join(smsRoot, "docs/release/operational-readiness-record.json"), "utf8"));
    expect(record.releaseId).toBe("fac-isr-sms@0.2.0-rc.1");
    expect(record.operationalReady).toBe(false);
    expect(record.qualification).toBe("blocked");
  });
});
