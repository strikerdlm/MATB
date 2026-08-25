import type { FastifyInstance } from "fastify";
import type { SafeModeService } from "../services/safe-mode.js";
import { requirePrincipal } from "../auth/http.js";

export function registerPackageRoutes(app: FastifyInstance, service: SafeModeService): void {
  app.get("/api/packages", async (request, reply) => {
    requirePrincipal(request);
    return reply.code(200).send(service.getPackageState());
  });

  app.get("/api/packages/quarantine", async (request, reply) => {
    requirePrincipal(request);
    return reply.code(200).send({ packages: service.getQuarantine() });
  });
}
