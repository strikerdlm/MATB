import { createPublicKey } from "node:crypto";
import { readFile } from "node:fs/promises";
import Fastify, { type FastifyInstance } from "fastify";
import { createConfig, type EdgeConfig, type EdgeConfigInput } from "./config.js";
import { openDatabase, type EdgeDatabase } from "./db/migrate.js";
import { SCHEMA_VERSION } from "./db/schema.js";
import { AuditLedger } from "./audit/ledger.js";
import { registerChecklistRoutes } from "./routes/checklists.js";
import { registerExportRoutes } from "./routes/exports.js";
import { registerGateRoutes } from "./routes/gates.js";
import { registerMissionRoutes } from "./routes/missions.js";
import { registerPackageRoutes } from "./routes/packages.js";
import { registerPostflightRoutes } from "./routes/postflight.js";
import { registerTelemetryRoutes } from "./routes/telemetry.js";
import { MissionService } from "./services/mission-service.js";
import { TelemetryService } from "./services/telemetry-service.js";
import { SafeModeService, SqliteTrustedKeyStore, type TrustedKeyStore } from "./services/safe-mode.js";
import { ActivePackageSafetyResolver, DeterministicSafetyEvaluationProvider, type SafetyEvaluationProvider } from "./services/safety-evaluation.js";
import { registerOperationalDataBoundary } from "./data-boundary.js";
import {
  createDefaultHttpAuthDependencies,
  registerHttpAuthentication,
  type HttpAuthDependencies,
} from "./auth/http.js";
import { RuntimeLease } from "./admin/runtime-lease.js";
import { MaintenanceLock } from "./admin/maintenance-lock.js";

interface ReadinessCheck {
  readonly status: "ok" | "pending";
  readonly detail?: string;
}

interface ReadinessReport {
  readonly status: "ready" | "not_ready";
  readonly technicalReady: boolean;
  readonly operationalReady: false;
  readonly checks: {
    readonly database: ReadinessCheck;
    readonly migrations: ReadinessCheck;
    readonly audit: ReadinessCheck;
    readonly tls: ReadinessCheck;
    readonly exportKey: ReadinessCheck;
    readonly trustAnchors: ReadinessCheck;
    readonly activeTerminology: ReadinessCheck;
    readonly activePolicy: ReadinessCheck;
    readonly bootstrapAdministrator: ReadinessCheck;
  };
}

export interface EdgeServer extends FastifyInstance {
  readonly edgeConfig: EdgeConfig;
  readonly edgeDatabase: EdgeDatabase;
  readonly auditLedger: AuditLedger;
  readonly missionService: MissionService;
  readonly telemetryService: TelemetryService;
  readonly safeModeService: SafeModeService;
}

export interface EdgeServerDependencies extends Partial<HttpAuthDependencies> {
  readonly safetyEvaluationProvider?: SafetyEvaluationProvider;
  readonly trustedKeyStore?: TrustedKeyStore;
  readonly now?: () => string;
  readonly readiness?: {
    readonly tlsConfigured?: boolean;
    readonly exportKeyConfigured?: boolean;
  };
}

