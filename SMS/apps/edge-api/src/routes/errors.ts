import type { FastifyReply } from "fastify";
import { MissionServiceError } from "../services/mission-service.js";

export function sendRouteError(reply: FastifyReply, error: unknown): FastifyReply {
  if (error instanceof MissionServiceError) {
    return reply.code(error.statusCode).send({ error: error.code, message: error.message });
  }
  const message = error instanceof Error ? error.message : "unexpected edge service error";
  return reply.code(500).send({ error: "INTERNAL_ERROR", message });
}
