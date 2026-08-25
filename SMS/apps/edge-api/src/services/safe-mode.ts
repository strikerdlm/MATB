import { createHash, createPublicKey } from "node:crypto";
import { isAbsolute, relative, resolve } from "node:path";
import { assertSignedPackageManifest, canonicalJson, rejectDowngrade, verifyPackage, type SignedPackageManifest, type VerificationReport } from "@fac-isr/evidence";
import type { AuditLedger } from "../audit/ledger.js";
import type { EdgeDatabase } from "../db/migrate.js";
import type { MissionService, ServiceActorContext } from "./mission-service.js";

export type PackageState = "verified" | "active" | "quarantined";
export type TrustedKeyAlgorithm = "ed25519" | "rsa-sha256";
export type TrustedKeyScope = SignedPackageManifest["kind"] | "*";

export interface TrustedKeyRecord {
  readonly keyId: string;
  readonly scope: TrustedKeyScope;
  readonly algorithm: TrustedKeyAlgorithm;
  readonly publicKeyPem: string;
  readonly addedAtUtc: string;
  readonly addedByUserId: string;
}

export interface TrustedKeyStore {
  get(keyId: string): TrustedKeyRecord | undefined;
}

export class InMemoryTrustedKeyStore implements TrustedKeyStore {
  private readonly records: ReadonlyMap<string, TrustedKeyRecord>;

  public constructor(records: readonly TrustedKeyRecord[] = []) {
    this.records = new Map(records.map((record) => [record.keyId, Object.freeze({ ...record })]));
  }

  public get(keyId: string): TrustedKeyRecord | undefined {
    return this.records.get(keyId);
  }
}

export interface PackageCheck {
  readonly id: string;
  readonly status: "pass" | "fail" | "warn";
  readonly reason?: string;
}

export interface PackageRecord {
  readonly packageId: string;
  readonly version: string;
  readonly state: PackageState;
  readonly reason: string;
  readonly importedAtUtc: string;
  readonly directory?: string;
  readonly manifest?: SignedPackageManifest;
  readonly checks: readonly PackageCheck[];
}

export interface MissionExport {
  readonly exportSchemaVersion: "1.0";
  readonly exportId: string;
  readonly missionId: string;
  readonly revisionId: string;
  readonly exportedAtUtc: string;
  readonly revision: unknown;
  readonly safetyResults: readonly unknown[];
  readonly checklistResponses: readonly unknown[];
  readonly gateApprovals: readonly unknown[];
  readonly auditManifest: { readonly eventCount: number; readonly eventHashes: readonly string[] };
  readonly hashes: { readonly payloadSha256: string };
}

export class SafeModeError extends Error {
  public constructor(public readonly statusCode: number, public readonly code: string, message: string, public readonly state: "read-only" | "quarantined" = "read-only") {
    super(message);
    this.name = "SafeModeError";
  }
}

export interface SafeModeServiceOptions {
  readonly database: EdgeDatabase;
  readonly packageDirectory: string;
  readonly auditLedger: AuditLedger;
  readonly missionService: MissionService;
  readonly now?: () => string;
  readonly trustedKeyStore?: TrustedKeyStore;
}

interface ImportInput {
  readonly directory?: unknown;
  readonly manifest?: unknown;
  readonly publicKeyPem?: unknown;
  readonly keyId?: unknown;
  readonly asOfUtc?: unknown;
}

interface ActivationInput {
  readonly packageId?: unknown;
  readonly version?: unknown;
  readonly keyId?: unknown;
  readonly asOfUtc?: unknown;
}

function objectInput(input: unknown): ImportInput {
  if (input === null || typeof input !== "object" || Array.isArray(input)) return {};
  return input as ImportInput;
}

function text(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() !== "" ? value : fallback;
}

function manifestIdentity(value: unknown): { packageId: string; version: string } {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return { packageId: "unknown", version: "unknown" };
  const manifest = value as Record<string, unknown>;
  return { packageId: text(manifest.packageId, "unknown"), version: text(manifest.version, "unknown") };
}

function checksFromReport(report: VerificationReport): readonly PackageCheck[] {
  return report.checks.map((check) => ({ id: check.id, status: check.status, ...(check.reason === undefined ? {} : { reason: check.reason }) }));
}