async function buildReadinessReport(database: EdgeDatabase, audit: AuditLedger, packages: SafeModeService, identityStore: HttpAuthDependencies["identityStore"], sessionManager: HttpAuthDependencies["sessionManager"], tlsConfigured: boolean, exportKeyConfigured: boolean): Promise<ReadinessReport> {
  const integrity = database.integrityCheck();
  const migrationsReady = database.schemaVersion() === SCHEMA_VERSION;
  const auditReport = await audit.verifyAuditChain();
  const sql = database.sql();
  let trustAnchors = true;
  const trustRows = sql.prepare("SELECT scope, algorithm, public_key_pem FROM trusted_keys").all() as Array<{ scope: string; algorithm: string; public_key_pem: string }>;
  if (trustRows.length === 0) trustAnchors = false;
  for (const row of trustRows) {
    try {
      const keyType = createPublicKey(row.public_key_pem).asymmetricKeyType;
      if (!(["regulatory", "policy", "map", "terrain", "airspace", "aip", "weather", "notam", "terminology", "software"] as const).includes(row.scope as never)) throw new Error("unsupported scope");
      if ((row.algorithm === "ed25519" && keyType !== "ed25519") || (row.algorithm === "rsa-sha256" && keyType !== "rsa" && keyType !== "rsa-pss")) throw new Error("algorithm mismatch");
      if (row.algorithm !== "ed25519" && row.algorithm !== "rsa-sha256") throw new Error("unsupported algorithm");
    } catch {
      trustAnchors = false;
    }
  }
  let activePackages: Awaited<ReturnType<SafeModeService["getPackageState"]>> = { active: [], quarantined: [] };
  try {
    activePackages = await packages.getPackageState();
  } catch {
    // Keep readiness pending below.
  }
  const activeRole = (role: string): boolean => activePackages.active.filter((record) => record.manifest?.kind === role).length === 1;
  const bootstrapAdministrator = sql.prepare(`SELECT 1 AS present FROM identities i
    JOIN identity_roles r ON r.user_id = i.user_id
    JOIN credential_versions c ON c.user_id = i.user_id AND c.retired_at_utc IS NULL
    WHERE r.role = 'administrator' AND i.disabled_at_utc IS NULL AND length(c.salt) >= 16 AND length(c.password_hash) >= 32 LIMIT 1`).get() !== undefined;
  const domainStateValid = !packages.isReadOnlySafeMode() && !identityStore.isReadOnlySafeMode() && !sessionManager.isReadOnlySafeMode();
  const checks = {
    database: integrity.ok && domainStateValid ? { status: "ok" as const } : { status: "pending" as const, detail: integrity.ok ? "persisted operational state is corrupt; service is read-only" : integrity.detail },
    migrations: migrationsReady
      ? { status: "ok" as const }
      : { status: "pending" as const, detail: "database migrations are incomplete" },
    audit: auditReport.ok && !audit.isReadOnlySafeMode() ? { status: "ok" as const } : { status: "pending" as const, detail: "audit chain validation failed" },
    tls: tlsConfigured ? { status: "ok" as const } : { status: "pending" as const, detail: "TLS material is not configured" },
    exportKey: exportKeyConfigured ? { status: "ok" as const } : { status: "pending" as const, detail: "runtime export key is not configured" },
    trustAnchors: trustAnchors ? { status: "ok" as const } : { status: "pending" as const, detail: "usable trusted package keys are not configured" },
    activeTerminology: activeRole("terminology") ? { status: "ok" as const } : { status: "pending" as const, detail: "active terminology package is not configured" },
    activePolicy: activeRole("policy") ? { status: "ok" as const } : { status: "pending" as const, detail: "active policy package is not configured" },
    bootstrapAdministrator: bootstrapAdministrator ? { status: "ok" as const } : { status: "pending" as const, detail: "bootstrap administrator is not configured" },
  };
  const technicalReady = Object.values(checks).every(({ status }) => status === "ok");
  return { status: technicalReady ? "ready" : "not_ready", technicalReady, operationalReady: false, checks };
}

function buildDegradedServer(config: EdgeConfig, https: { readonly cert: Buffer; readonly key: Buffer } | undefined, error: unknown): EdgeServer {
  const app = Fastify({ logger: false, ...(https === undefined ? {} : { https }) }) as unknown as EdgeServer;
  Object.defineProperty(app, "edgeConfig", { value: config, enumerable: false });
  const detail = error instanceof Error ? error.message : String(error);
  app.get("/healthz", async () => ({ status: "ok", service: "fac-isr-edge-api", internet: config.internet, degraded: true }));
  app.get("/readyz", async (_request, reply) => reply.code(503).send({
    status: "not_ready", technicalReady: false, operationalReady: false,
    checks: {
      database: { status: "pending", detail }, migrations: { status: "pending" }, audit: { status: "pending" },
      tls: { status: https === undefined ? "pending" : "ok" }, exportKey: { status: "pending" }, trustAnchors: { status: "pending" },
      activeTerminology: { status: "pending" }, activePolicy: { status: "pending" }, bootstrapAdministrator: { status: "pending" },
    },
  }));
  app.all("/api/*", async (_request, reply) => reply.code(503).send({ error: "READ_ONLY_DEGRADED_STARTUP", message: "operational state is unavailable" }));
  return app;
}

async function loadTlsMaterial(config: EdgeConfig): Promise<{ readonly cert: Buffer; readonly key: Buffer } | undefined> {
  if (config.tls === undefined) return undefined;
  try {
    const [cert, key] = await Promise.all([
      readFile(config.tls.certPath),
      readFile(config.tls.keyPath),
    ]);
    return { cert, key };
  } catch (error) {
    throw new Error(`TLS material could not be loaded: ${error instanceof Error ? error.message : String(error)}`);
  }
}

async function exportKeyIsReadable(config: EdgeConfig): Promise<boolean> {
  if (config.exportKeyPath === undefined) return false;
  try {
    return (await readFile(config.exportKeyPath)).byteLength > 0;
  } catch {
    return false;
  }
}

