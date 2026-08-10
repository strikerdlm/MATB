import type { FastifyInstance } from "fastify";
import { sendRouteError } from "./errors.js";
import type { MissionService } from "../services/mission-service.js";

export function registerGateRoutes(app: FastifyInstance, service: MissionService): void {
  app.post<{ Params: { revisionId: string; gate: string } }>("/api/revisions/:revisionId/gates/:gate", async (request, reply) => {
    try {
      const approval = await service.recordGateDecision(request.params.revisionId, request.params.gate, request.body);
      return reply.code(201).send(approval);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });

  app.get<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/safety-result", async (request, reply) => {
    try {
      return reply.code(200).send(service.getSafetyResult(request.params.revisionId));
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}
