import type { FastifyInstance } from "fastify";
import { SafeModeError, type SafeModeService } from "../services/safe-mode.js";

export function registerPackageRoutes(app: FastifyInstance, service: SafeModeService): void {
  app.post("/api/packages/import", async (request, reply) => {
    try {
      const record = await service.importPackage(request.body);
      return reply.code(record.state === "quarantined" ? 422 : 201).send(record);
    } catch (error) {
      if (error instanceof SafeModeError) return reply.code(error.statusCode).send({ error: error.code, state: error.state, message: error.message });
      return reply.code(500).send({ error: "INTERNAL_ERROR", message: error instanceof Error ? error.message : "unexpected package import error" });
    }
  });

  app.get("/api/packages/quarantine", async (_request, reply) => reply.code(200).send({ packages: service.getQuarantine() }));
}
