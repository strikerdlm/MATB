import { isIP } from "node:net";
import { resolvePortableRuntimePath } from "./runtime/paths.js";

export type InternetMode = "disabled";
export type DeploymentMode = "test" | "standalone" | "tactical";

export interface TlsPathsInput {
  readonly certPath: string;
  readonly keyPath: string;
  readonly clientCaPath?: string;
}

export interface TlsPaths extends TlsPathsInput {
  readonly requireClientCertificate: boolean;
  readonly rejectUnauthorizedClients: boolean;
}

export interface TelemetryAdapterCertificateInput {
  readonly fingerprintSha256: string;
  readonly adapterId: string;
  readonly aircraftIds: readonly string[];
}

export interface TelemetryAdapterCertificate {
  readonly fingerprintSha256: string;
  readonly adapterId: string;
  readonly aircraftIds: readonly string[];
}

export interface EdgeConfigInput {
  readonly deploymentMode?: DeploymentMode;
  readonly bindAddress?: string;
  readonly port?: number;
  readonly configDirectory?: string;
  readonly consoleDirectory?: string;
  readonly databaseUrl?: string;
  readonly packageDirectory?: string;
  readonly exportKeyPath?: string;
  readonly exportKeyId?: string;
  readonly releaseId?: string;
  readonly bodyLimitBytes?: number;
  readonly telemetryAdapters?: readonly TelemetryAdapterCertificateInput[];
  readonly lockTimeoutMs?: number;
  readonly internet?: InternetMode | string;
  readonly tls?: Partial<TlsPathsInput>;
}

export interface EdgeConfig {
  readonly deploymentMode: DeploymentMode;
  readonly bindAddress: string;
  readonly port: number;
  readonly configDirectory: string;
  readonly consoleDirectory: string;
  readonly databaseUrl: string;
  readonly packageDirectory: string;
  readonly exportKeyPath?: string;
  readonly exportKeyId?: string;
  readonly releaseId: string;
  readonly bodyLimitBytes: number;
  readonly telemetryAdapters: readonly TelemetryAdapterCertificate[];
  readonly lockTimeoutMs: number;
  readonly internet: InternetMode;
  readonly tls?: TlsPaths;
}

export function tlsRequestPolicy(config: Pick<EdgeConfig, "deploymentMode" | "telemetryAdapters">): { readonly requestCert: boolean; readonly rejectUnauthorized: boolean } {
  return Object.freeze({
    requestCert: config.deploymentMode === "tactical" || config.telemetryAdapters.length > 0,
    rejectUnauthorized: config.deploymentMode === "tactical",
  });
}

const DEFAULT_PACKAGE_DIRECTORY = "./data/packages";
const TEXT = /^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$/;
const LOOPBACK = new Set(["localhost", "127.0.0.1", "::1"]);

function assertNonEmptyString(value: string | undefined, field: string): string {
  if (typeof value !== "string" || value.trim().length === 0 || value !== value.trim() || value.includes("\0")) throw new Error(`${field} must be non-empty text`);
  return value;
}

function normalizePath(base: string, value: string | undefined, field: string): string {
  return resolvePortableRuntimePath(base, assertNonEmptyString(value, field));
}

function validateBindAddress(value: string): string {
  if (value !== "localhost" && isIP(value) === 0) throw new Error("bindAddress must be localhost or a valid IP address");
  return value;
}

function validatePositiveInteger(value: number, field: string, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isInteger(value) || value <= 0 || value > maximum) throw new Error(`${field} must be a positive integer`);
  return value;
}

function validatePort(value: number): number {
  if (!Number.isInteger(value) || value < 0 || value > 65_535) throw new Error("port must be an integer between 0 and 65535");
  return value;
}

function validateTls(tls: Partial<TlsPathsInput> | undefined, mode: DeploymentMode, base: string): TlsPaths | undefined {
  if (tls === undefined) {
    if (mode !== "test") throw new Error(`${mode} mode requires HTTPS certificate and key paths`);
    return undefined;
  }
  const hasCert = tls.certPath !== undefined;
  const hasKey = tls.keyPath !== undefined;
  if (hasCert !== hasKey) throw new Error("tls requires both certPath and keyPath");
  if (!hasCert || !hasKey) {
    if (mode !== "test") throw new Error(`${mode} mode requires HTTPS certificate and key paths`);
    return undefined;
  }
  if (mode === "tactical" && tls.clientCaPath === undefined) throw new Error("tactical mode requires a client CA path");
  return Object.freeze({
    certPath: normalizePath(base, tls.certPath, "tls.certPath"),
    keyPath: normalizePath(base, tls.keyPath, "tls.keyPath"),
    ...(tls.clientCaPath === undefined ? {} : { clientCaPath: normalizePath(base, tls.clientCaPath, "tls.clientCaPath") }),
    requireClientCertificate: mode === "tactical",
    rejectUnauthorizedClients: mode === "tactical",
  });
}