function packagePath(root: string, directory: unknown): string {
  const relativeDirectory = text(directory, ".");
  if (isAbsolute(relativeDirectory) || relativeDirectory.split(/[\\/]/).includes("..")) throw new Error("package directory must remain inside the configured package root");
  const full = resolve(root, relativeDirectory);
  const fromRoot = relative(resolve(root), full);
  if (fromRoot === ".." || fromRoot.startsWith("..")) throw new Error("package directory must remain inside the configured package root");
  return full;
}

function hashPayload(value: unknown): string {
  const normalized = JSON.parse(JSON.stringify(value)) as unknown;
  return createHash("sha256").update(canonicalJson(normalized)).digest("hex");
}

export class SafeModeService {
  private readonly database: EdgeDatabase;
  private readonly packageDirectory: string;
  private readonly audit: AuditLedger;
  private readonly missions: MissionService;
  private readonly now: () => string;
  private readonly trustedKeys: TrustedKeyStore;
  private packages: PackageRecord[] = [];
  private databaseFailure = false;
  private exportFailure = false;

  public constructor(options: SafeModeServiceOptions) {
    this.database = options.database;
    this.packageDirectory = resolve(options.packageDirectory);
    this.audit = options.auditLedger;
    this.missions = options.missionService;
    this.now = options.now ?? (() => new Date().toISOString());
    this.trustedKeys = options.trustedKeyStore ?? new InMemoryTrustedKeyStore();
    this.load();
  }

  public async importPackage(input: unknown, context: ServiceActorContext): Promise<PackageRecord> {
    if (this.databaseFailure) throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", "package writes are disabled while the local database is unavailable");
    const envelope = objectInput(input);
    const identity = manifestIdentity(envelope.manifest);
    const importedAtUtc = text(envelope.asOfUtc, this.now());
    try {
      if (envelope.manifest === undefined) throw new Error("manifest is required");
      assertSignedPackageManifest(envelope.manifest, true);
      const manifest = envelope.manifest;
      const keyId = requiredText(envelope.keyId, "keyId");
      if (keyId !== manifest.keyId) throw new Error("package keyId does not match the manifest keyId");
      const trustedKey = this.requireTrustedKey(keyId, manifest.kind);
      if (envelope.publicKeyPem !== undefined) throw new Error("request-provided publicKeyPem is not accepted");
      const directory = packagePath(this.packageDirectory, envelope.directory);
      const report = await verifyPackage(directory, manifest, trustedKey.publicKeyPem, importedAtUtc);
      if (!report.ok) throw new PackageVerificationError(report);
      const current = this.packages.find((record) => record.packageId === manifest.packageId && record.state !== "quarantined" && record.manifest !== undefined);
      if (current?.manifest !== undefined) rejectDowngrade(current.manifest, manifest);
      if (manifest.qualification !== "approved") throw new Error("package qualification is not approved for activation");
      const record: PackageRecord = Object.freeze({ packageId: manifest.packageId, version: manifest.version, state: "verified", reason: "verified against configured trusted key", importedAtUtc, directory, manifest, checks: report.checks });
      this.packages.push(record);
      this.persist();
      await this.audit.append({ type: "package.imported", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, occurredAtUtc: importedAtUtc, action: "import", reason: record.reason, payload: { packageId: record.packageId, version: record.version } });
      return record;
    } catch (error) {
      const reason = error instanceof PackageVerificationError ? error.message : error instanceof Error ? error.message : String(error);
      const checks = error instanceof PackageVerificationError ? checksFromReport(error.report) : [{ id: "verification", status: "fail" as const, reason }];
      const record: PackageRecord = Object.freeze({ packageId: identity.packageId, version: identity.version, state: "quarantined", reason, importedAtUtc, ...(envelope.manifest !== undefined && typeof envelope.manifest === "object" ? { manifest: envelope.manifest as SignedPackageManifest } : {}), checks });
      this.packages.push(record);
      this.persist();
      await this.audit.append({ type: "package.quarantined", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, occurredAtUtc: importedAtUtc, action: "quarantine", reason, payload: { packageId: record.packageId, version: record.version } });
      return record;
    }
  }

