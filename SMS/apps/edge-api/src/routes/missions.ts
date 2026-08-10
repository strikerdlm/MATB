import type { FastifyInstance } from "fastify";
import { sendRouteError } from "./errors.js";
import type { MissionService } from "../services/mission-service.js";

export function registerMissionRoutes(app: FastifyInstance, service: MissionService): void {
  app.post("/api/missions", async (request, reply) => {
    try {
      const revision = await service.createMission(request.body);
      return reply.code(201).send(revision);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });

  app.get<{ Params: { missionId: string } }>("/api/missions/:missionId", async (request, reply) => {
    try {
      return reply.code(200).send(service.getMission(request.params.missionId));
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });

  app.post<{ Params: { missionId: string } }>("/api/missions/:missionId/revisions", async (request, reply) => {
    try {
      const revision = await service.createRevision(request.params.missionId, request.body);
      return reply.code(201).send(revision);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}
