import { createHash, createPublicKey } from "node:crypto";
import { lstat, readFile, realpath } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { assertSignedPackageManifest, canonicalJson, verifyPackage, type SignedPackageManifest, type VerificationReport } from "@fac-isr/evidence";
import { AtomicConflictError, AtomicDomainWriteError, type AuditEventInput, type AuditLedger } from "../audit/ledger.js";
import type { EdgeDatabase } from "../db/migrate.js";
import type { ServiceActorContext, StagedMissionMutation } from "./mission-service.js";
import type { ActiveSafetyPackage, ActiveSafetyPackageSource } from "./safety-evaluation.js";

export type PackageState = "verified" | "active" | "quarantined";
export type TrustedKeyAlgorithm = "ed25519" | "rsa-sha256";
export type TrustedKeyScope = SignedPackageManifest["kind"];
const PACKAGE_ID = /^[a-z0-9][a-z0-9._-]{2,127}$/;
const PACKAGE_VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

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

export class SqliteTrustedKeyStore implements TrustedKeyStore {
  public constructor(private readonly database: EdgeDatabase) {}

  public add(record: TrustedKeyRecord): TrustedKeyRecord {
    this.database.assertFencingToken();
    this.database.sql().prepare(`INSERT INTO trusted_keys
      (key_id, scope, algorithm, public_key_pem, added_at_utc, added_by_user_id)
      VALUES (?, ?, ?, ?, ?, ?)`)
      .run(record.keyId, record.scope, record.algorithm, record.publicKeyPem, record.addedAtUtc, record.addedByUserId);
    return Object.freeze({ ...record });
  }

  public get(keyId: string): TrustedKeyRecord | undefined {
    const row = this.database.sql().prepare("SELECT * FROM trusted_keys WHERE key_id = ?").get(keyId) as Record<string, unknown> | undefined;
    return row === undefined ? undefined : Object.freeze({ keyId: String(row.key_id), scope: String(row.scope) as TrustedKeyScope, algorithm: String(row.algorithm) as TrustedKeyAlgorithm, publicKeyPem: String(row.public_key_pem), addedAtUtc: String(row.added_at_utc), addedByUserId: String(row.added_by_user_id) });
  }

  public list(): readonly TrustedKeyRecord[] {
    const rows = this.database.sql().prepare("SELECT key_id FROM trusted_keys ORDER BY key_id").all() as { key_id: string }[];
    return Object.freeze(rows.map(({ key_id }) => this.get(key_id)!));
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
  readonly verifiedProvenance?: VerifiedPackageProvenance;
  readonly untrustedManifestSha256?: string;
  readonly checks: readonly PackageCheck[];
}

export interface VerifiedPackageProvenance {
  readonly packageId: string;
  readonly version: string;
  readonly contentSha256: string;
  readonly effectiveFromUtc: string;
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
  readonly missionService: {
    markSafetyEvaluationsStale(context: ServiceActorContext, reason: string): Promise<void>;
    stageSafetyEvaluationsStale?(context: ServiceActorContext, reason: string): StagedMissionMutation;
    getMission(missionId: string): Record<string, unknown>;
  };
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
  return {
    packageId: typeof manifest.packageId === "string" && PACKAGE_ID.test(manifest.packageId) ? manifest.packageId : "unknown",
    version: typeof manifest.version === "string" && PACKAGE_VERSION.test(manifest.version) ? manifest.version : "unknown",
  };
}

function checksFromReport(report: VerificationReport): readonly PackageCheck[] {
  return report.checks.map((check) => ({ id: check.id, status: check.status, ...(check.reason === undefined ? {} : { reason: check.reason }) }));
}

async function packagePath(root: string, directory: unknown): Promise<string> {
  const relativeDirectory = text(directory, ".");
  if (isAbsolute(relativeDirectory) || relativeDirectory.split(/[\\/]/).includes("..")) throw new Error("package directory must remain inside the configured package root");
  const full = resolve(root, relativeDirectory);
  const fromRoot = relative(resolve(root), full);
  if (fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) throw new Error("package directory must remain inside the configured package root");
  const rootInfo = await lstat(root);
  if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) throw new Error("configured package root must be a real directory, not a symbolic link");
  let cursor = root;
  for (const part of fromRoot.split(sep).filter(Boolean)) {
    cursor = resolve(cursor, part);
    const info = await lstat(cursor);
    if (info.isSymbolicLink()) throw new Error("package directory symbolic links are not permitted");
  }
  const fullInfo = await lstat(full);
  if (!fullInfo.isDirectory()) throw new Error("package directory must be a directory");
  const [realRoot, realFull] = await Promise.all([realpath(root), realpath(full)]);
  const realRelative = relative(realRoot, realFull);
  if (realRelative === ".." || realRelative.startsWith(`..${sep}`) || isAbsolute(realRelative)) throw new Error("package directory must remain contained by the configured package root");
  return realFull;
}

