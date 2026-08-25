import type { InjectOptions, LightMyRequestResponse } from "fastify";
import { LocalIdentityStore } from "../src/auth/identity.js";
import type { UserRole } from "../src/auth/roles.js";
import { SessionManager } from "../src/auth/session.js";
import { buildServer, type EdgeServer } from "../src/server.js";
import { nowUtc } from "./mission-fixture.js";

const password = "correct horse battery staple";

export interface HttpTestIdentity {
  readonly userId: string;
  readonly roles: readonly UserRole[];
  readonly missionIds?: readonly string[];
}

interface SessionHeaders {
  readonly cookie: string;
  readonly csrfToken: string;
}

export interface AuthenticatedTestServer {
  readonly app: EdgeServer;
  request(input: InjectOptions, userId?: string): Promise<LightMyRequestResponse>;
}

export async function authenticatedTestServer(
  config: Parameters<typeof buildServer>[0],
  identities: readonly HttpTestIdentity[] = [{ userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] }],
): Promise<AuthenticatedTestServer> {
  const identityStore = new LocalIdentityStore({ now: () => nowUtc });
  for (const identity of identities) {
    identityStore.register({
      userId: identity.userId,
      displayName: identity.userId,
      roles: identity.roles,
      missionIds: identity.missionIds ?? [],
      password,
    });
  }
  let sequence = 0;
  const sessionManager = new SessionManager({
    now: () => nowUtc,
    idleTimeoutMs: 15 * 60_000,
    maxLifetimeMs: 8 * 60 * 60_000,
    reauthenticationIntervalMs: 5 * 60_000,
    sessionIdFactory: () => `test-session-${++sequence}`,
    csrfTokenFactory: () => `test-csrf-${sequence}`,
  });
  const app = await buildServer(config, { identityStore, sessionManager });
  const sessions = new Map<string, SessionHeaders>();
  for (const identity of identities) {
    const response = await app.inject({
      method: "POST",
      url: "/api/auth/login",
      payload: { userId: identity.userId, password },
    });
    if (response.statusCode !== 200) throw new Error(`test login failed for ${identity.userId}`);
    const body = response.json() as { csrfToken: string };
    sessions.set(identity.userId, {
      cookie: `__Host-sms_session=test-session-${sessions.size + 1}`,
      csrfToken: body.csrfToken,
    });
  }

  return {
    app,
    async request(input, userId = identities[0]?.userId ?? "") {
      const session = sessions.get(userId);
      if (session === undefined) throw new Error(`no authenticated test session for ${userId}`);
      return app.inject({
        ...input,
        headers: {
          ...input.headers,
          cookie: session.cookie,
          ...(input.method === "GET" || input.method === "HEAD" ? {} : { "x-csrf-token": session.csrfToken }),
        },
      });
    },
  };
}