function validateTelemetryAdapters(records: readonly TelemetryAdapterCertificateInput[] | undefined): readonly TelemetryAdapterCertificate[] {
  const fingerprints = new Set<string>();
  const adapterIds = new Set<string>();
  return Object.freeze((records ?? []).map((record) => {
    const fingerprintSha256 = record.fingerprintSha256.replaceAll(":", "").toLowerCase();
    const adapterId = assertNonEmptyString(record.adapterId, "telemetry adapterId");
    if (!/^[a-f0-9]{64}$/.test(fingerprintSha256)) throw new Error("telemetry adapter fingerprint must be a SHA-256 digest");
    if (!TEXT.test(adapterId)) throw new Error("telemetry adapterId is invalid");
    if (fingerprints.has(fingerprintSha256) || adapterIds.has(adapterId)) throw new Error("telemetry adapter identities must be unique");
    if (!Array.isArray(record.aircraftIds) || record.aircraftIds.length === 0 || record.aircraftIds.length > 256) throw new Error("telemetry adapter aircraftIds must be bounded and non-empty");
    const aircraftIds = Object.freeze(record.aircraftIds.map((value) => {
      const id = assertNonEmptyString(value, "telemetry aircraftId");
      if (!TEXT.test(id)) throw new Error("telemetry aircraftId is invalid");
      return id;
    }));
    if (new Set(aircraftIds).size !== aircraftIds.length) throw new Error("telemetry aircraftIds must be unique");
    fingerprints.add(fingerprintSha256);
    adapterIds.add(adapterId);
    return Object.freeze({ fingerprintSha256, adapterId, aircraftIds });
  }));
}

export function createConfig(input: EdgeConfigInput = {}): EdgeConfig {
  const deploymentMode = input.deploymentMode ?? "test";
  if (!["test", "standalone", "tactical"].includes(deploymentMode)) throw new Error("deploymentMode is invalid");
  const bindAddress = validateBindAddress(input.bindAddress ?? "127.0.0.1");
  if (deploymentMode === "standalone" && !LOOPBACK.has(bindAddress)) throw new Error("standalone mode must bind to loopback");
  const configDirectory = resolvePortableRuntimePath(process.cwd(), input.configDirectory ?? ".");
  const port = validatePort(input.port ?? 0);
  const databaseUrl = input.databaseUrl === ":memory:" ? ":memory:" : normalizePath(configDirectory, input.databaseUrl ?? "./data/edge.sqlite", "databaseUrl");
  const packageDirectory = normalizePath(configDirectory, input.packageDirectory ?? DEFAULT_PACKAGE_DIRECTORY, "packageDirectory");
  const consoleDirectory = normalizePath(configDirectory, input.consoleDirectory ?? "./apps/console/dist", "consoleDirectory");
  const lockTimeoutMs = validatePositiveInteger(input.lockTimeoutMs ?? 5_000, "lockTimeoutMs");
  const bodyLimitBytes = validatePositiveInteger(input.bodyLimitBytes ?? 64 * 1024, "bodyLimitBytes", 1024 * 1024);
  if ((input.exportKeyPath === undefined) !== (input.exportKeyId === undefined)) throw new Error("exportKeyPath and exportKeyId must be configured together");
  const exportKeyId = input.exportKeyId === undefined ? undefined : assertNonEmptyString(input.exportKeyId, "exportKeyId");
  if (exportKeyId !== undefined && !TEXT.test(exportKeyId)) throw new Error("exportKeyId is invalid");
  const releaseId = input.releaseId ?? "fac-isr-sms@0.2.0-rc.1";
  if (releaseId !== "fac-isr-sms@0.2.0-rc.1") throw new Error("releaseId must identify this release candidate");
  const telemetryAdapters = validateTelemetryAdapters(input.telemetryAdapters);
  const tls = validateTls(input.tls, deploymentMode, configDirectory);
  if (deploymentMode !== "test" && telemetryAdapters.length > 0 && tls?.clientCaPath === undefined) throw new Error("telemetry adapters require a client CA path");
  const internet = input.internet ?? "disabled";
  if (internet !== "disabled") throw new Error("internet must be disabled for the edge runtime");
  return Object.freeze({
    deploymentMode,
    bindAddress,
    port,
    configDirectory,
    consoleDirectory,
    databaseUrl,
    packageDirectory,
    ...(input.exportKeyPath === undefined ? {} : { exportKeyPath: normalizePath(configDirectory, input.exportKeyPath, "exportKeyPath"), exportKeyId }),
    releaseId,
    bodyLimitBytes,
    telemetryAdapters,
    lockTimeoutMs,
    internet: "disabled" as const,
    tls,
  });
}
