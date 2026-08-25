import type { FastifyInstance } from "fastify";
import { SafeModeError, type SafeModeService } from "../services/safe-mode.js";
import { canReadMission, forbid, requirePrincipal } from "../auth/http.js";
import { serviceContext } from "./authorization.js";

export function registerExportRoutes(app: FastifyInstance, service: SafeModeService): void {
  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/export", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      const missionId = request.params.revisionId.split(":", 1)[0] ?? request.params.revisionId;
      if (!canReadMission(principal, missionId)) return forbid(reply, "mission assignment or reviewer visibility is required");
      return reply.code(200).send(await service.exportRevision(request.params.revisionId, serviceContext(principal)));
    } catch (error) {
      if (error instanceof SafeModeError) return reply.code(error.statusCode).send({ error: error.code, state: error.state, message: error.message });
      return reply.code(500).send({ error: "EXPORT_FAILED", message: error instanceof Error ? error.message : "export failed" });
    }
  });

  app.post("/api/mission-import/review", async (request, reply) => reply.code(200).send(service.reviewMissionImport(request.body)));
}
