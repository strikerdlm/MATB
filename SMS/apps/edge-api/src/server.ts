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
import { InMemoryTrustedKeyStore, SafeModeService, type TrustedKeyStore } from "./services/safe-mode.js";
import { ActivePackageSafetyResolver, DeterministicSafetyEvaluationProvider, type SafetyEvaluationProvider } from "./services/safety-evaluation.js";
import { registerOperationalDataBoundary } from "./data-boundary.js";
import {
  createDefaultHttpAuthDependencies,
  registerHttpAuthentication,
  type HttpAuthDependencies,
} from "./auth/http.js";

interface ReadinessCheck {
  readonly status: "ok" | "pending";
  readonly detail?: string;
}

interface ReadinessReport {
  readonly status: "ready" | "not_ready";
  readonly checks: {
    readonly database: ReadinessCheck;
    readonly migrations: ReadinessCheck;
    readonly signingKeys: ReadinessCheck;
    readonly terminology: ReadinessCheck;
    readonly policyPackage: ReadinessCheck;
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
}

function buildReadinessReport(database: EdgeDatabase): ReadinessReport {
  const migrationsReady = database.schemaVersion() === SCHEMA_VERSION;
  const checks = {
    database: { status: "ok" as const },
    migrations: migrationsReady
      ? { status: "ok" as const }
      : { status: "pending" as const, detail: "database migrations are incomplete" },
    signingKeys: { status: "pending" as const, detail: "local signing keys are not configured" },
    terminology: { status: "pending" as const, detail: "active terminology package is not configured" },
    policyPackage: { status: "pending" as const, detail: "active policy package is not configured" },
  };
  const ready = Object.values(checks).every(({ status }) => status === "ok");
  return { status: ready ? "ready" : "not_ready", checks };
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

export async function buildServer(input: EdgeConfigInput = {}, dependencies: EdgeServerDependencies = {}): Promise<EdgeServer> {
  const edgeConfig = createConfig(input);
  const https = await loadTlsMaterial(edgeConfig);
  const edgeDatabase = openDatabase(edgeConfig.databaseUrl, edgeConfig.lockTimeoutMs);
  const auditLedger = new AuditLedger({ database: edgeDatabase });
  const now = dependencies.now ?? (() => new Date().toISOString());
  const missionTarget: { current?: MissionService } = {};
  const missionBoundary = {
    markSafetyEvaluationsStale: async (...args: Parameters<MissionService["markSafetyEvaluationsStale"]>) => requireMissionTarget(missionTarget).markSafetyEvaluationsStale(...args),
    getMission: (...args: Parameters<MissionService["getMission"]>) => requireMissionTarget(missionTarget).getMission(...args),
  };
  const safeModeService = new SafeModeService({ database: edgeDatabase, packageDirectory: edgeConfig.packageDirectory, auditLedger, missionService: missionBoundary, now, trustedKeyStore: dependencies.trustedKeyStore ?? new InMemoryTrustedKeyStore() });
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
    edgeDatabase.close();
  });

  registerOperationalDataBoundary(app);
  const defaults = createDefaultHttpAuthDependencies();
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
    const report = buildReadinessReport(edgeDatabase);
    return reply.code(report.status === "ready" ? 200 : 503).send(report);
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