  public async activatePackage(input: ActivationInput, context: ServiceActorContext): Promise<PackageRecord> {
    if (this.databaseFailure) throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", "package writes are disabled while the local database is unavailable");
    const packageId = requiredText(input.packageId, "packageId");
    const version = requiredText(input.version, "version");
    const keyId = requiredText(input.keyId, "keyId");
    const trustedKey = this.trustedKeys.get(keyId);
    if (trustedKey === undefined) throw new SafeModeError(409, "TRUSTED_KEY_UNKNOWN", "package activation requires a configured trusted key", "quarantined");
    const candidate = this.packages.find((record) => record.packageId === packageId && record.version === version && record.state === "verified");
    if (candidate?.manifest === undefined || candidate.directory === undefined) {
      throw new SafeModeError(409, "PACKAGE_NOT_VERIFIED", "package must be verified before activation", "quarantined");
    }
    if (candidate.manifest.keyId !== keyId) throw new SafeModeError(409, "PACKAGE_KEY_MISMATCH", "activation key does not match the verified package", "quarantined");
    this.assertTrustedKey(trustedKey, candidate.manifest.kind);
    const activatedAtUtc = text(input.asOfUtc, this.now());
    const report = await verifyPackage(candidate.directory, candidate.manifest, trustedKey.publicKeyPem, activatedAtUtc);
    if (!report.ok) {
      const quarantined: PackageRecord = Object.freeze({ ...candidate, state: "quarantined", reason: report.checks.find((check) => check.status === "fail")?.reason ?? "package verification failed at activation", checks: checksFromReport(report) });
      this.packages = this.packages.map((record) => record === candidate ? quarantined : record);
      this.persist();
      throw new SafeModeError(409, "PACKAGE_ACTIVATION_REJECTED", quarantined.reason, "quarantined");
    }
    const active: PackageRecord = Object.freeze({ ...candidate, state: "active", reason: "verified package activated", checks: checksFromReport(report) });
    const nextPackages = this.packages.map((record) => {
      if (record === candidate) return active;
      if (record.state === "active" && record.manifest?.kind === candidate.manifest?.kind) return Object.freeze({ ...record, state: "verified" as const, reason: "superseded by a newly activated package" });
      return record;
    });
    await this.audit.append({ type: "package.activated", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, occurredAtUtc: activatedAtUtc, action: "activate", reason: active.reason, payload: { packageId, version, keyId, kind: candidate.manifest.kind } });
    await this.missions.markSafetyEvaluationsStale(context, `package ${packageId}@${version} activation invalidated prior evaluations`);
    this.packages = nextPackages;
    this.persist();
    return active;
  }

  public getQuarantine(): readonly PackageRecord[] {
    return this.packages.filter((record) => record.state === "quarantined").map((record) => ({ ...record, checks: [...record.checks] }));
  }

  public getPackageState(): { readonly active: readonly PackageRecord[]; readonly quarantined: readonly PackageRecord[] } {
    return Object.freeze({
      active: Object.freeze(this.packages.filter((record) => record.state === "active").map(copyPackageRecord)),
      quarantined: Object.freeze(this.packages.filter((record) => record.state === "quarantined").map(copyPackageRecord)),
    });
  }

