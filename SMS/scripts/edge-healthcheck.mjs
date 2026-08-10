import https from "node:https";
import { buildServer } from "../apps/edge-api/dist/server.js";

async function selfTest() {
  const app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
  try {
    const health = await app.inject({ method: "GET", url: "/healthz" });
    const readiness = await app.inject({ method: "GET", url: "/readyz" });
    const payload = health.json();
    if (health.statusCode !== 200 || payload.status !== "ok" || payload.internet !== "disabled") {
      throw new Error("edge health contract failed");
    }
    if (readiness.statusCode !== 503 || readiness.json().status !== "not_ready") {
      throw new Error("edge readiness must fail closed until local packages are activated");
    }
  } finally {
    await app.close();
  }
  process.stdout.write("PASS edge self-test (offline; readiness fail-closed)\n");
}

async function liveCheck() {
  const port = Number(process.env.SMS_PORT ?? "8443");
  const response = await new Promise((resolve, reject) => {
    const request = https.get({
      hostname: "127.0.0.1",
      port,
      path: "/healthz",
      rejectUnauthorized: false,
      timeout: 4_000,
    }, resolve);
    request.once("timeout", () => request.destroy(new Error("health check timed out")));
    request.once("error", reject);
  });
  const chunks = [];
  for await (const chunk of response) chunks.push(chunk);
  const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (response.statusCode !== 200 || payload.status !== "ok" || payload.internet !== "disabled") {
    throw new Error("live edge health check failed");
  }
  process.stdout.write("PASS live edge health check\n");
}

try {
  if (process.argv[2] === "--live") await liveCheck();
  else await selfTest();
} catch (error) {
  process.stderr.write(`FAIL edge health check: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
