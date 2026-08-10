import type { FastifyInstance } from "fastify";

const WRITE_METHODS = new Set(["DELETE", "PATCH", "POST", "PUT"]);
const RESEARCH_ONLY_FIELDS = new Set([
  "conditionassignment",
  "consentversion",
  "ethicsapprovalid",
  "participantcode",
  "protocolid",
  "researchsessionid",
]);

function containsResearchDomain(value: unknown, visited: WeakSet<object>): boolean {
  if (value === null || typeof value !== "object") return false;
  if (visited.has(value)) return false;
  visited.add(value);

  if (Array.isArray(value)) return value.some((item) => containsResearchDomain(item, visited));

  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const normalizedKey = key.toLowerCase();
    if (RESEARCH_ONLY_FIELDS.has(normalizedKey)) return true;
    if (normalizedKey === "datadomain" && child === "research") return true;
    if (normalizedKey === "nondispatchable" && child === true) return true;
    if (containsResearchDomain(child, visited)) return true;
  }
  return false;
}

/** Reject research-domain records before any operational route can persist them. */
export function isResearchDomainPayload(value: unknown): boolean {
  return containsResearchDomain(value, new WeakSet());
}

export function registerOperationalDataBoundary(app: FastifyInstance): void {
  app.addHook("preValidation", async (request, reply) => {
    if (!request.url.startsWith("/api/") || !WRITE_METHODS.has(request.method)) return;
    if (!isResearchDomainPayload(request.body)) return;
    return reply.code(400).send({
      error: "RESEARCH_DATA_DOMAIN_FORBIDDEN",
      message: "research-domain records cannot enter operational storage",
    });
  });
}
