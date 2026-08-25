import { Readable } from "node:stream";
import type { FastifyInstance, FastifyRequest } from "fastify";
import { TelemetryServiceError, type TelemetryPeerIdentity, type TelemetryService, type TelemetryIngestionResult } from "../services/telemetry-service.js";
import type { MissionService } from "../services/mission-service.js";
import { canReadMission, forbid, requirePrincipal } from "../auth/http.js";
import { sendRouteError } from "./errors.js";

const TELEMETRY_ROLES = new Set(["commander", "safety-officer", "maintainer", "operator", "observer", "reviewer"]);

export type TelemetryPeerIdentityProvider = (request: FastifyRequest) => TelemetryPeerIdentity;

export function tlsTelemetryPeerIdentity(request: FastifyRequest): TelemetryPeerIdentity {
  const socket = request.raw.socket as typeof request.raw.socket & {
    readonly authorized?: boolean;
    getPeerCertificate?(): { readonly fingerprint256?: string; readonly subject?: { readonly CN?: string } };
  };
  const certificate = socket.getPeerCertificate?.();
  const fingerprint = certificate?.fingerprint256?.replaceAll(":", "").toLowerCase();
  return Object.freeze({
    authorized: socket.authorized === true,
    ...(fingerprint === undefined ? {} : { fingerprintSha256: fingerprint }),
    ...(certificate?.subject?.CN === undefined ? {} : { subject: `CN=${certificate.subject.CN}` }),
  });
}

export function registerTelemetryRoutes(
  app: FastifyInstance,
  service: TelemetryService,
  missionService: MissionService,
  peerIdentity: TelemetryPeerIdentityProvider = tlsTelemetryPeerIdentity,
): void {
  app.post("/api/telemetry/ingest", async (request, reply) => {
    try {
      const peer = peerIdentity(request);
      service.authorizePeer(peer);
      const revisionId = (request.body as { revisionId?: unknown } | null)?.revisionId;
      const missionAircraftIds = typeof revisionId === "string" ? missionService.aircraftIdsForRevision(revisionId) : undefined;
      return reply.code(202).send(service.ingest(request.body, peer, missionAircraftIds));
    } catch (error) {
      return sendTelemetryError(reply, error);
    }
  });

  app.get<{ Params: { revisionId: string }; Querystring: { window?: string; follow?: string } }>("/api/revisions/:revisionId/telemetry/stream", async (request, reply) => {
    try {
      const principal = requirePrincipal(request);
      const missionId = missionService.missionIdForRevision(request.params.revisionId);
      if (!principal.roles.some((role) => TELEMETRY_ROLES.has(role)) || !canReadMission(principal, missionId)) {
        return forbid(reply, "an assigned operational, observer, or reviewer role is required");
      }
      const window = request.query.window === undefined ? 50 : Number(request.query.window);
      const snapshot = service.snapshot(request.params.revisionId, window);
      const follow = request.query.follow !== "false";
      let unsubscribe: () => void = () => undefined;
      const output = new Readable({
        read() { /* records are pushed by the telemetry service */ },
        destroy(error, callback) {
          unsubscribe();
          callback(error);
        },
      });
      const push = (record: TelemetryIngestionResult) => output.push(`data: ${JSON.stringify(record)}\n\n`);
      for (const record of snapshot) push(record);
      if (follow) {
        unsubscribe = service.subscribe(request.params.revisionId, push, () => output.push(null));
        reply.raw.once("close", () => output.destroy());
      } else {
        output.push(null);
      }
      return reply.header("content-type", "text/event-stream; charset=utf-8").header("cache-control", "no-store").header("x-accel-buffering", "no").code(200).send(output);
    } catch (error) {
      if (error instanceof TelemetryServiceError) return sendTelemetryError(reply, error);
      return sendRouteError(reply, error);
    }
  });
}

function sendTelemetryError(reply: { code(statusCode: number): { send(payload: unknown): unknown } }, error: unknown): unknown {
  if (error instanceof TelemetryServiceError) return reply.code(error.statusCode).send({ error: error.code, message: error.message });
  return reply.code(500).send({ error: "INTERNAL_ERROR", message: "an unexpected error occurred" });
}
