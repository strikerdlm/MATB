export interface RuntimeSignalTarget {
  exitCode?: number;
  on(event: "SIGINT" | "SIGTERM", listener: () => void): unknown;
  removeListener(event: "SIGINT" | "SIGTERM", listener: () => void): unknown;
}

export interface ClosableRuntime {
  close(): Promise<unknown>;
}

export type RuntimeLogSink = (entry: Readonly<Record<string, unknown>>) => void;

export interface RuntimeResource {
  readonly name: string;
  readonly close: () => unknown | Promise<unknown>;
}

export async function closeRuntimeResources(resources: readonly RuntimeResource[]): Promise<void> {
  let failed = false;
  for (const resource of resources) {
    try {
      await resource.close();
    } catch {
      failed = true;
    }
  }
  if (failed) throw new Error("runtime resource cleanup failed");
}

export function installGracefulShutdown(
  runtime: ClosableRuntime,
  signals: RuntimeSignalTarget,
  log: RuntimeLogSink = () => undefined,
): { readonly closed: Promise<void>; dispose(): void } {
  let started = false;
  let resolveClosed!: () => void;
  const closed = new Promise<void>((resolve) => { resolveClosed = resolve; });
  const remove = () => {
    signals.removeListener("SIGINT", onSigint);
    signals.removeListener("SIGTERM", onSigterm);
  };
  const shutdown = (signal: "SIGINT" | "SIGTERM") => {
    if (started) return;
    started = true;
    log({ event: "runtime.shutdown", signal });
    void Promise.resolve().then(() => runtime.close()).then(() => {
      signals.exitCode = 0;
    }, () => {
      signals.exitCode = 1;
      log({ event: "runtime.shutdown.failed", code: "SHUTDOWN_FAILED" });
    }).finally(() => {
      remove();
      resolveClosed();
    });
  };
  const onSigint = () => shutdown("SIGINT");
  const onSigterm = () => shutdown("SIGTERM");
  signals.on("SIGINT", onSigint);
  signals.on("SIGTERM", onSigterm);
  return Object.freeze({ closed, dispose: remove });
}
