import type { AuthenticatedSession, ReadinessReport } from "./types.js";

const SAFE_METHODS = new Set(["GET", "HEAD"]);

export class SessionExpiredError extends Error {
  public constructor() { super("the authenticated session expired"); this.name = "SessionExpiredError"; }
}

export class EdgeApiError extends Error {
  public constructor(public readonly status: number, public readonly code: string, message: string) {
    super(message); this.name = "EdgeApiError";
  }
}

export class EdgeApiClient {
  private activeSession?: AuthenticatedSession;

  public constructor(private readonly origin = typeof location === "undefined" ? "https://edge.invalid" : location.origin) {}

  public session(): AuthenticatedSession | undefined { return this.activeSession; }

  public async login(userId: string, password: string, signal?: AbortSignal): Promise<AuthenticatedSession> {
    const session = await this.request<AuthenticatedSession>("/api/auth/login", "POST", { userId, password }, false, signal);
    this.activeSession = Object.freeze(session);
    return session;
  }

  public async restoreSession(signal?: AbortSignal): Promise<AuthenticatedSession> {
    const session = await this.request<AuthenticatedSession>("/api/auth/session", "GET", undefined, true, signal);
    this.activeSession = Object.freeze(session);
    return session;
  }

  public async reauthenticate(password: string, signal?: AbortSignal): Promise<AuthenticatedSession> {
    const session = await this.post<AuthenticatedSession>("/api/auth/reauthenticate", { password }, signal);
    this.activeSession = Object.freeze(session);
    return session;
  }

  public async lock(signal?: AbortSignal): Promise<void> { await this.post<void>("/api/auth/lock", undefined, signal); this.activeSession = undefined; }
  public async logout(signal?: AbortSignal): Promise<void> { await this.post<void>("/api/auth/logout", undefined, signal); this.activeSession = undefined; }
  public forgetSession(): void { this.activeSession = undefined; }
  public get<T>(path: string, signal?: AbortSignal): Promise<T> { return this.request<T>(path, "GET", undefined, true, signal); }
  public post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> { return this.request<T>(path, "POST", body, true, signal); }

  public async readiness(signal?: AbortSignal): Promise<ReadinessReport> {
    const response = await fetch(sameOriginPath("/readyz", this.origin), { method: "GET", credentials: "same-origin", headers: { accept: "application/json" }, signal });
    return parseJson<ReadinessReport>(response);
  }

  private async request<T>(path: string, method: "GET" | "POST", body?: unknown, authenticated = true, signal?: AbortSignal): Promise<T> {
    const csrfToken = this.activeSession?.csrfToken;
    const response = await fetch(sameOriginPath(path, this.origin), {
      method,
      credentials: "same-origin",
      signal,
      headers: {
        accept: "application/json",
        ...(body === undefined ? {} : { "content-type": "application/json" }),
        ...(!SAFE_METHODS.has(method) && authenticated && csrfToken !== undefined ? { "x-csrf-token": csrfToken } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (response.status === 401) { this.activeSession = undefined; throw new SessionExpiredError(); }
    if (!response.ok) {
      const failure: { error?: string; message?: string } = await parseJson<{ error?: string; message?: string }>(response).catch(() => ({}));
      throw new EdgeApiError(response.status, failure.error ?? "REQUEST_FAILED", failure.message ?? "request failed");
    }
    if (response.status === 204) return undefined as T;
    return parseJson<T>(response);
  }
}

export function sameOriginPath(path: string, origin: string): string {
  if (!path.startsWith("/") || path.startsWith("//") || /[\\\u0000-\u001f\u007f]/u.test(path)) {
    throw new TypeError("Edge API paths must be same-origin and unambiguous");
  }
  let resolved: URL;
  try { resolved = new URL(path, origin); } catch { throw new TypeError("Edge API paths must be same-origin and unambiguous"); }
  if (resolved.origin !== new URL(origin).origin || resolved.username !== "" || resolved.password !== "" || resolved.hash !== "") {
    throw new TypeError("Edge API paths must be same-origin and unambiguous");
  }
  return `${resolved.pathname}${resolved.search}`;
}

async function parseJson<T>(response: Response): Promise<T> {
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) throw new TypeError("Edge API response was not JSON");
  return response.json() as Promise<T>;
}
