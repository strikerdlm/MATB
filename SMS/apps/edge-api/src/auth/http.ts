import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { AuthenticationError, LocalAuthenticator, LocalIdentityStore } from "./identity.js";
import type { UserRole } from "./roles.js";
import { SessionManager, type Session } from "./session.js";
import type { EdgeDatabase } from "../db/migrate.js";

export const SESSION_COOKIE_NAME = "__Host-sms_session";
export const SESSION_COOKIE_ATTRIBUTES = "Secure; HttpOnly; SameSite=Strict; Path=/";
export const DEFAULT_SESSION_POLICY = Object.freeze({
  idleTimeoutMs: 15 * 60_000,
  maxLifetimeMs: 8 * 60 * 60_000,
  reauthenticationIntervalMs: 5 * 60_000,
});

export interface AuthenticatedPrincipal {
  readonly userId: string;
  readonly roles: readonly UserRole[];
  readonly missionIds: readonly string[];
  readonly sessionId: string;
  readonly csrfToken: string;
  readonly requiresReauthentication: boolean;
  readonly expiresAtUtc: string;
  readonly lastActivityAtUtc: string;
  readonly idleTimeoutMs: number;
  readonly clientCertificateFingerprint?: string;
}

export interface HttpAuthDependencies {
  readonly identityStore: LocalIdentityStore;
  readonly sessionManager: SessionManager;
}

