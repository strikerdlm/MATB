import type { FastifyInstance } from "fastify";
import { sendRouteError } from "./errors.js";
import type { MissionService } from "../services/mission-service.js";

export function registerPostflightRoutes(app: FastifyInstance, service: MissionService): void {
  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/postflight", async (request, reply) => {
    try {
      const record = await service.recordPostflight(request.params.revisionId, request.body);
      return reply.code(201).send(record);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });

  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/occurrences", async (request, reply) => {
    try {
      const record = await service.recordOccurrence(request.params.revisionId, request.body);
      return reply.code(201).send(record);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}
