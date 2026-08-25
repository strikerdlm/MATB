import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";
import * as productionTelemetry from "../src/index.js";

const forbidden = ["ReplayGateway", "ReplayTelemetryAdapter", "ReadOnlyTelemetryAdapterFixture", "replayFixture", "signReplayFixture"];

describe("production telemetry package boundary", () => {
  it("does not export or compile replay, fixture, or fixture-signing helpers", () => {
    for (const name of forbidden) expect(productionTelemetry).not.toHaveProperty(name);
    const dist = new URL("../dist/", import.meta.url);
    const files = readdirSync(dist).filter((file) => file.endsWith(".js") || file.endsWith(".d.ts"));
    const compiled = files.map((file) => readFileSync(new URL(file, dist), "utf8")).join("\n");
    for (const name of forbidden) expect(compiled).not.toContain(name);
    expect(files).not.toEqual(expect.arrayContaining(["replay.js", "replay.d.ts"]));
  });
});
