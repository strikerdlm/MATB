import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";

describe("edge startup failure boundary", () => {
  it("emits one sanitized JSON failure without stack traces or filesystem paths", () => {
    const result = spawnSync(process.execPath, ["scripts/start-edge.mjs"], {
      cwd: new URL("../../..", import.meta.url),
      env: { PATH: process.env.PATH ?? "" },
      encoding: "utf8",
    });
    expect(result.status).toBe(1);
    const lines = result.stderr.trim().split("\n");
    expect(lines).toHaveLength(1);
    expect(JSON.parse(lines[0]!)).toEqual({ event: "startup.failed", code: "STARTUP_FAILED" });
    expect(result.stderr).not.toMatch(/at file:|start-edge\.mjs:\d|\/root\/|SMS_DEPLOYMENT_MODE/);
  });
});
