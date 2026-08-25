export interface RuntimeSignalTarget {
  exitCode?: number;
  once(event: "SIGINT" | "SIGTERM", listener: () => void): unknown;
  removeListener(event: "SIGINT" | "SIGTERM", listener: () => void): unknown;
}

export interface ClosableRuntime {
  close(): Promise<unknown>;
}

export type RuntimeLogSink = (entry: Readonly<Record<string, unknown>>) => void;

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
    remove();
    log({ event: "runtime.shutdown", signal });
    void runtime.close().then(() => {
      signals.exitCode = 0;
    }, () => {
      signals.exitCode = 1;
      log({ event: "runtime.shutdown.failed", code: "SHUTDOWN_FAILED" });
    }).finally(resolveClosed);
  };
  const onSigint = () => shutdown("SIGINT");
  const onSigterm = () => shutdown("SIGTERM");
  signals.once("SIGINT", onSigint);
  signals.once("SIGTERM", onSigterm);
  return Object.freeze({ closed, dispose: remove });
}
