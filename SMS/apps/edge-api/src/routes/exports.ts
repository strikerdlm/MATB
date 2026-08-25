import type { FastifyInstance } from "fastify";
import { SafeModeError, type SafeModeService } from "../services/safe-mode.js";
import { canReadMission, forbid, requirePrincipal } from "../auth/http.js";
import { serviceContext } from "./authorization.js";

export function registerExportRoutes(app: FastifyInstance, service: SafeModeService, missionService: { missionIdForRevision(revisionId: string): string }): void {
  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/export", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      const missionId = missionService.missionIdForRevision(request.params.revisionId);
      if ((!principal.roles.includes("commander") && !principal.roles.includes("reviewer")) || !canReadMission(principal, missionId)) return forbid(reply, "commander or reviewer authority is required");
      if (principal.requiresReauthentication) return reply.code(403).send({ error: "REAUTHENTICATION_REQUIRED", message: "fresh re-authentication is required" });
      return reply.code(200).send(await service.exportRevision(request.params.revisionId, missionId, serviceContext(principal)));
    } catch (error) {
      if (error instanceof SafeModeError) return reply.code(error.statusCode).send({ error: error.code, state: error.state, message: error.statusCode >= 500 ? "export could not be created" : error.message });
      return reply.code(500).send({ error: "EXPORT_FAILED", message: "export could not be created" });
    }
  });

  app.post("/api/mission-import/review", async (request, reply) => reply.code(200).send(service.reviewMissionImport(request.body)));
}
