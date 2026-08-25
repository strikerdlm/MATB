import type { FastifyInstance } from "fastify";
import { TelemetryServiceError } from "../services/telemetry-service.js";
import type { TelemetryService } from "../services/telemetry-service.js";
import type { MissionService } from "../services/mission-service.js";
import { canReadMission, forbid, requirePrincipal } from "../auth/http.js";
import { sendRouteError } from "./errors.js";

export function registerTelemetryRoutes(app: FastifyInstance, service: TelemetryService, missionService: MissionService): void {
  app.post("/api/telemetry/replay", async (request, reply) => {
    try {
      const result = await service.replay(request.body);
      return reply.code(201).send(result);
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/telemetry/stream", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      const missionId = missionService.missionIdForRevision(request.params.revisionId);
      if (!canReadMission(principal, missionId)) return forbid(reply, "mission assignment or reviewer visibility is required");
      const events = service.stream(request.params.revisionId);
      const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
      return reply.header("content-type", "text/event-stream; charset=utf-8").code(200).send(body);
    } catch (error) {
      return sendRouteError(reply, error);
    }
  });
}

function sendError(reply: { code(statusCode: number): { send(payload: unknown): unknown } }, error: unknown): unknown {
  if (error instanceof TelemetryServiceError) return reply.code(error.statusCode).send({ error: error.code, message: error.message });
  return reply.code(500).send({ error: "INTERNAL_ERROR", message: error instanceof Error ? error.message : "unexpected telemetry error" });
}
