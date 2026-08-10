import type { FastifyInstance } from "fastify";
import { sendRouteError } from "./errors.js";
import type { MissionService } from "../services/mission-service.js";

export function registerChecklistRoutes(app: FastifyInstance, service: MissionService): void {
  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/checklist-responses", async (request, reply) => {
    try {
      const response = await service.recordChecklistResponse(request.params.revisionId, request.body);
      return reply.code(201).send(response);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}
