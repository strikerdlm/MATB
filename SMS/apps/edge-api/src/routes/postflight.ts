import type { FastifyInstance } from "fastify";
import { sendRouteError } from "./errors.js";
import type { MissionService } from "../services/mission-service.js";
import { forbid, requirePrincipal } from "../auth/http.js";
import { hasMissionAssignment, serviceContext } from "./authorization.js";

export function registerPostflightRoutes(app: FastifyInstance, service: MissionService): void {
  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/postflight", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      const missionId = service.missionIdForRevision(request.params.revisionId);
      if (!hasMissionAssignment(principal, missionId)) return forbid(reply, "mission assignment is required");
      const record = await service.recordPostflight(request.params.revisionId, request.body, serviceContext(principal));
      return reply.code(201).send(record);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });

  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/occurrences", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      const missionId = service.missionIdForRevision(request.params.revisionId);
      if (!hasMissionAssignment(principal, missionId)) return forbid(reply, "mission assignment is required");
      const record = await service.recordOccurrence(request.params.revisionId, request.body, serviceContext(principal));
      return reply.code(201).send(record);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}
