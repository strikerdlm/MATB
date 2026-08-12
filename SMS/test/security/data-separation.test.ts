import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { parseResearchEvent } from "../../packages/research/src/index.js";
import { buildServer, type EdgeServer } from "../../apps/edge-api/src/server.js";
import { verifyDataSeparation } from "../../scripts/verify-data-separation.mjs";

const smsRoot = process.cwd();
const temporaryDirectories: string[] = [];
let app: EdgeServer | undefined;

afterEach(async () => {
  await app?.close();
  app = undefined;
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("operational and research data separation", () => {
  it("rejects a research-domain payload before operational storage", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });

    const response = await app.inject({
      method: "POST",
      url: "/api/missions",
      payload: {
        dataDomain: "research",
        protocolId: "PROTOCOL-1",
        ethicsApprovalId: "ETHICS-1",
        participantCode: "P-001",
        nonDispatchable: true,
      },
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ error: "RESEARCH_DATA_DOMAIN_FORBIDDEN" });
    expect(app.edgeDatabase.tableNames().every((name) => !/research|participant|protocol|consent/i.test(name))).toBe(true);
  });

  it("rejects operational identity at the research contract", () => {
    expect(() => parseResearchEvent({
      eventId: "EVENT-1",
      sessionId: "SESSION-1",
      occurredAtUtc: "2026-08-10T15:00:01.000Z",
      sequence: 0,
      type: "matb.response",
      dataDomain: "research",
      nonDispatchable: true,
      payload: { response: 1 },
      quality: "valid",
      operationalUserId: "OPERATOR-1",
    })).toThrow(/separation/i);
  });

  it("proves package, schema, mount, and runtime boundaries", async () => {
    const report = await verifyDataSeparation(smsRoot, { runtime: true });

    expect(report.ok, JSON.stringify(report.violations, null, 2)).toBe(true);
    expect(report.violations).toEqual([]);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "workspace-dependencies", status: "pass" }));
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "operational-ingress", status: "pass" }));
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "database-key-separation", status: "pass" }));
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "encrypted-operational-path", status: "pass" }));
  });

  it("detects an operational dependency on the research package", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-isr-data-boundary-fixture-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "apps/edge-api"), { recursive: true });
    await mkdir(join(root, "packages/research"), { recursive: true });
    await mkdir(join(root, "docker"), { recursive: true });
    await writeFile(join(root, "apps/edge-api/package.json"), JSON.stringify({
      name: "@fac-isr/edge-api",
      dependencies: { "@fac-isr/research": "0.1.0" },
    }), "utf8");
    await writeFile(join(root, "packages/research/package.json"), JSON.stringify({
      name: "@fac-isr/research",
      dependencies: {},
    }), "utf8");
    await writeFile(join(root, "docker/data-domain-policy.json"), JSON.stringify({
      schemaVersion: "1.0",
      domains: {
        operational: { databasePathEnv: "SHARED_DATABASE", hostDataDirectoryEnv: "OPERATIONAL_DATA", encryptionKeyIdEnv: "SHARED_KEY" },
        research: { databasePathEnv: "SHARED_DATABASE", hostDataDirectoryEnv: "RESEARCH_DATA", encryptionKeyIdEnv: "SHARED_KEY" },
      },
      allowedFlows: [{ from: "research", to: "operational", payload: "approved-deidentified-aggregate-review", automatic: false }],
    }), "utf8");

    const report = await verifyDataSeparation(root, { runtime: false });

    expect(report.ok).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ id: "workspace-dependencies" }));
    expect(report.violations).toContainEqual(expect.objectContaining({ id: "database-key-separation" }));
  });
});
