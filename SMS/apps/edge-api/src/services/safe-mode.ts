import { createHash } from "node:crypto";
import { isAbsolute, relative, resolve } from "node:path";
import { assertSignedPackageManifest, canonicalJson, rejectDowngrade, verifyPackage, type SignedPackageManifest, type VerificationReport } from "@fac-isr/evidence";
import type { AuditLedger } from "../audit/ledger.js";
import type { EdgeDatabase } from "../db/migrate.js";
import type { MissionService } from "./mission-service.js";

export type PackageState = "active" | "quarantined";

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

interface SafeModeServiceOptions {
  readonly database: EdgeDatabase;
  readonly packageDirectory: string;
  readonly auditLedger: AuditLedger;
  readonly missionService: MissionService;
  readonly now?: () => string;
}

interface ImportInput {
  readonly directory?: unknown;
  readonly manifest?: unknown;
  readonly publicKeyPem?: unknown;
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
  private packages: PackageRecord[] = [];
  private databaseFailure = false;
  private exportFailure = false;

  public constructor(options: SafeModeServiceOptions) {
    this.database = options.database;
    this.packageDirectory = resolve(options.packageDirectory);
    this.audit = options.auditLedger;
    this.missions = options.missionService;
    this.now = options.now ?? (() => new Date().toISOString());
    this.load();
  }

  public async importPackage(input: unknown): Promise<PackageRecord> {
    if (this.databaseFailure) throw new SafeModeError(503, "SAFE_MODE_DATABASE_FAILURE", "package writes are disabled while the local database is unavailable");
    const envelope = objectInput(input);
    const identity = manifestIdentity(envelope.manifest);
    const importedAtUtc = text(envelope.asOfUtc, this.now());
    try {
      if (envelope.manifest === undefined) throw new Error("manifest is required");
      assertSignedPackageManifest(envelope.manifest, true);
      const manifest = envelope.manifest;
      if (typeof envelope.publicKeyPem !== "string" || envelope.publicKeyPem.trim() === "") throw new Error("publicKeyPem is required for signature verification");
      const directory = packagePath(this.packageDirectory, envelope.directory);
      const report = await verifyPackage(directory, manifest, envelope.publicKeyPem, importedAtUtc);
      if (!report.ok) throw new PackageVerificationError(report);
      const current = this.packages.find((record) => record.packageId === manifest.packageId && record.state === "active" && record.manifest !== undefined);
      if (current?.manifest !== undefined) rejectDowngrade(current.manifest, manifest);
      if (manifest.qualification !== "approved") throw new Error("package qualification is not approved for activation");
      const record: PackageRecord = Object.freeze({ packageId: manifest.packageId, version: manifest.version, state: "active", reason: "verified and approved", importedAtUtc, manifest, checks: report.checks });
      this.packages.push(record);
      this.persist();
      await this.audit.append({ type: "package.imported", actorUserId: "edge-service", occurredAtUtc: importedAtUtc, action: "import", reason: record.reason, payload: { packageId: record.packageId, version: record.version } });
      return record;
    } catch (error) {
      const reason = error instanceof PackageVerificationError ? error.message : error instanceof Error ? error.message : String(error);
      const checks = error instanceof PackageVerificationError ? checksFromReport(error.report) : [{ id: "verification", status: "fail" as const, reason }];
      const record: PackageRecord = Object.freeze({ packageId: identity.packageId, version: identity.version, state: "quarantined", reason, importedAtUtc, ...(envelope.manifest !== undefined && typeof envelope.manifest === "object" ? { manifest: envelope.manifest as SignedPackageManifest } : {}), checks });
      this.packages.push(record);
      this.persist();
      await this.audit.append({ type: "package.quarantined", actorUserId: "edge-service", occurredAtUtc: importedAtUtc, action: "quarantine", reason, payload: { packageId: record.packageId, version: record.version } });
      return record;
    }
  }

  public getQuarantine(): readonly PackageRecord[] {
    return this.packages.filter((record) => record.state === "quarantined").map((record) => ({ ...record, checks: [...record.checks] }));
  }

  public async exportRevision(revisionId: string): Promise<MissionExport> {
    if (this.exportFailure) throw new SafeModeError(500, "EXPORT_FAILED", "export failed before the mission store was changed");
    const missionId = revisionId.split(":", 1)[0] ?? revisionId;
    const mission = this.missions.getMission(missionId) as { missionId: string; revisions: readonly Record<string, unknown>[]; safetyResults: readonly unknown[]; checklistResponses: readonly unknown[]; gateApprovals: readonly unknown[] };
    const revision = mission.revisions.find((candidate) => candidate.id === revisionId);
    if (revision === undefined) throw new SafeModeError(404, "REVISION_NOT_FOUND", "mission revision was not found");
    const events = await this.audit.queryAudit({ missionRevisionId: revisionId });
    const payload = { revision, safetyResults: mission.safetyResults.filter((result) => (result as { missionRevisionId?: string }).missionRevisionId === revisionId), checklistResponses: mission.checklistResponses.filter((response) => (response as { revisionId?: string }).revisionId === revisionId), gateApprovals: mission.gateApprovals.filter((approval) => (approval as { missionRevisionId?: string }).missionRevisionId === revisionId) };
    return Object.freeze({ exportSchemaVersion: "1.0", exportId: `export:${revisionId}:${this.now()}`, missionId: mission.missionId, revisionId, exportedAtUtc: this.now(), ...payload, auditManifest: { eventCount: events.length, eventHashes: events.map((event) => event.hash) }, hashes: { payloadSha256: hashPayload(payload) } });
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
}

class PackageVerificationError extends Error {
  public constructor(public readonly report: VerificationReport) {
    super(report.checks.find((check) => check.status === "fail")?.reason ?? "package verification failed");
    this.name = "PackageVerificationError";
  }
}
