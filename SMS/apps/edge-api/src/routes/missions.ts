import type { FastifyInstance } from "fastify";
import { sendRouteError } from "./errors.js";
import type { MissionService } from "../services/mission-service.js";
import { canReadMission, forbid, requirePrincipal } from "../auth/http.js";
import { canManageMission, serviceContext } from "./authorization.js";

export function registerMissionRoutes(app: FastifyInstance, service: MissionService): void {
  app.post("/api/missions", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      if (!canManageMission(principal)) return forbid(reply, "commander or safety-officer role is required");
      const revision = await service.createMission(request.body, serviceContext(principal));
      return reply.code(201).send(revision);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });

  app.get<{ Params: { missionId: string } }>("/api/missions/:missionId", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      if (!canReadMission(principal, request.params.missionId)) return forbid(reply, "mission assignment or reviewer visibility is required");
      return reply.code(200).send(service.getMission(request.params.missionId));
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });

  app.post<{ Params: { missionId: string } }>("/api/missions/:missionId/revisions", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      if (!canManageMission(principal) || !canReadMission(principal, request.params.missionId)) {
        return forbid(reply, "assigned commander or safety-officer role is required");
      }
      const revision = await service.createRevision(request.params.missionId, request.body, serviceContext(principal));
      return reply.code(201).send(revision);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}