export async function buildServer(input: EdgeConfigInput = {}, dependencies: EdgeServerDependencies = {}): Promise<EdgeServer> {
  const edgeConfig = createConfig(input);
  const https = await loadTlsMaterial(edgeConfig);
  const exportKeyConfigured = await exportKeyIsReadable(edgeConfig);
  const maintenanceLock = new MaintenanceLock(edgeConfig.databaseUrl, edgeConfig.lockTimeoutMs);
  maintenanceLock.acquire();
  let edgeDatabase: EdgeDatabase;
  try {
    edgeDatabase = openDatabase(edgeConfig.databaseUrl, edgeConfig.lockTimeoutMs, { maintenanceLock });
  } catch (error) {
    maintenanceLock.release();
    return buildDegradedServer(edgeConfig, https, error);
  }
  const auditLedger = new AuditLedger({ database: edgeDatabase });
  const now = dependencies.now ?? (() => new Date().toISOString());
  if (!edgeDatabase.integrityCheck().ok || !(await auditLedger.verifyAuditChain()).ok) await auditLedger.simulateWriteFailure();
  // Runtime ownership uses the process wall clock, independent of injectable
  // domain clocks used to evaluate packages and mission records.
  const runtimeLease = new RuntimeLease(edgeDatabase, { holderId: `edge-service:${process.pid}`, durationMs: 120_000 });
  try {
    runtimeLease.acquire();
  } catch (error) {
    edgeDatabase.close();
    maintenanceLock.release();
    throw error;
  }
  const leaseTimer = setInterval(() => {
    try {
      runtimeLease.renew();
    } catch {
      void auditLedger.simulateWriteFailure();
    }
  }, 40_000);
  leaseTimer.unref();
  const missionTarget: { current?: MissionService } = {};
  const missionBoundary = {
    markSafetyEvaluationsStale: async (...args: Parameters<MissionService["markSafetyEvaluationsStale"]>) => requireMissionTarget(missionTarget).markSafetyEvaluationsStale(...args),
    stageSafetyEvaluationsStale: (...args: Parameters<MissionService["stageSafetyEvaluationsStale"]>) => requireMissionTarget(missionTarget).stageSafetyEvaluationsStale(...args),
    getMission: (...args: Parameters<MissionService["getMission"]>) => requireMissionTarget(missionTarget).getMission(...args),
  };
  const safeModeService = new SafeModeService({ database: edgeDatabase, packageDirectory: edgeConfig.packageDirectory, auditLedger, missionService: missionBoundary, now, trustedKeyStore: dependencies.trustedKeyStore ?? new SqliteTrustedKeyStore(edgeDatabase) });
  const resolver = new ActivePackageSafetyResolver(safeModeService);
  const safetyEvaluationProvider = dependencies.safetyEvaluationProvider ?? new DeterministicSafetyEvaluationProvider({ now, resolve: resolver.resolve.bind(resolver) });
  const missionService = new MissionService({ auditLedger, database: edgeDatabase, now, safetyEvaluationProvider });
  missionTarget.current = missionService;
  const telemetryService = new TelemetryService();
  const defaults = createDefaultHttpAuthDependencies(edgeDatabase);
  const authDependencies = {
    identityStore: dependencies.identityStore ?? defaults.identityStore,
    sessionManager: dependencies.sessionManager ?? defaults.sessionManager,
  };
  if (safeModeService.isReadOnlySafeMode() || authDependencies.identityStore.isReadOnlySafeMode() || authDependencies.sessionManager.isReadOnlySafeMode()) {
    clearInterval(leaseTimer);
    runtimeLease.release();
    edgeDatabase.close();
    maintenanceLock.release();
    return buildDegradedServer(edgeConfig, https, new Error("persisted operational domain validation failed"));
  }
  const app = Fastify({ logger: false, ...(https === undefined ? {} : { https }) }) as unknown as EdgeServer;
  Object.defineProperties(app, {
    edgeConfig: { value: edgeConfig, enumerable: false },
    edgeDatabase: { value: edgeDatabase, enumerable: false },
    auditLedger: { value: auditLedger, enumerable: false },
    missionService: { value: missionService, enumerable: false },
    telemetryService: { value: telemetryService, enumerable: false },
    safeModeService: { value: safeModeService, enumerable: false },
  });

  app.addHook("onClose", async () => {
    clearInterval(leaseTimer);
    runtimeLease.release();
    edgeDatabase.close();
    maintenanceLock.release();
  });

  registerOperationalDataBoundary(app);
  registerHttpAuthentication(app, authDependencies);

  app.get("/healthz", async () => ({
    status: "ok",
    service: "fac-isr-edge-api",
    internet: edgeConfig.internet,
  }));

  app.get("/readyz", async (_request, reply) => {
    const report = await buildReadinessReport(
      edgeDatabase,
      auditLedger,
      safeModeService,
      authDependencies.identityStore,
      authDependencies.sessionManager,
      dependencies.readiness?.tlsConfigured ?? https !== undefined,
      dependencies.readiness?.exportKeyConfigured ?? exportKeyConfigured,
    );
    return reply.code(report.technicalReady ? 200 : 503).send(report);
  });

  registerMissionRoutes(app, missionService);
  registerChecklistRoutes(app, missionService);
  registerGateRoutes(app, missionService);
  registerPostflightRoutes(app, missionService);
  registerTelemetryRoutes(app, telemetryService, missionService);
  registerPackageRoutes(app, safeModeService);
  registerExportRoutes(app, safeModeService);

  return app;
}

function requireMissionTarget(target: { current?: MissionService }): MissionService {
  if (target.current === undefined) throw new Error("mission service is not initialized");
  return target.current;
}
