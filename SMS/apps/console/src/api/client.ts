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

  public session(): AuthenticatedSession | undefined { return this.activeSession; }

  public async login(userId: string, password: string): Promise<AuthenticatedSession> {
    const session = await this.request<AuthenticatedSession>("/api/auth/login", "POST", { userId, password }, false);
    this.activeSession = Object.freeze(session);
    return session;
  }

  public async restoreSession(): Promise<AuthenticatedSession> {
    const session = await this.request<AuthenticatedSession>("/api/auth/session", "GET");
    this.activeSession = Object.freeze(session);
    return session;
  }

  public async reauthenticate(password: string): Promise<AuthenticatedSession> {
    const session = await this.post<AuthenticatedSession>("/api/auth/reauthenticate", { password });
    this.activeSession = Object.freeze(session);
    return session;
  }

  public async lock(): Promise<void> { await this.post<void>("/api/auth/lock"); this.activeSession = undefined; }
  public async logout(): Promise<void> { await this.post<void>("/api/auth/logout"); this.activeSession = undefined; }
  public get<T>(path: string): Promise<T> { return this.request<T>(path, "GET"); }
  public post<T>(path: string, body?: unknown): Promise<T> { return this.request<T>(path, "POST", body); }

  public async readiness(): Promise<ReadinessReport> {
    const response = await fetch("/readyz", { method: "GET", credentials: "same-origin", headers: { accept: "application/json" } });
    return parseJson<ReadinessReport>(response);
  }

  private async request<T>(path: string, method: "GET" | "POST", body?: unknown, authenticated = true): Promise<T> {
    if (!path.startsWith("/") || path.startsWith("//")) throw new TypeError("Edge API paths must be same-origin");
    const csrfToken = this.activeSession?.csrfToken;
    const response = await fetch(path, {
      method,
      credentials: "same-origin",
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

async function parseJson<T>(response: Response): Promise<T> {
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) throw new TypeError("Edge API response was not JSON");
  return response.json() as Promise<T>;
}
