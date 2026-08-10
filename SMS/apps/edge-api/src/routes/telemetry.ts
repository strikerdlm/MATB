import type { FastifyInstance, FastifyRequest } from "fastify";
import { TelemetryServiceError } from "../services/telemetry-service.js";
import type { TelemetryService } from "../services/telemetry-service.js";

export function registerTelemetryRoutes(app: FastifyInstance, service: TelemetryService): void {
  app.post("/api/telemetry/replay", async (request, reply) => {
    if (!hasLocalSession(request)) return reply.code(401).send({ error: "LOCAL_SESSION_REQUIRED" });
    try {
      const result = await service.replay(request.body);
      return reply.code(201).send(result);
    } catch (error) {
      return sendError(reply, error);
    }
  });

  app.get<{ Params: { revisionId: string } }>("/api/revisions/:revisionId/telemetry/stream", async (request, reply) => {
    if (!hasLocalSession(request)) return reply.code(401).send({ error: "LOCAL_SESSION_REQUIRED" });
    const events = service.stream(request.params.revisionId);
    const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
    return reply.header("content-type", "text/event-stream; charset=utf-8").code(200).send(body);
  });
}

function hasLocalSession(request: FastifyRequest): boolean {
  const session = request.headers["x-local-session"];
  return typeof session === "string" && session.trim() !== "";
}

function sendError(reply: { code(statusCode: number): { send(payload: unknown): unknown } }, error: unknown): unknown {
  if (error instanceof TelemetryServiceError) return reply.code(error.statusCode).send({ error: error.code, message: error.message });
  return reply.code(500).send({ error: "INTERNAL_ERROR", message: error instanceof Error ? error.message : "unexpected telemetry error" });
}
