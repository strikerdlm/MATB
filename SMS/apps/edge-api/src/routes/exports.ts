import type { FastifyInstance } from "fastify";
import { SafeModeError, type SafeModeService } from "../services/safe-mode.js";

export function registerExportRoutes(app: FastifyInstance, service: SafeModeService): void {
  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/export", async (request, reply) => {
    try {
      return reply.code(200).send(await service.exportRevision(request.params.revisionId));
    } catch (error) {
      if (error instanceof SafeModeError) return reply.code(error.statusCode).send({ error: error.code, state: error.state, message: error.message });
      return reply.code(500).send({ error: "EXPORT_FAILED", message: error instanceof Error ? error.message : "export failed" });
    }
  });

  app.post("/api/mission-import/review", async (request, reply) => reply.code(200).send(service.reviewMissionImport(request.body)));
}
