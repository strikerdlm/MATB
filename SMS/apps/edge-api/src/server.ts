import Fastify, { type FastifyInstance } from "fastify";
import { createConfig, type EdgeConfig, type EdgeConfigInput } from "./config.js";
import { openDatabase, type EdgeDatabase } from "./db/migrate.js";
import { SCHEMA_VERSION } from "./db/schema.js";
import { AuditLedger } from "./audit/ledger.js";
import { registerChecklistRoutes } from "./routes/checklists.js";
import { registerGateRoutes } from "./routes/gates.js";
import { registerMissionRoutes } from "./routes/missions.js";
import { registerPostflightRoutes } from "./routes/postflight.js";
import { MissionService } from "./services/mission-service.js";

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

export async function buildServer(input: EdgeConfigInput = {}): Promise<EdgeServer> {
  const edgeConfig = createConfig(input);
  const edgeDatabase = openDatabase(edgeConfig.databaseUrl, edgeConfig.lockTimeoutMs);
  const auditLedger = new AuditLedger({ database: edgeDatabase });
  const missionService = new MissionService({ auditLedger, database: edgeDatabase });
  const app = Fastify({ logger: false }) as unknown as EdgeServer;
  Object.defineProperties(app, {
    edgeConfig: { value: edgeConfig, enumerable: false },
    edgeDatabase: { value: edgeDatabase, enumerable: false },
    auditLedger: { value: auditLedger, enumerable: false },
    missionService: { value: missionService, enumerable: false },
  });

  app.addHook("onClose", async () => {
    edgeDatabase.close();
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

  return app;
}
