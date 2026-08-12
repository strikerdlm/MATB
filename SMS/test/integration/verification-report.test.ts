import { describe, expect, it } from "vitest";
import { buildVerificationReport } from "../../scripts/generate-verification-report.mjs";

const requiredCoverage = [
  "accessibility",
  "battery-reserve",
  "bilingual-equivalence",
  "concurrency-gate-separation",
  "data-separation",
  "dependency-invalidation",
  "geospatial-integrity",
  "golden-blocked-cases",
  "long-duration-performance",
  "multi-aircraft-performance",
  "no-c2",
  "normalized-rules-calculations",
  "offline-cold-start",
  "package-integrity",
  "racae-classes",
  "responsive-human-factors",
  "telemetry-degradation",
  "vfr-ifr",
  "visual-conditions",
] as const;

describe("verification matrix report contract", () => {
  it("maps every approved design area to executable, hash-locked evidence and an honest reviewer", async () => {
    const report = await buildVerificationReport(process.cwd(), { execute: false, write: false });

    expect(report.schemaVersion).toBe("1.0");
    expect(new Set(report.requirements.map((requirement) => requirement.coverage))).toEqual(new Set(requiredCoverage));
    expect(report.requirements.every((requirement) => requirement.command.trim() !== "")).toBe(true);
    expect(report.requirements.every((requirement) => ["not-run", "pass", "fail", "conditional"].includes(requirement.result))).toBe(true);
    expect(report.requirements.every((requirement) => requirement.artifacts.length > 0)).toBe(true);
    expect(report.requirements.every((requirement) => requirement.artifacts.every((artifact) => /^[a-f0-9]{64}$/.test(artifact.sha256)))).toBe(true);
    expect(report.requirements.every((requirement) => requirement.reviewer.type === "automated" && requirement.reviewer.id === "fac-isr-sms-ci")).toBe(true);
    expect(report.requirements.every((requirement) => typeof requirement.unresolvedLimitation === "string")).toBe(true);
    expect(report.operationalReady).toBe(false);
  });
});
