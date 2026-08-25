import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { validateCiRunSelection } from "../../scripts/validate-release-ci-run.mjs";
import { validateExpectedOperationalBlock } from "../../scripts/validate-operational-block.mjs";

const commit = "a".repeat(40);
const repository = "strikerdlm/MATB";
const workflow = { id: 731, path: ".github/workflows/sms-ci.yml", state: "active" };
const protectedMain = { name: "main", protected: true };
const smsRoot = process.cwd();
const trustedRun = {
  id: 90210,
  workflow_id: 731,
  path: ".github/workflows/sms-ci.yml@refs/heads/main",
  conclusion: "success",
  status: "completed",
  event: "push",
  head_branch: "main",
  head_sha: commit,
  repository: { full_name: repository },
  head_repository: { full_name: repository },
};

describe("release workflow trust policy", () => {
  it("accepts only a completed trusted-main push from the exact sms-ci workflow and commit", () => {
    expect(validateCiRunSelection(trustedRun, workflow, { expectedCommit: commit, expectedRepository: repository, requestedRunId: "90210", branch: protectedMain })).toBe(90210);

    for (const mutation of [
      { event: "pull_request" },
      { head_branch: "feature/untrusted" },
      { head_sha: "b".repeat(40) },
      { workflow_id: 999 },
      { conclusion: "failure" },
      { status: "in_progress" },
      { head_repository: { full_name: "fork/MATB" } },
      { path: ".github/workflows/other.yml@refs/heads/main" },
    ]) {
      expect(() => validateCiRunSelection({ ...trustedRun, ...mutation }, workflow, {
        expectedCommit: commit,
        expectedRepository: repository,
        requestedRunId: "90210",
        branch: protectedMain,
      })).toThrow();
    }
    expect(() => validateCiRunSelection(trustedRun, workflow, { expectedCommit: commit, expectedRepository: repository, requestedRunId: "9;echo unsafe", branch: protectedMain })).toThrow(/numeric/u);
    expect(() => validateCiRunSelection(trustedRun, workflow, { expectedCommit: commit, expectedRepository: repository, requestedRunId: "90210", branch: { name: "main", protected: false } })).toThrow(/protected/u);
  });

  it("accepts only the documented valid-but-blocked operational result and exit code", () => {
    const scopes = [
      "cybersecurity-deployment", "emergency-response", "human-factors-protocol",
      "official-geospatial-data", "operational-checklist", "racae-interpretation-translation",
      "research-separation", "risk-authority", "training-safety-promotion",
    ];
    const report = {
      ok: true,
      operationalReady: false,
      qualification: "blocked",
      pendingReviewScopes: scopes,
      violations: [],
      blockers: scopes.map((scope) => ({ code: "INSTITUTIONAL_REVIEW_PENDING", scope })),
    };
    expect(validateExpectedOperationalBlock(report, 1)).toEqual({ pendingReviewCount: 9 });
    expect(() => validateExpectedOperationalBlock(report, 2)).toThrow(/exit code/u);
    expect(() => validateExpectedOperationalBlock({ ...report, ok: false }, 1)).toThrow(/valid/u);
    expect(() => validateExpectedOperationalBlock({ ...report, pendingReviewScopes: scopes.slice(1) }, 1)).toThrow(/pending/u);
    expect(() => validateExpectedOperationalBlock({ ...report, operationalReady: true }, 1)).toThrow(/operationalReady/u);
  });

  it("keeps disconnected OCI commands aligned with Compose services and the released image reference", async () => {
    const packageJson = JSON.parse(await readFile(join(smsRoot, "package.json"), "utf8")) as { version: string };
    const compose = await readFile(join(smsRoot, "docker/compose.edge.yml"), "utf8");
    const guide = await readFile(join(smsRoot, "docs/operator-guide.md"), "utf8");
    const releasedImage = `fac-isr-sms:${packageJson.version}`;
    const servicesBlock = /^services:\n([\s\S]*?)^networks:/mu.exec(compose)?.[1] ?? "";
    const serviceNames = [...servicesBlock.matchAll(/^  ([a-z][a-z0-9_-]*):$/gmu)].map((match) => match[1]);
    const composeImages = [...compose.matchAll(/^\s+image: \$\{SMS_EDGE_IMAGE:-([^}]+)\}$/gmu)].map((match) => match[1]);

    expect(serviceNames).toEqual(["init", "edge"]);
    expect(composeImages).toEqual([releasedImage, releasedImage]);
    expect(guide).toContain(`export SMS_EDGE_IMAGE=${releasedImage}`);
    expect(guide).toContain("docker compose -f docker/compose.edge.yml up init");
    expect(guide).toContain("docker compose -f docker/compose.edge.yml up -d edge");
  });
});
