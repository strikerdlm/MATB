import { isIP } from "node:net";
import { resolve } from "node:path";

export interface TlsConfigInput {
  readonly tacticalMode: boolean;
  readonly bindAddress: string;
  readonly certPath?: string;
  readonly keyPath?: string;
  readonly clientCaPath?: string;
}

export interface TlsConfig {
  readonly tacticalMode: boolean;
  readonly bindAddress: string;
  readonly certPath?: string;
  readonly keyPath?: string;
  readonly clientCaPath?: string;
  readonly requireClientCertificate: boolean;
  readonly rejectUnauthorizedClients: boolean;
  readonly loopbackBootstrapAllowed: boolean;
}

export interface TransportRequest {
  readonly bindAddress: string;
  readonly encrypted: boolean;
  readonly loopbackBootstrap: boolean;
}

export interface TransportDecision {
  readonly allowed: boolean;
  readonly reason: string;
}

export interface TlsPeerInput {
  readonly subject: string;
  readonly fingerprintSha256: string;
  readonly observedAtUtc: string;
}

export interface TlsPeerAuditIdentity extends TlsPeerInput {
  readonly source: "tls-client-certificate";
}

function isLoopback(address: string): boolean {
  return address === "localhost" || address === "127.0.0.1" || address === "::1";
}

function canonicalPath(value: string | undefined, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value.includes("\0")) {
    throw new Error(`${field} must be a non-empty path`);
  }
  return resolve(value);
}

function validUtc(value: string): boolean {
  const timestamp = new Date(value);
  return Number.isFinite(timestamp.getTime()) && value.endsWith("Z");
}

export function validateTlsConfig(input: TlsConfigInput): TlsConfig {
  if (typeof input.tacticalMode !== "boolean") throw new Error("tacticalMode is required");
  if (input.bindAddress !== "localhost" && isIP(input.bindAddress) === 0) {
    throw new Error("bindAddress must be localhost or a valid IP address");
  }
  const hasCert = input.certPath !== undefined;
  const hasKey = input.keyPath !== undefined;
  if (hasCert !== hasKey) throw new Error("TLS requires both certificate and key paths");
  if (input.tacticalMode && (!hasCert || !hasKey)) {
    throw new Error("tactical mode requires certificate and key paths");
  }
  if (input.tacticalMode && input.clientCaPath === undefined) throw new Error("tactical mode requires a client CA path");
  if (!input.tacticalMode && !isLoopback(input.bindAddress)) throw new Error("standalone mode must bind to loopback");
  return Object.freeze({
    tacticalMode: input.tacticalMode,
    bindAddress: input.bindAddress,
    certPath: hasCert ? canonicalPath(input.certPath, "certPath") : undefined,
    keyPath: hasKey ? canonicalPath(input.keyPath, "keyPath") : undefined,
    clientCaPath: input.clientCaPath === undefined ? undefined : canonicalPath(input.clientCaPath, "clientCaPath"),
    requireClientCertificate: input.tacticalMode,
    rejectUnauthorizedClients: input.tacticalMode,
    loopbackBootstrapAllowed: isLoopback(input.bindAddress),
  });
}

export function authorizeTransport(input: TransportRequest): TransportDecision {
  if (input.bindAddress !== "localhost" && isIP(input.bindAddress) === 0) {
    return { allowed: false, reason: "bind address is invalid" };
  }
  if (input.encrypted) return { allowed: true, reason: "authenticated TLS transport" };
  if (input.loopbackBootstrap && isLoopback(input.bindAddress)) {
    return { allowed: true, reason: "explicit loopback bootstrap" };
  }
  return { allowed: false, reason: "plaintext transport is restricted to loopback bootstrap" };
}

export function recordTlsPeer(input: TlsPeerInput): TlsPeerAuditIdentity {
  if (typeof input.subject !== "string" || input.subject.trim() === "") {
    throw new Error("TLS peer subject is required");
  }
  if (!/^[a-f0-9]{64}$/i.test(input.fingerprintSha256)) {
    throw new Error("TLS peer fingerprint must be a SHA-256 hex digest");
  }
  if (!validUtc(input.observedAtUtc)) throw new Error("TLS peer timestamp must be UTC");
  return Object.freeze({
    source: "tls-client-certificate",
    subject: input.subject,
    fingerprintSha256: input.fingerprintSha256.toLowerCase(),
    observedAtUtc: new Date(input.observedAtUtc).toISOString(),
  });
}