function hashPayload(value: unknown): string {
  const normalized = JSON.parse(JSON.stringify(value)) as unknown;
  return createHash("sha256").update(canonicalJson(normalized)).digest("hex");
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
    Object.freeze(value);
  }
  return value;
}

function detached<T>(value: T): T {
  return deepFreeze(JSON.parse(canonicalJson(value)) as T);
}

export class SafeModeService implements ActiveSafetyPackageSource {
  private readonly database: EdgeDatabase;
  private readonly packageDirectory: string;
  private readonly audit: AuditLedger;
  private readonly missions: SafeModeServiceOptions["missionService"];
  private readonly now: () => string;
  private readonly trustedKeys: TrustedKeyStore;
  private packages: PackageRecord[] = [];
  private packageGeneration = 0;
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
    const importedAtUtc = this.now();
    let record: PackageRecord;
    let eventType: "package.imported" | "package.quarantined";
    let validatedManifest: SignedPackageManifest | undefined;
    try {
      if (envelope.manifest === undefined) throw new Error("manifest is required");
      const manifest = detached(envelope.manifest);
      assertSignedPackageManifest(manifest, true);
      validatedManifest = manifest;
      const keyId = requiredText(envelope.keyId, "keyId");
      if (keyId !== manifest.keyId) throw new Error("package keyId does not match the manifest keyId");
      const trustedKey = this.requireTrustedKey(keyId, manifest.kind);
      if (envelope.publicKeyPem !== undefined) throw new Error("request-provided publicKeyPem is not accepted");
      const directory = await packagePath(this.packageDirectory, envelope.directory);
      const report = await verifyPackage(directory, manifest, trustedKey.publicKeyPem, importedAtUtc);
      if (!report.ok) throw new PackageVerificationError(report);
      const installed = this.packages.flatMap((candidate) => candidate.verifiedProvenance?.packageId === manifest.packageId ? [candidate.verifiedProvenance] : []);
      if (installed.some((candidate) => candidate.version === manifest.version)) throw new Error(`duplicate package identity already imported: ${manifest.packageId}@${manifest.version}`);
      for (const current of installed) rejectVerifiedDowngrade(current, manifest);
      if (manifest.qualification !== "approved") throw new Error("package qualification is not approved for activation");
      record = detached({ packageId: manifest.packageId, version: manifest.version, state: "verified" as const, reason: "verified against configured trusted key", importedAtUtc, directory, manifest, verifiedProvenance: provenanceFor(manifest), checks: checksFromReport(report) });
      eventType = "package.imported";
    } catch (error) {
      const reason = error instanceof PackageVerificationError ? error.message : error instanceof Error ? error.message : String(error);
      const checks = error instanceof PackageVerificationError ? checksFromReport(error.report) : [{ id: "verification", status: "fail" as const, reason }];
      record = detached({ packageId: identity.packageId, version: identity.version, state: "quarantined" as const, reason, importedAtUtc, ...(validatedManifest === undefined ? (envelope.manifest === undefined ? {} : { untrustedManifestSha256: hashPayload(envelope.manifest) }) : { manifest: validatedManifest }), checks });
      eventType = "package.quarantined";
    }
    const prior = this.packages;
    const duplicateIdentity = prior.some((existing) => existing.packageId === record.packageId && existing.version === record.version);
    const next = duplicateIdentity ? prior : [...prior, record];
    await this.commitSnapshot(next, [{ type: eventType, actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, occurredAtUtc: importedAtUtc, action: eventType === "package.imported" ? "import" : "quarantine", reason: record.reason, payload: { packageId: record.packageId, version: record.version } }]);
    return record;
  }

  public async activatePackage(input: ActivationInput, context: ServiceActorContext): Promise<PackageRecord> {
    if (this.databaseFailure) throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", "package writes are disabled while the local database is unavailable");
    const packageId = requiredText(input.packageId, "packageId");
    const version = requiredText(input.version, "version");
    const keyId = requiredText(input.keyId, "keyId");
    const configuredKey = this.trustedKeys.get(keyId);
    if (configuredKey === undefined) throw new SafeModeError(409, "TRUSTED_KEY_UNKNOWN", "package activation requires a configured trusted key", "quarantined");
    const candidates = this.packages.filter((record) => record.packageId === packageId && record.version === version && record.state === "verified");
    if (candidates.length > 1) throw new SafeModeError(409, "PACKAGE_IDENTITY_AMBIGUOUS", "package identity is not unique", "quarantined");
    const candidate = candidates[0];
    if (candidate?.manifest === undefined || candidate.directory === undefined) {
      throw new SafeModeError(409, "PACKAGE_NOT_VERIFIED", "package must be verified before activation", "quarantined");
    }
    if (candidate.manifest.keyId !== keyId) throw new SafeModeError(409, "PACKAGE_KEY_MISMATCH", "activation key does not match the verified package", "quarantined");
    const candidateManifest = candidate.manifest;
    const candidateDirectory = candidate.directory;
    const trustedKey = this.assertTrustedKey(keyId, configuredKey, candidateManifest.kind);
    const activatedAtUtc = this.now();
    await packagePath(this.packageDirectory, relative(this.packageDirectory, candidateDirectory));
    const report = await verifyPackage(candidateDirectory, candidateManifest, trustedKey.publicKeyPem, activatedAtUtc);
    if (!report.ok) {
      const quarantined: PackageRecord = detached({ ...candidate, state: "quarantined" as const, reason: report.checks.find((check) => check.status === "fail")?.reason ?? "package verification failed at activation", checks: checksFromReport(report) });
      const prior = this.packages;
      const next = prior.map((item) => item === candidate ? quarantined : item);
      await this.commitSnapshot(next, [{ type: "package.quarantined", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, occurredAtUtc: activatedAtUtc, action: "quarantine", reason: quarantined.reason, payload: { packageId, version } }]);
      throw new SafeModeError(409, "PACKAGE_ACTIVATION_REJECTED", quarantined.reason, "quarantined");
    }
    const active: PackageRecord = detached({ ...candidate, state: "active" as const, reason: "verified package activated", checks: checksFromReport(report) });
    const nextPackages = this.packages.map((record) => {
      if (record === candidate) return active;
      if (record.state === "active" && record.manifest?.kind === candidateManifest.kind) return detached({ ...record, state: "verified" as const, reason: "superseded by a newly activated package" });
      return record;
    });
    const invalidationReason = `package ${packageId}@${version} activation invalidated prior evaluations`;
    const stagedMission = this.missions.stageSafetyEvaluationsStale?.(context, invalidationReason);
    await this.commitSnapshot(
      nextPackages,
      [
        { type: "package.activated", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, occurredAtUtc: activatedAtUtc, action: "activate", reason: active.reason, payload: { packageId, version, keyId, kind: candidateManifest.kind } },
        ...(stagedMission?.auditInputs ?? []),
      ],
      stagedMission?.writeDomain,
      stagedMission?.publish,
    );
    if (stagedMission === undefined) await this.missions.markSafetyEvaluationsStale(context, invalidationReason);
    return active;
  }

  public async getQuarantine(): Promise<readonly PackageRecord[]> {
    await this.reverifyActivePackages(this.now());
    return this.packages.filter((record) => record.state === "quarantined").map((record) => ({ ...record, checks: [...record.checks] }));
  }

  public async getPackageState(): Promise<{ readonly active: readonly PackageRecord[]; readonly quarantined: readonly PackageRecord[] }> {
    await this.reverifyActivePackages(this.now());
    return Object.freeze({
      active: Object.freeze(this.databaseFailure ? [] : this.packages.filter((record) => record.state === "active").map(copyPackageRecord)),
      quarantined: Object.freeze(this.packages.filter((record) => record.state === "quarantined").map(copyPackageRecord)),
    });
  }

  public async getReverifiedActivePackage(kind: "policy" | "terminology" | "regulatory", asOfUtc: string): Promise<ActiveSafetyPackage> {
    await this.reverifyActivePackages(asOfUtc);
    if (this.databaseFailure) throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", "active packages are unavailable while package state is unsafe");
    const active = this.packages.filter((record) => record.state === "active" && record.manifest?.kind === kind);
    if (active.length !== 1 || active[0]?.manifest === undefined || active[0].directory === undefined) throw new SafeModeError(409, "ACTIVE_PACKAGE_UNAVAILABLE", `exactly one reverified active ${kind} package is required`, "quarantined");
    const record = active[0];
    const manifest = record.manifest;
    const directory = record.directory;
    if (manifest === undefined || directory === undefined) throw new SafeModeError(409, "ACTIVE_PACKAGE_UNAVAILABLE", `active ${kind} package is incomplete`, "quarantined");
    const documents: Record<string, string> = {};
    for (const file of manifest.files) {
      const content = await readFile(resolve(directory, file.path));
      if (content.byteLength !== file.sizeBytes || createHash("sha256").update(content).digest("hex") !== file.sha256) {
        throw new SafeModeError(409, "ACTIVE_PACKAGE_CONTENT_CHANGED", `active package content changed after verification: ${file.path}`, "quarantined");
      }
      documents[file.path] = content.toString("utf8");
    }
    return detached({ packageId: record.packageId, version: record.version, documents });
  }

  public async exportRevision(revisionId: string, context: ServiceActorContext): Promise<MissionExport> {
    if (this.exportFailure) throw new SafeModeError(500, "EXPORT_FAILED", "export failed before the mission store was changed");
    const missionId = revisionId.split(":", 1)[0] ?? revisionId;
    const mission = this.missions.getMission(missionId) as { missionId: string; revisions: readonly Record<string, unknown>[]; safetyResults: readonly unknown[]; checklistResponses: readonly unknown[]; gateApprovals: readonly unknown[] };
    const revision = mission.revisions.find((candidate) => candidate.id === revisionId);
    if (revision === undefined) throw new SafeModeError(404, "REVISION_NOT_FOUND", "mission revision was not found");
    const events = await this.audit.queryAudit({ missionRevisionId: revisionId });
    const payload = { revision, safetyResults: mission.safetyResults.filter((result) => (result as { revisionId?: string }).revisionId === revisionId), checklistResponses: mission.checklistResponses.filter((response) => (response as { revisionId?: string }).revisionId === revisionId), gateApprovals: mission.gateApprovals.filter((approval) => (approval as { missionRevisionId?: string }).missionRevisionId === revisionId) };
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

  public isReadOnlySafeMode(): boolean { return this.databaseFailure; }

  private load(): void {
    try {
      const generation = this.database.sql().prepare("SELECT generation FROM package_state_generation WHERE singleton = 1").get() as { generation: number } | undefined;
      if (generation === undefined || !Number.isInteger(generation.generation) || generation.generation < 0) throw new Error("package generation state is corrupt");
      this.packageGeneration = generation.generation;
      const rows = this.database.sql().prepare("SELECT record_json FROM packages ORDER BY package_id, version").all() as { record_json: string }[];
      this.packages = rows.map(({ record_json }) => parsePackageRecord(JSON.parse(record_json) as unknown));
      assertUniquePackageRecords(this.packages);
    } catch {
      this.packages = [];
      this.databaseFailure = true;
    }
  }

  private writeSnapshot(packages: readonly PackageRecord[]): void {
    const sql = this.database.sql();
    const claimed = sql.prepare("UPDATE package_state_generation SET generation = generation + 1 WHERE singleton = 1 AND generation = ?")
      .run(this.packageGeneration) as { changes?: number | bigint };
    if (Number(claimed.changes ?? 0) !== 1) throw new AtomicConflictError("package state changed in another repository instance");
    sql.prepare("DELETE FROM active_package_roles").run();
    sql.prepare("DELETE FROM packages").run();
    for (const record of packages) {
      const kind = record.manifest?.kind ?? null;
      sql.prepare("INSERT INTO packages (package_id, version, kind, state, imported_at_utc, record_json) VALUES (?, ?, ?, ?, ?, ?)")
        .run(record.packageId, record.version, kind, record.state, record.importedAtUtc, JSON.stringify(record));
      if (record.state === "active" && kind !== null) sql.prepare("INSERT INTO active_package_roles (role, package_id, version) VALUES (?, ?, ?)").run(kind, record.packageId, record.version);
    }
  }

  private async commitSnapshot(next: PackageRecord[], auditInputs: readonly AuditEventInput[], writeRelatedDomain?: () => void, publishRelated?: () => void): Promise<void> {
    if (this.databaseFailure) throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", "package writes are disabled while the local database is unavailable");
    try {
      await this.audit.commitAtomic(auditInputs, () => {
        try {
          this.writeSnapshot(next);
          writeRelatedDomain?.();
        } catch (error) {
          if (error instanceof AtomicConflictError) throw error;
          throw new AtomicDomainWriteError("normalized package persistence failed", { cause: error });
        }
      });
    } catch (error) {
      if (error instanceof AtomicConflictError) {
        throw new SafeModeError(409, "PACKAGE_STATE_CONFLICT", error.message);
      }
      this.databaseFailure = true;
      throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", errorMessage(error));
    }
    this.packages = next;
    this.packageGeneration += 1;
    publishRelated?.();
  }

  private async reverifyActivePackages(asOfUtc: string): Promise<void> {
    if (this.databaseFailure) return;
    const prior = this.packages;
    const replacements = new Map<PackageRecord, PackageRecord>();
    for (const record of prior.filter((candidate) => candidate.state === "active")) {
      let reason: string | undefined;
      let checks: readonly PackageCheck[] = record.checks;
      try {
        if (record.manifest === undefined || record.directory === undefined) throw new Error("active package record is incomplete");
        const key = this.requireTrustedKey(record.manifest.keyId, record.manifest.kind);
        await packagePath(this.packageDirectory, relative(this.packageDirectory, record.directory));
        const report = await verifyPackage(record.directory, record.manifest, key.publicKeyPem, asOfUtc);
        checks = checksFromReport(report);
        if (!report.ok) reason = report.checks.find((check) => check.status === "fail")?.reason ?? "active package re-verification failed";
      } catch (error) {
        reason = errorMessage(error);
        checks = [{ id: "active-reverification", status: "fail", reason }];
      }
      if (reason !== undefined) replacements.set(record, detached({ ...record, state: "quarantined" as const, reason, checks }));
    }
    if (replacements.size === 0) return;
    const next = prior.map((record) => replacements.get(record) ?? record);
    const occurredAtUtc = this.now();
    await this.commitSnapshot(next, [...replacements.values()].map((quarantined) => ({ type: "package.quarantined", actorUserId: "safe-mode-service", clientSessionId: "package-reverification", occurredAtUtc, action: "quarantine", reason: quarantined.reason, payload: { packageId: quarantined.packageId, version: quarantined.version } })));
  }

  private requireTrustedKey(keyId: string, kind: SignedPackageManifest["kind"]): TrustedKeyRecord {
    const record = this.trustedKeys.get(keyId);
    if (record === undefined) throw new Error(`unknown trusted key: ${keyId}`);
    return this.assertTrustedKey(keyId, record, kind);
  }

  private assertTrustedKey(lookupId: string, value: TrustedKeyRecord, kind: SignedPackageManifest["kind"]): TrustedKeyRecord {
    if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("trusted key record is invalid");
    if (value.keyId !== lookupId || value.keyId.trim() === "") throw new Error("trusted key record keyId does not match its lookup ID");
    if (value.scope !== kind) throw new Error(`trusted key ${value.keyId} has wrong scope for ${kind}`);
    if (value.algorithm !== "ed25519" && value.algorithm !== "rsa-sha256") throw new Error(`trusted key ${value.keyId} uses an unsupported algorithm`);
    if (!isExactUtc(value.addedAtUtc) || Date.parse(value.addedAtUtc) > Date.parse(this.now()) || typeof value.addedByUserId !== "string" || value.addedByUserId.trim() === "") throw new Error(`trusted key ${value.keyId} metadata is invalid`);
    if (typeof value.publicKeyPem !== "string" || value.publicKeyPem.trim() === "") throw new Error(`trusted key ${value.keyId} public key is invalid`);
    const keyType = createPublicKey(value.publicKeyPem).asymmetricKeyType;
    switch (value.algorithm) {
      case "ed25519":
        if (keyType !== "ed25519") throw new Error(`trusted key ${value.keyId} algorithm does not match its key material`);
        break;
      case "rsa-sha256":
        if (keyType !== "rsa" && keyType !== "rsa-pss") throw new Error(`trusted key ${value.keyId} algorithm does not match its key material`);
        break;
      default:
        throw new Error(`trusted key ${value.keyId} uses an unsupported algorithm`);
    }
    return detached(value);
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
  return detached(record);
}

function isExactUtc(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?Z$/.exec(value);
  if (!match) return false;
  const [, year, month, day, hour, minute, second, fraction = "000"] = match;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === Number(year)
    && date.getUTCMonth() + 1 === Number(month)
    && date.getUTCDate() === Number(day)
    && date.getUTCHours() === Number(hour)
    && date.getUTCMinutes() === Number(minute)
    && date.getUTCSeconds() === Number(second)
    && date.getUTCMilliseconds() === Number(fraction);
}

export function parsePackageRecord(value: unknown): PackageRecord {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("package record must be an object");
  const record = value as Record<string, unknown>;
  const packageId = requiredStoredText(record.packageId, "packageId");
  const version = requiredStoredText(record.version, "version");
  if (!(["verified", "active", "quarantined"] as const).includes(record.state as PackageState)) throw new Error("package record state is invalid");
  const reason = requiredStoredText(record.reason, "reason");
  if (!isExactUtc(record.importedAtUtc)) throw new Error("package record importedAtUtc is invalid");
  if (!Array.isArray(record.checks)) throw new Error("package record checks are invalid");
  const checks = record.checks.map((value) => {
    if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("package check is invalid");
    const check = value as Record<string, unknown>;
    const id = requiredStoredText(check.id, "check.id");
    if (!["pass", "fail", "warn"].includes(String(check.status))) throw new Error("package check status is invalid");
    return { id, status: check.status as PackageCheck["status"], ...(check.reason === undefined ? {} : { reason: requiredStoredText(check.reason, "check.reason") }) };
  });
  let manifest: SignedPackageManifest | undefined;
  if (record.manifest !== undefined) {
    assertSignedPackageManifest(record.manifest, true);
    manifest = record.manifest;
    if (manifest.packageId !== packageId || manifest.version !== version) throw new Error("package record identity does not match its manifest");
  }
  const directory = record.directory === undefined ? undefined : requiredStoredText(record.directory, "directory");
  let verifiedProvenance: VerifiedPackageProvenance | undefined;
  if (record.verifiedProvenance !== undefined) {
    if (record.verifiedProvenance === null || typeof record.verifiedProvenance !== "object" || Array.isArray(record.verifiedProvenance)) throw new Error("verified package provenance is invalid");
    const raw = record.verifiedProvenance as Record<string, unknown>;
    verifiedProvenance = {
      packageId: requiredStoredText(raw.packageId, "verifiedProvenance.packageId"),
      version: requiredStoredText(raw.version, "verifiedProvenance.version"),
      contentSha256: requiredStoredSha256(raw.contentSha256, "verifiedProvenance.contentSha256"),
      effectiveFromUtc: requiredStoredUtc(raw.effectiveFromUtc, "verifiedProvenance.effectiveFromUtc"),
    };
    if (verifiedProvenance.packageId !== packageId || verifiedProvenance.version !== version || manifest?.contentSha256 !== verifiedProvenance.contentSha256 || manifest.effectiveFromUtc !== verifiedProvenance.effectiveFromUtc) throw new Error("verified package provenance does not match its immutable record");
  }
  if (record.state !== "quarantined" && verifiedProvenance === undefined) throw new Error("non-quarantined package record lacks verified provenance");
  const untrustedManifestSha256 = record.untrustedManifestSha256 === undefined ? undefined : requiredStoredSha256(record.untrustedManifestSha256, "untrustedManifestSha256");
  if (untrustedManifestSha256 !== undefined && (record.state !== "quarantined" || manifest !== undefined || verifiedProvenance !== undefined)) throw new Error("untrusted manifest digest is invalid for this package record");
  return detached({ packageId, version, state: record.state as PackageState, reason, importedAtUtc: record.importedAtUtc, ...(directory === undefined ? {} : { directory }), ...(manifest === undefined ? {} : { manifest }), ...(verifiedProvenance === undefined ? {} : { verifiedProvenance }), ...(untrustedManifestSha256 === undefined ? {} : { untrustedManifestSha256 }), checks });
}

function requiredStoredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim()) throw new Error(`package record ${field} is invalid`);
  return value;
}

