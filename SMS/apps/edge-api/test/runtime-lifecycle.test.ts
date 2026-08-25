import { EventEmitter } from "node:events";
import { describe, expect, it, vi } from "vitest";
import { installGracefulShutdown } from "../src/runtime/lifecycle.js";

class FakeProcess extends EventEmitter {
  public exitCode: number | undefined;
}

describe("edge runtime lifecycle", () => {
  it("closes exactly once on SIGINT or SIGTERM and removes signal listeners", async () => {
    for (const signal of ["SIGINT", "SIGTERM"] as const) {
      const runtime = new FakeProcess();
      const close = vi.fn(async () => undefined);
      const logs: unknown[] = [];
      const lifecycle = installGracefulShutdown({ close }, runtime, (entry) => logs.push(entry));
      runtime.emit(signal);
      runtime.emit(signal);
      await lifecycle.closed;
      expect(close).toHaveBeenCalledTimes(1);
      expect(runtime.exitCode).toBe(0);
      expect(runtime.listenerCount("SIGINT")).toBe(0);
      expect(runtime.listenerCount("SIGTERM")).toBe(0);
      expect(logs).toEqual([{ event: "runtime.shutdown", signal }]);
    }
  });

  it("sets a failing exit code when graceful close fails without logging the secret error", async () => {
    const runtime = new FakeProcess();
    const logs: unknown[] = [];
    const lifecycle = installGracefulShutdown({ close: async () => { throw new Error("private shutdown secret"); } }, runtime, (entry) => logs.push(entry));
    runtime.emit("SIGTERM");
    await lifecycle.closed;
    expect(runtime.exitCode).toBe(1);
    expect(JSON.stringify(logs)).not.toContain("private shutdown secret");
    expect(logs).toEqual([{ event: "runtime.shutdown", signal: "SIGTERM" }, { event: "runtime.shutdown.failed", code: "SHUTDOWN_FAILED" }]);
  });
});
