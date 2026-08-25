import type { FastifyInstance } from "fastify";
import { sendRouteError } from "./errors.js";
import type { MissionService } from "../services/mission-service.js";
import { forbid, requirePrincipal } from "../auth/http.js";
import { gateContext, hasMissionAssignment, isSupportedGate } from "./authorization.js";

export function registerGateRoutes(app: FastifyInstance, service: MissionService): void {
  app.post<{ Params: { revisionId: string; gate: string } }>("/api/revisions/:revisionId/gates/:gate", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      if (!isSupportedGate(request.params.gate)) return reply.code(400).send({ error: "INVALID_GATE", message: "gate is not supported" });
      const missionId = service.missionIdForRevision(request.params.revisionId);
      if (!hasMissionAssignment(principal, missionId)) return forbid(reply, "mission assignment is required");
      const context = gateContext(principal, request.params.gate);
      if (context === undefined) return forbid(reply, "the exact assigned gate role is required");
      if (principal.requiresReauthentication) return forbid(reply, "fresh re-authentication is required for gate decisions");
      const approval = await service.recordGateDecision(request.params.revisionId, request.params.gate, request.body, context);
      return reply.code(201).send(approval);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });

  app.get<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/safety-result", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      const missionId = service.missionIdForRevision(request.params.revisionId);
      if (!principal.roles.includes("reviewer") && !hasMissionAssignment(principal, missionId)) {
        return forbid(reply, "mission assignment or reviewer visibility is required");
      }
      return reply.code(200).send(service.getSafetyResult(request.params.revisionId));
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}
