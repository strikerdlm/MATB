import { afterEach, describe, expect, it, vi } from "vitest";
import { EdgeApiClient, SessionExpiredError } from "../src/api/client.js";

describe("EdgeApiClient", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses same-origin credentials and attaches the in-memory CSRF token to unsafe calls", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"],
        sessionId: "session-1", csrfToken: "csrf-live", requiresReauthentication: false,
      }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ responseId: "response-1" }), {
        status: 201, headers: { "content-type": "application/json" },
      }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new EdgeApiClient();

    await client.login("commander-1", "secret-password");
    await client.post("/api/revisions/mission-1:r0/checklist-responses", {
      responseId: "response-1", itemId: "preflight-1", response: "pass",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/auth/login", expect.objectContaining({
      method: "POST", credentials: "same-origin",
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/revisions/mission-1:r0/checklist-responses", expect.objectContaining({
      method: "POST", credentials: "same-origin",
      headers: expect.objectContaining({ "x-csrf-token": "csrf-live" }),
    }));
  });

  it("clears only in-memory session state and signals lock on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "AUTHENTICATION_REQUIRED" }), {
      status: 401, headers: { "content-type": "application/json" },
    })));
    const client = new EdgeApiClient();

    await expect(client.get("/api/missions")).rejects.toBeInstanceOf(SessionExpiredError);
    expect(client.session()).toBeUndefined();
  });

  it("uses passive status without replacing the active CSRF token", async () => {
    const active = {
      userId: "operator-1", roles: ["operator"] as const, missionIds: ["mission-1"], sessionId: "session-1", csrfToken: "csrf-original",
      requiresReauthentication: false, expiresAtUtc: "2026-08-10T02:00:00.000Z", lastActivityAtUtc: "2026-08-09T18:00:00.000Z", idleTimeoutMs: 900_000,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(active), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ sessionId: "session-1", expiresAtUtc: active.expiresAtUtc, lastActivityAtUtc: active.lastActivityAtUtc, idleTimeoutMs: active.idleTimeoutMs, requiresReauthentication: true }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new EdgeApiClient();

    await client.login("operator-1", "secret-password");
    const status = await client.sessionStatus();
    await client.post("/api/revisions/mission-1:r0/checklist-responses", { response: "pass" });

    expect(status.requiresReauthentication).toBe(true);
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/auth/status", expect.objectContaining({ method: "GET" }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/revisions/mission-1:r0/checklist-responses", expect.objectContaining({ headers: expect.objectContaining({ "x-csrf-token": "csrf-original" }) }));
  });

  it("does not let a late lock completion clear a newer client session", async () => {
    const session = (id: string, csrfToken: string) => ({ userId: id, roles: ["operator"] as const, missionIds: ["mission-1"], sessionId: id, csrfToken, requiresReauthentication: false, expiresAtUtc: "2026-08-10T02:00:00.000Z", lastActivityAtUtc: "2026-08-09T18:00:00.000Z", idleTimeoutMs: 900_000 });
    let finishLock!: (response: Response) => void;
    const pendingLock = new Promise<Response>((resolve) => { finishLock = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session("old-session", "old-csrf")), { status: 200, headers: { "content-type": "application/json" } }))
      .mockReturnValueOnce(pendingLock)
      .mockResolvedValueOnce(new Response(JSON.stringify(session("new-session", "new-csrf")), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new EdgeApiClient();

    await client.login("old-session", "secret-password");
    const locking = client.lock("old-session");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await client.login("new-session", "secret-password");
    finishLock(new Response(null, { status: 204 }));
    await locking;

    expect(client.session()?.sessionId).toBe("new-session");
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual({ expectedSessionId: "old-session" });
  });

  it("serializes a CSRF-rotating restore ahead of unsafe calls", async () => {
    const session = (csrfToken: string) => ({ userId: "operator-1", roles: ["operator"] as const, missionIds: ["mission-1"], sessionId: "session-1", csrfToken, requiresReauthentication: false, expiresAtUtc: "2026-08-10T02:00:00.000Z", lastActivityAtUtc: "2026-08-09T18:00:00.000Z", idleTimeoutMs: 900_000 });
    let finishRestore!: (response: Response) => void;
    const pendingRestore = new Promise<Response>((resolve) => { finishRestore = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session("csrf-old")), { status: 200, headers: { "content-type": "application/json" } }))
      .mockReturnValueOnce(pendingRestore)
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new EdgeApiClient();
    await client.login("operator-1", "secret-password");

    const restoring = client.restoreSession();
    const writing = client.post("/api/revisions/mission-1:r0/checklist-responses", { response: "pass" });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    finishRestore(new Response(JSON.stringify(session("csrf-new")), { status: 200, headers: { "content-type": "application/json" } }));
    await restoring;
    await writing;

    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/revisions/mission-1:r0/checklist-responses", expect.objectContaining({ headers: expect.objectContaining({ "x-csrf-token": "csrf-new" }) }));
  });

  it.each([
    "/\\evil.example/mission",
    "/api/missions\\..\\..\\evil",
    "/api/missions\nX-Test: injected",
    "//evil.example/mission",
    "https://evil.example/mission",
  ])("rejects the normalized cross-origin or ambiguous path %s before fetch", async (path) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const client = new EdgeApiClient("https://console.example");

    await expect(client.get(path)).rejects.toThrow(/same-origin/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
