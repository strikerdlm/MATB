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

async function buildReadinessReport(database: EdgeDatabase, audit: AuditLedger, tlsConfigured: boolean, exportKeyConfigured: boolean): Promise<ReadinessReport> {
  const integrity = database.integrityCheck();
  const migrationsReady = database.schemaVersion() === SCHEMA_VERSION;
  const auditReport = await audit.verifyAuditChain();
  const sql = database.sql();
  const trustAnchors = Number((sql.prepare("SELECT COUNT(*) AS count FROM trusted_keys").get() as { count: number }).count) > 0;
  const activeRole = (role: string): boolean => sql.prepare("SELECT 1 AS present FROM active_package_roles WHERE role = ?").get(role) !== undefined;
  const bootstrapAdministrator = sql.prepare(`SELECT 1 AS present FROM identities i
    JOIN identity_roles r ON r.user_id = i.user_id
    WHERE r.role = 'administrator' AND i.disabled_at_utc IS NULL LIMIT 1`).get() !== undefined;
  const checks = {
    database: integrity.ok ? { status: "ok" as const } : { status: "pending" as const, detail: integrity.detail },
    migrations: migrationsReady
      ? { status: "ok" as const }
      : { status: "pending" as const, detail: "database migrations are incomplete" },
    audit: auditReport.ok && !audit.isReadOnlySafeMode() ? { status: "ok" as const } : { status: "pending" as const, detail: "audit chain validation failed" },
    tls: tlsConfigured ? { status: "ok" as const } : { status: "pending" as const, detail: "TLS material is not configured" },
    exportKey: exportKeyConfigured ? { status: "ok" as const } : { status: "pending" as const, detail: "runtime export key is not configured" },
    trustAnchors: trustAnchors ? { status: "ok" as const } : { status: "pending" as const, detail: "trusted package keys are not configured" },
    activeTerminology: activeRole("terminology") ? { status: "ok" as const } : { status: "pending" as const, detail: "active terminology package is not configured" },
    activePolicy: activeRole("policy") ? { status: "ok" as const } : { status: "pending" as const, detail: "active policy package is not configured" },
    bootstrapAdministrator: bootstrapAdministrator ? { status: "ok" as const } : { status: "pending" as const, detail: "bootstrap administrator is not configured" },
  };
  const technicalReady = Object.values(checks).every(({ status }) => status === "ok");
  return { status: technicalReady ? "ready" : "not_ready", technicalReady, operationalReady: false, checks };
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
  const edgeDatabase = openDatabase(edgeConfig.databaseUrl, edgeConfig.lockTimeoutMs);
  const auditLedger = new AuditLedger({ database: edgeDatabase });
  const now = dependencies.now ?? (() => new Date().toISOString());
  if (!edgeDatabase.integrityCheck().ok || !(await auditLedger.verifyAuditChain()).ok) await auditLedger.simulateWriteFailure();
  const runtimeLease = new RuntimeLease(edgeDatabase, { holderId: `edge-service:${process.pid}`, now, durationMs: 120_000 });
  runtimeLease.acquire();
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
  });

  registerOperationalDataBoundary(app);
  const defaults = createDefaultHttpAuthDependencies(edgeDatabase);
  registerHttpAuthentication(app, {
    identityStore: dependencies.identityStore ?? defaults.identityStore,
    sessionManager: dependencies.sessionManager ?? defaults.sessionManager,
  });

  app.get("/healthz", async () => ({
    status: "ok",
    service: "fac-isr-edge-api",
    internet: edgeConfig.internet,
  }));

  app.get("/readyz", async (_request, reply) => {
    const report = await buildReadinessReport(
      edgeDatabase,
      auditLedger,
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
