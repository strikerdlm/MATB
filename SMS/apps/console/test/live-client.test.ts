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
});