declare module "fastify" {
  interface FastifyRequest {
    authenticatedPrincipal?: AuthenticatedPrincipal;
  }
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const ADAPTER_AUTHENTICATED_ROUTES = new Set(["/api/telemetry/ingest"]);
const ACCOUNTABLE_IDENTITY_FIELDS = new Set([
  "actorUserId",
  "actorRole",
  "clientSessionId",
  "accountableUserId",
  "sessionId",
  "signerUserId",
  "signerRole",
]);

export function createDefaultHttpAuthDependencies(database?: EdgeDatabase): HttpAuthDependencies {
  return {
    identityStore: new LocalIdentityStore({ database }),
    sessionManager: new SessionManager({ ...DEFAULT_SESSION_POLICY, database }),
  };
}

function principalFrom(session: Session): AuthenticatedPrincipal {
  return Object.freeze({
    userId: session.userId,
    roles: Object.freeze([...session.roles]),
    missionIds: Object.freeze([...session.missionIds]),
    sessionId: session.sessionId,
    csrfToken: session.csrfToken,
    requiresReauthentication: session.requiresReauthentication === true,
    expiresAtUtc: session.expiresAtUtc,
    lastActivityAtUtc: session.lastActivityAtUtc,
    idleTimeoutMs: session.idleTimeoutMs,
  });
}

function sessionCookie(sessionId: string): string {
  return `${SESSION_COOKIE_NAME}=${sessionId}; ${SESSION_COOKIE_ATTRIBUTES}`;
}

function clearedSessionCookie(): string {
  return `${SESSION_COOKIE_NAME}=; Max-Age=0; ${SESSION_COOKIE_ATTRIBUTES}`;
}

function cookieValue(request: FastifyRequest): string | undefined {
  const header = request.headers.cookie;
  if (header === undefined) return undefined;
  for (const part of header.split(";")) {
    const separator = part.indexOf("=");
    if (separator < 0) continue;
    const name = part.slice(0, separator).trim();
    if (name === SESSION_COOKIE_NAME) return part.slice(separator + 1).trim() || undefined;
  }
  return undefined;
}

function unauthorized(reply: FastifyReply): FastifyReply {
  return reply.code(401).send({ error: "AUTHENTICATION_REQUIRED", message: "an active authenticated session is required" });
}

function accountableIdentityField(value: unknown, visited = new WeakSet<object>()): string | undefined {
  if (value === null || typeof value !== "object") return undefined;
  if (visited.has(value)) return undefined;
  visited.add(value);
  if (Array.isArray(value)) {
    for (const item of value) {
      const field = accountableIdentityField(item, visited);
      if (field !== undefined) return field;
    }
    return undefined;
  }
  for (const [field, child] of Object.entries(value as Record<string, unknown>)) {
    if (ACCOUNTABLE_IDENTITY_FIELDS.has(field)) return field;
    const nested = accountableIdentityField(child, visited);
    if (nested !== undefined) return nested;
  }
  return undefined;
}

export function requirePrincipal(request: FastifyRequest): AuthenticatedPrincipal {
  if (request.authenticatedPrincipal === undefined) throw new Error("authenticated principal was not established");
  return request.authenticatedPrincipal;
}

export function canReadMission(principal: AuthenticatedPrincipal, missionId: string): boolean {
  return principal.roles.includes("reviewer")
    || principal.missionIds.includes("*")
    || principal.missionIds.includes(missionId);
}

export function forbid(reply: FastifyReply, message: string): FastifyReply {
  return reply.code(403).send({ error: "AUTHORIZATION_FORBIDDEN", message });
}

export function registerHttpAuthentication(app: FastifyInstance, dependencies: HttpAuthDependencies): void {
  const authenticator = new LocalAuthenticator(dependencies.identityStore, dependencies.sessionManager);

  app.addHook("onRequest", async (request, reply) => {
    if (request.is404 || !request.url.startsWith("/api/") || (request.method === "POST" && request.routeOptions.url === "/api/auth/login")) return;
    if (request.routeOptions.url !== undefined && ADAPTER_AUTHENTICATED_ROUTES.has(request.routeOptions.url)) return;
    const sessionCredential = cookieValue(request);
    if (sessionCredential === undefined) return unauthorized(reply);
    const session = dependencies.sessionManager.getSessionByCredential(sessionCredential);
    if (session === undefined || session.state !== "active") return unauthorized(reply);
    if (!dependencies.identityStore.isSessionIdentityValid(session.userId, session.credentialVersion, session.roles, session.missionIds)) {
      dependencies.sessionManager.deleteSession(session.sessionId);
      return unauthorized(reply);
    }
    const touched = dependencies.sessionManager.touchSessionByCredential(sessionCredential);
    if (touched === undefined) return unauthorized(reply);
    if (touched.state !== "active") return unauthorized(reply);
    request.authenticatedPrincipal = principalFrom(touched);
    const csrf = request.headers["x-csrf-token"];
    if (!SAFE_METHODS.has(request.method) && (typeof csrf !== "string" || !dependencies.sessionManager.verifyCsrfToken(touched.sessionId, csrf))) {
      return reply.code(403).send({ error: "CSRF_TOKEN_INVALID", message: "the exact session CSRF token is required" });
    }
  });

  app.addHook("preHandler", async (request, reply) => {
    if (!request.url.startsWith("/api/") || SAFE_METHODS.has(request.method)) return;
    const field = accountableIdentityField(request.body);
    if (field === undefined) return;
    return reply.code(400).send({
      error: "ACCOUNTABLE_IDENTITY_FORBIDDEN",
      message: `${field} must be derived from the authenticated session`,
    });
  });

  app.post("/api/auth/login", async (request, reply) => {
    const body = request.body as { userId?: unknown; password?: unknown } | null;
    const userId = typeof body?.userId === "string" ? body.userId : "";
    const password = typeof body?.password === "string" ? body.password : "";
    try {
      const issued = await authenticator.authenticateLocalWithCredential({ userId, password });
      return reply.header("set-cookie", sessionCookie(issued.credential)).code(200).send(principalFrom(issued.session));
    } catch (error) {
      if (error instanceof AuthenticationError) return unauthorized(reply);
      throw error;
    }
  });

  app.get("/api/auth/session", async (request, reply) => {
    const principal = requirePrincipal(request);
    const rotated = dependencies.sessionManager.rotateCsrfToken(principal.sessionId);
    return reply.code(200).send(principalFrom(rotated));
  });

  app.post("/api/auth/reauthenticate", async (request, reply) => {
    const principal = requirePrincipal(request);
    const body = request.body as { password?: unknown } | null;
    const password = typeof body?.password === "string" ? body.password : "";
    try {
      const session = await authenticator.reauthenticateLocal(principal.sessionId, { userId: principal.userId, password });
      return reply.code(200).send(principalFrom(session));
    } catch (error) {
      if (error instanceof AuthenticationError) return unauthorized(reply);
      throw error;
    }
  });

  app.post("/api/auth/lock", async (request, reply) => {
    const principal = requirePrincipal(request);
    dependencies.sessionManager.lockSession(principal.sessionId, "user requested lock");
    return reply.header("set-cookie", clearedSessionCookie()).code(204).send();
  });

  app.post("/api/auth/logout", async (request, reply) => {
    const principal = requirePrincipal(request);
    dependencies.sessionManager.deleteSession(principal.sessionId);
    return reply.header("set-cookie", clearedSessionCookie()).code(204).send();
  });
}
