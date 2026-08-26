import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { scanNoC2 } from "../../scripts/verify-no-c2.mjs";

const smsRoot = process.cwd();
const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("no-C2 static and runtime boundary", () => {
  it("finds no command-looking route, adapter method, event, or outbound runtime transport", async () => {
    const result = await scanNoC2(smsRoot, { runtime: true });

    expect(result.forbidden, JSON.stringify(result.forbidden, null, 2)).toEqual([]);
    expect(result.routes).toContainEqual(expect.objectContaining({ method: "POST", path: "/api/missions" }));
    expect(result.routes).toContainEqual(expect.objectContaining({ method: "GET", path: "/api/revisions/:revisionId/telemetry/stream" }));
    expect(result.adapters).toContainEqual(expect.objectContaining({ name: "ReadOnlyTelemetryAdapter" }));
    expect(result.runtimeProbes.every((probe) => probe.status === 404)).toBe(true);
  });

  it("detects command-shaped route and adapter additions", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-isr-no-c2-fixture-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "apps/edge-api/src/routes"), { recursive: true });
    await mkdir(join(root, "packages/telemetry/src"), { recursive: true });
    await writeFile(join(root, "apps/edge-api/src/routes/control.ts"), [
      "export function register(app: { post(path: string, handler: () => void): void }) {",
      "  app.post('/api/arm', () => undefined);",
      "}",
      "",
    ].join("\n"), "utf8");
    await writeFile(join(root, "packages/telemetry/src/control.ts"), [
      "export interface AircraftAdapter {",
      "  sendCommand(value: string): Promise<void>;",
      "}",
      "",
    ].join("\n"), "utf8");

    const result = await scanNoC2(root, { runtime: false });

    expect(result.forbidden).toContainEqual(expect.objectContaining({ id: "command-route" }));
    expect(result.forbidden).toContainEqual(expect.objectContaining({ id: "command-identifier" }));
  });

  it("detects command messages and unapproved outbound runtime clients", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-isr-no-c2-network-fixture-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "apps/edge-api/src"), { recursive: true });
    await writeFile(join(root, "apps/edge-api/src/outbound.ts"), [
      "import { request } from 'node:https';",
      "export const messageType = 'gcs-command';",
      "export const outboundClient = request;",
      "",
    ].join("\n"), "utf8");

    const result = await scanNoC2(root, { runtime: false });

    expect(result.forbidden).toContainEqual(expect.objectContaining({ id: "command-message" }));
    expect(result.forbidden).toContainEqual(expect.objectContaining({ id: "network-client" }));
  });

  it("does not allow an external fetch merely because it is placed in the console client", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-isr-no-c2-console-network-fixture-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "apps/console/src/api"), { recursive: true });
    await writeFile(join(root, "apps/console/src/api/client.ts"), "export const leak = fetch('https://example.invalid/mission');\n", "utf8");

    const result = await scanNoC2(root, { runtime: false });

    expect(result.forbidden).toContainEqual(expect.objectContaining({ id: "network-client" }));
  });

  it("does not approve an arbitrary fetch merely because its argument is named path", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-isr-no-c2-console-path-fixture-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "apps/console/src/api"), { recursive: true });
    await writeFile(join(root, "apps/console/src/api/client.ts"), [
      "export function leak(path: string) {",
      "  return fetch(path);",
      "}",
      "",
    ].join("\n"), "utf8");

    const result = await scanNoC2(root, { runtime: false });

    expect(result.forbidden).toContainEqual(expect.objectContaining({ id: "network-client" }));
  });

  it("documents read-only route, recovery, and C2-link status terms without treating them as commands", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-isr-read-only-fixture-"));
    temporaryDirectories.push(root);
    await mkdir(join(root, "packages/telemetry/src"), { recursive: true });
    await writeFile(join(root, "packages/telemetry/src/status.ts"), [
      "export interface ReadOnlyStatus {",
      "  routeDeviationM: number;",
      "  recoveryStatus: 'available' | 'degraded';",
      "  c2Link: 'normal' | 'degraded' | 'lost';",
      "}",
      "",
    ].join("\n"), "utf8");

    const result = await scanNoC2(root, { runtime: false });

    expect(result.forbidden).toEqual([]);
    expect(result.approvedReadOnlyTerms).toEqual(expect.arrayContaining(["routeDeviationM", "recoveryStatus", "c2Link"]));
  });
});
