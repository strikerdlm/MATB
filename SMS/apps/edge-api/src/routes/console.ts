import type { FastifyInstance } from "fastify";
import { requirePrincipal } from "../auth/http.js";
import type { AuditLedger } from "../audit/ledger.js";
import type { MissionService } from "../services/mission-service.js";

export function registerConsoleReadRoutes(app: FastifyInstance, missions: MissionService, audit: AuditLedger): void {
  app.get("/api/missions", async (request, reply) => {
    const principal = requirePrincipal(request);
    const visibility = principal.roles.includes("reviewer") || principal.missionIds.includes("*")
      ? undefined
      : new Set(principal.missionIds);
    return reply.code(200).send({ missions: missions.listMissions(visibility) });
  });

  app.get("/api/audit/health", async (request, reply) => {
    requirePrincipal(request);
    const report = await audit.verifyAuditChain();
    const events = report.ok ? await audit.queryAudit() : [];
    const lastEventHash = events.at(-1)?.hash;
    return reply.code(200).send({
      state: report.ok && !audit.isReadOnlySafeMode() ? "healthy" : "safe-mode",
      eventCount: events.length,
      ...(lastEventHash === undefined ? {} : { lastEventHash }),
    });
  });
}
