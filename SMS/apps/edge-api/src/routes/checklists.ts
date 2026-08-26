import type { FastifyInstance } from "fastify";
import { sendRouteError } from "./errors.js";
import type { MissionService } from "../services/mission-service.js";
import { forbid, requirePrincipal } from "../auth/http.js";
import { hasMissionAssignment, serviceContext } from "./authorization.js";

export function registerChecklistRoutes(app: FastifyInstance, service: MissionService): void {
  app.post<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/checklist-responses", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      const missionId = service.missionIdForRevision(request.params.revisionId);
      if (!hasMissionAssignment(principal, missionId)) return forbid(reply, "mission assignment is required");
      const response = await service.recordChecklistResponse(request.params.revisionId, request.body, serviceContext(principal));
      return reply.code(201).send(response);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}
