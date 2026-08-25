import { randomUUID } from "node:crypto";
import type { FastifyInstance, FastifyRequest } from "fastify";
import type { RuntimeLogSink } from "./lifecycle.js";

const REQUEST_ID = /^[a-zA-Z0-9_-]{16,128}$/;
const CSP = "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'; form-action 'self'; connect-src 'self'";

export function requestIdFrom(request: FastifyRequest): string {
  return request.id;
}

export function safeRequestId(header: string | string[] | undefined): string {
  const candidate = Array.isArray(header) ? undefined : header;
  return typeof candidate === "string" && REQUEST_ID.test(candidate) ? candidate : randomUUID();
}

export function registerHttpSecurity(app: FastifyInstance, log: RuntimeLogSink = () => undefined): void {
  app.addHook("onSend", async (request, reply) => {
    reply.header("x-request-id", request.id);
    reply.header("content-security-policy", CSP);
    reply.header("x-content-type-options", "nosniff");
    reply.header("x-frame-options", "DENY");
    reply.header("referrer-policy", "no-referrer");
    reply.header("strict-transport-security", "max-age=31536000; includeSubDomains");
    reply.header("permissions-policy", "camera=(), microphone=(), geolocation=(), usb=()");
    if (request.url.startsWith("/api/")) reply.header("cache-control", "no-store");
  });

  app.addHook("onResponse", async (request, reply) => {
    log(Object.freeze({
      event: "http.response",
      requestId: request.id,
      method: request.method,
      route: request.routeOptions.url ?? "unmatched",
      statusCode: reply.statusCode,
    }));
  });

  app.setNotFoundHandler(async (request, reply) => reply.code(404).send({
    error: "NOT_FOUND",
    message: "resource not found",
    requestId: request.id,
  }));

  app.setErrorHandler(async (error, request, reply) => {
    const detail = error !== null && typeof error === "object" ? error as { readonly statusCode?: number; readonly code?: string } : {};
    if (detail.statusCode === 413 || detail.code === "FST_ERR_CTP_BODY_TOO_LARGE") {
      return reply.code(413).send({ error: "PAYLOAD_TOO_LARGE", message: "request body exceeds the configured limit", requestId: request.id });
    }
    log(Object.freeze({ event: "http.error", requestId: request.id, method: request.method, route: request.routeOptions.url ?? "unmatched", code: "INTERNAL_ERROR" }));
    return reply.code(500).send({ error: "INTERNAL_ERROR", message: "an unexpected error occurred", requestId: request.id });
  });
}
