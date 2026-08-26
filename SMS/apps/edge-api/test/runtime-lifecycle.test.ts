import { EventEmitter } from "node:events";
import { describe, expect, it, vi } from "vitest";
import { closeRuntimeResources, installGracefulShutdown } from "../src/runtime/lifecycle.js";

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

  it("keeps guarded signal handlers installed until asynchronous shutdown settles", async () => {
    const runtime = new FakeProcess();
    let release!: () => void;
    const close = vi.fn(() => new Promise<void>((resolve) => { release = resolve; }));
    const lifecycle = installGracefulShutdown({ close }, runtime);
    runtime.emit("SIGINT");
    await Promise.resolve();
    expect(runtime.listenerCount("SIGINT")).toBe(1);
    expect(runtime.listenerCount("SIGTERM")).toBe(1);
    runtime.emit("SIGINT");
    runtime.emit("SIGTERM");
    expect(close).toHaveBeenCalledTimes(1);
    release();
    await lifecycle.closed;
    expect(runtime.listenerCount("SIGINT")).toBe(0);
    expect(runtime.listenerCount("SIGTERM")).toBe(0);
  });

  it("attempts every runtime cleanup even when earlier resources fail", async () => {
    const calls: string[] = [];
    await expect(closeRuntimeResources([
      { name: "telemetry", close: () => { calls.push("telemetry"); throw new Error("telemetry secret"); } },
      { name: "timer", close: () => { calls.push("timer"); } },
      { name: "lease", close: () => { calls.push("lease"); throw new Error("lease secret"); } },
      { name: "database", close: () => { calls.push("database"); } },
      { name: "maintenance-lock", close: () => { calls.push("maintenance-lock"); } },
    ])).rejects.toThrow("runtime resource cleanup failed");
    expect(calls).toEqual(["telemetry", "timer", "lease", "database", "maintenance-lock"]);
  });
});
