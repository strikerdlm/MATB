import { isIP } from "node:net";
import { resolve } from "node:path";

export type InternetMode = "disabled";

export interface TlsPaths {
  readonly certPath: string;
  readonly keyPath: string;
}

export interface EdgeConfigInput {
  readonly bindAddress?: string;
  readonly port?: number;
  readonly databaseUrl?: string;
  readonly packageDirectory?: string;
  readonly lockTimeoutMs?: number;
  readonly internet?: InternetMode | string;
  readonly tls?: Partial<TlsPaths>;
}

export interface EdgeConfig {
  readonly bindAddress: string;
  readonly port: number;
  readonly databaseUrl: string;
  readonly packageDirectory: string;
  readonly lockTimeoutMs: number;
  readonly internet: InternetMode;
  readonly tls?: TlsPaths;
}

const DEFAULT_PACKAGE_DIRECTORY = "./data/packages";

function assertNonEmptyString(value: string | undefined, field: string): string {
  if (typeof value !== "string" || value.trim().length === 0 || value.includes("\0")) {
    throw new Error(`${field} must be a non-empty path`);
  }
  return value;
}

function normalizePath(value: string | undefined, field: string): string {
  return resolve(assertNonEmptyString(value, field));
}

function validateBindAddress(value: string): string {
  if (value !== "localhost" && isIP(value) === 0) {
    throw new Error("bindAddress must be localhost or a valid IP address");
  }
  return value;
}

function validatePort(value: number): number {
  if (!Number.isInteger(value) || value < 0 || value > 65_535) {
    throw new Error("port must be an integer between 0 and 65535");
  }
  return value;
}

function validateLockTimeout(value: number): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error("lockTimeoutMs must be a positive integer");
  }
  return value;
}

function validateTls(tls: Partial<TlsPaths> | undefined): TlsPaths | undefined {
  if (tls === undefined) return undefined;
  const certPath = tls.certPath;
  const keyPath = tls.keyPath;
  if ((certPath === undefined) !== (keyPath === undefined)) {
    throw new Error("tls requires both certPath and keyPath");
  }
  if (certPath === undefined || keyPath === undefined) return undefined;
  return Object.freeze({
    certPath: normalizePath(certPath, "tls.certPath"),
    keyPath: normalizePath(keyPath, "tls.keyPath"),
  });
}

export function createConfig(input: EdgeConfigInput = {}): EdgeConfig {
  const bindAddress = validateBindAddress(input.bindAddress ?? "127.0.0.1");
  const port = validatePort(input.port ?? 0);
  const databaseUrl = input.databaseUrl === ":memory:"
    ? ":memory:"
    : normalizePath(input.databaseUrl ?? "./data/edge.sqlite", "databaseUrl");
  const packageDirectory = normalizePath(
    input.packageDirectory ?? DEFAULT_PACKAGE_DIRECTORY,
    "packageDirectory",
  );
  const lockTimeoutMs = validateLockTimeout(input.lockTimeoutMs ?? 5_000);
  const internet = input.internet ?? "disabled";
  if (internet !== "disabled") {
    throw new Error("internet must be disabled for the edge runtime");
  }

  return Object.freeze({
    bindAddress,
    port,
    databaseUrl,
    packageDirectory,
    lockTimeoutMs,
    internet: "disabled" as const,
    tls: validateTls(input.tls),
  });
}
