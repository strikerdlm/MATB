import { afterEach, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildServer } from "../src/server.js";

describe("offline edge server", () => {
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("boots with internet disabled and exposes a local health check", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });

    const response = await app.inject({ method: "GET", url: "/healthz" });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({
      status: "ok",
      internet: "disabled",
    });
  });

  it("does not claim readiness before policy dependencies are validated", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });

    const response = await app.inject({ method: "GET", url: "/readyz" });

    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({
      status: "not_ready",
      checks: {
        database: { status: "ok" },
        migrations: { status: "ok" },
        signingKeys: { status: "pending" },
        terminology: { status: "pending" },
        policyPackage: { status: "pending" },
      },
    });
  });
});
