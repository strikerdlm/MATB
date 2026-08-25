import { afterEach, describe, expect, it } from "vitest";
import type { EdgeServer } from "../src/server.js";
import { buildServer } from "../src/server.js";

describe("edge HTTP security boundary", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("adds a request ID, strict CSP, and transport-safe security headers", async () => {
    app = await buildServer({ databaseUrl: ":memory:" });
    const response = await app.inject({ method: "GET", url: "/healthz" });
    expect(response.statusCode).toBe(200);
    expect(response.headers["x-request-id"]).toMatch(/^[a-zA-Z0-9_-]{16,128}$/);
    expect(response.headers["content-security-policy"]).toContain("default-src 'self'");
    expect(response.headers["content-security-policy"]).toContain("object-src 'none'");
    expect(response.headers["content-security-policy"]).not.toContain("unsafe-inline");
    expect(response.headers["x-content-type-options"]).toBe("nosniff");
    expect(response.headers["x-frame-options"]).toBe("DENY");
    expect(response.headers["referrer-policy"]).toBe("no-referrer");
    expect(response.headers["strict-transport-security"]).toMatch(/max-age=/);
  });

  it("returns stable sanitized errors without internal secrets", async () => {
    const entries: unknown[] = [];
    app = await buildServer({ databaseUrl: ":memory:" }, { logSink: (entry) => entries.push(entry) });
    app.get("/fixture-failure", async () => { throw new Error("private-key=never-disclose"); });
    const response = await app.inject({ method: "GET", url: "/fixture-failure", headers: { "x-request-id": "external-request-id-1234" } });
    expect(response.statusCode).toBe(500);
    expect(response.headers["x-request-id"]).not.toBe("external-request-id-1234");
    expect(response.json()).toEqual({ error: "INTERNAL_ERROR", message: "an unexpected error occurred", requestId: response.headers["x-request-id"] });
    expect(response.body).not.toContain("never-disclose");
    expect(entries).toEqual(expect.arrayContaining([expect.objectContaining({ requestId: response.headers["x-request-id"], clientCorrelationId: "external-request-id-1234" })]));
  });

  it("enforces a strict JSON body limit with a stable error", async () => {
    app = await buildServer({ databaseUrl: ":memory:", bodyLimitBytes: 64 * 1024 });
    const response = await app.inject({ method: "POST", url: "/api/auth/login", payload: { userId: "user", password: "s".repeat(70_000) } });
    expect(response.statusCode).toBe(413);
    expect(response.json()).toMatchObject({ error: "PAYLOAD_TOO_LARGE", message: "request body exceeds the configured limit" });
    expect(response.json().requestId).toBe(response.headers["x-request-id"]);
  });

  it("writes sensitive-safe JSON metadata without headers or payloads", async () => {
    const entries: unknown[] = [];
    app = await buildServer({ databaseUrl: ":memory:" }, { logSink: (entry) => entries.push(entry) });
    await app.inject({
      method: "POST", url: "/api/auth/login",
      headers: { cookie: "__Host-sms_session=raw-cookie-secret", authorization: "Bearer raw-token-secret" },
      payload: { userId: "missing", password: "raw-password-secret", csrfToken: "raw-csrf-secret" },
    });
    expect(entries).toEqual(expect.arrayContaining([expect.objectContaining({ event: "http.response", method: "POST", statusCode: 401 })]));
    const serialized = JSON.stringify(entries);
    for (const secret of ["raw-cookie-secret", "raw-token-secret", "raw-password-secret", "raw-csrf-secret"]) expect(serialized).not.toContain(secret);
  });
});