function requiredStoredSha256(value: unknown, field: string): string {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)) throw new Error(`package record ${field} is invalid`);
  return value;
}

function requiredStoredUtc(value: unknown, field: string): string {
  if (!isExactUtc(value)) throw new Error(`package record ${field} is invalid`);
  return value;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function assertUniquePackageRecords(records: readonly PackageRecord[]): void {
  const identities = new Set<string>();
  const activeKinds = new Set<string>();
  for (const record of records) {
    if (record.verifiedProvenance !== undefined) {
      const identity = `${record.verifiedProvenance.packageId}@${record.verifiedProvenance.version}`;
      if (identities.has(identity)) throw new Error(`duplicate persisted verified package identity: ${identity}`);
      identities.add(identity);
    }
    if (record.state === "active" && record.manifest !== undefined) {
      if (activeKinds.has(record.manifest.kind)) throw new Error(`multiple active persisted packages for kind: ${record.manifest.kind}`);
      activeKinds.add(record.manifest.kind);
    }
  }
}

function provenanceFor(manifest: SignedPackageManifest): VerifiedPackageProvenance {
  return { packageId: manifest.packageId, version: manifest.version, contentSha256: manifest.contentSha256, effectiveFromUtc: manifest.effectiveFromUtc };
}

function rejectVerifiedDowngrade(current: VerifiedPackageProvenance, incoming: SignedPackageManifest): void {
  if (Date.parse(incoming.effectiveFromUtc) < Date.parse(current.effectiveFromUtc)) throw new Error(`package effective-period downgrade rejected: ${current.effectiveFromUtc} -> ${incoming.effectiveFromUtc}`);
  const currentParts = current.version.split(".").map(Number);
  const incomingParts = incoming.version.split(".").map(Number);
  for (let index = 0; index < 3; index += 1) {
    const difference = (incomingParts[index] ?? 0) - (currentParts[index] ?? 0);
    if (difference > 0) return;
    if (difference < 0) throw new Error(`package downgrade rejected: ${current.version} -> ${incoming.version}`);
  }
}