  public async exportRevision(revisionId: string, context: ServiceActorContext): Promise<MissionExport> {
    if (this.exportFailure) throw new SafeModeError(500, "EXPORT_FAILED", "export failed before the mission store was changed");
    const missionId = revisionId.split(":", 1)[0] ?? revisionId;
    const mission = this.missions.getMission(missionId) as { missionId: string; revisions: readonly Record<string, unknown>[]; safetyResults: readonly unknown[]; checklistResponses: readonly unknown[]; gateApprovals: readonly unknown[] };
    const revision = mission.revisions.find((candidate) => candidate.id === revisionId);
    if (revision === undefined) throw new SafeModeError(404, "REVISION_NOT_FOUND", "mission revision was not found");
    const events = await this.audit.queryAudit({ missionRevisionId: revisionId });
    const payload = { revision, safetyResults: mission.safetyResults.filter((result) => (result as { missionRevisionId?: string }).missionRevisionId === revisionId), checklistResponses: mission.checklistResponses.filter((response) => (response as { revisionId?: string }).revisionId === revisionId), gateApprovals: mission.gateApprovals.filter((approval) => (approval as { missionRevisionId?: string }).missionRevisionId === revisionId) };
    const exportedAtUtc = this.now();
    const result = Object.freeze({ exportSchemaVersion: "1.0" as const, exportId: `export:${revisionId}:${exportedAtUtc}`, missionId: mission.missionId, revisionId, exportedAtUtc, ...payload, auditManifest: { eventCount: events.length, eventHashes: events.map((event) => event.hash) }, hashes: { payloadSha256: hashPayload(payload) } });
    await this.audit.append({ type: "export.created", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, missionRevisionId: revisionId, occurredAtUtc: exportedAtUtc, action: "export", reason: "revision export created", payload: { exportId: result.exportId } });
    return result;
  }

  public reviewMissionImport(input: unknown): Record<string, unknown> {
    const envelope = objectInput(input) as Record<string, unknown>;
    return Object.freeze({ state: "read-only-review", cloneRequired: true, missionId: text(envelope.missionId, "unknown"), revisionId: text(envelope.revisionId, "unknown"), requestedState: text(envelope.requestedState, "Draft"), availableActions: ["review", "clone"], blockedActions: ["activate", "release", "overwrite"] });
  }

  /** Fixture-only failure injection used to prove safe-mode behavior. */
  public async simulateDatabaseFailure(): Promise<void> { this.databaseFailure = true; }
  /** Fixture-only failure injection used to prove exports are non-mutating. */
  public async simulateExportFailure(): Promise<void> { this.exportFailure = true; }

  private load(): void {
    try {
      const row = this.database.sql().prepare("SELECT value FROM service_state WHERE key = ?").get("package_store") as { value?: unknown } | undefined;
      if (row?.value === undefined) return;
      const parsed = JSON.parse(String(row.value)) as unknown;
      if (!Array.isArray(parsed)) throw new Error("package store must be an array");
      this.packages = parsed as PackageRecord[];
    } catch {
      this.databaseFailure = true;
    }
  }

  private persist(): void {
    if (this.databaseFailure) throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", "package writes are disabled while the local database is unavailable");
    try {
      const value = JSON.stringify(this.packages);
      this.database.sql().prepare("INSERT INTO service_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value").run("package_store", value);
    } catch (error) {
      this.databaseFailure = true;
      throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", error instanceof Error ? error.message : "package store write failed");
    }
  }

  private requireTrustedKey(keyId: string, kind: SignedPackageManifest["kind"]): TrustedKeyRecord {
    const record = this.trustedKeys.get(keyId);
    if (record === undefined) throw new Error(`unknown trusted key: ${keyId}`);
    this.assertTrustedKey(record, kind);
    return record;
  }

  private assertTrustedKey(record: TrustedKeyRecord, kind: SignedPackageManifest["kind"]): void {
    if (record.scope !== "*" && record.scope !== kind) throw new Error(`trusted key ${record.keyId} has wrong scope for ${kind}`);
    const keyType = createPublicKey(record.publicKeyPem).asymmetricKeyType;
    if (record.algorithm === "ed25519" && keyType !== "ed25519") throw new Error(`trusted key ${record.keyId} algorithm does not match its key material`);
    if (record.algorithm === "rsa-sha256" && keyType !== "rsa" && keyType !== "rsa-pss") throw new Error(`trusted key ${record.keyId} algorithm does not match its key material`);
  }
}

class PackageVerificationError extends Error {
  public constructor(public readonly report: VerificationReport) {
    super(report.checks.find((check) => check.status === "fail")?.reason ?? "package verification failed");
    this.name = "PackageVerificationError";
  }
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim()) throw new SafeModeError(400, "INVALID_PACKAGE_INPUT", `${field} is required`, "quarantined");
  return value;
}

function copyPackageRecord(record: PackageRecord): PackageRecord {
  return { ...record, checks: [...record.checks] };
}
