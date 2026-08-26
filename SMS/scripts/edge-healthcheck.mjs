import https from "node:https";
import { readFile } from "node:fs/promises";
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

export async function buildInstalledRequestOptions(mode, environment = process.env) {
  const hostname = environment.SMS_HEALTH_HOST;
  const port = Number(environment.SMS_HEALTH_PORT ?? environment.SMS_PORT);
  const servername = environment.SMS_HEALTH_SERVERNAME;
  const caPath = environment.SMS_HEALTH_CA_PATH;
  if (!hostname) throw new Error("SMS_HEALTH_HOST is required");
  if (!Number.isInteger(port) || port < 1 || port > 65_535) throw new Error("SMS_HEALTH_PORT or SMS_PORT must be a valid TCP port");
  if (!servername) throw new Error("SMS_HEALTH_SERVERNAME is required");
  if (!caPath) throw new Error("SMS_HEALTH_CA_PATH is required");
  const clientCertificate = environment.SMS_HEALTH_CLIENT_CERT_PATH;
  const clientKey = environment.SMS_HEALTH_CLIENT_KEY_PATH;
  if ((clientCertificate === undefined) !== (clientKey === undefined)) throw new Error("health client certificate and key must be configured together");
  const clientTls = clientCertificate === undefined ? {} : {
    cert: await readFile(clientCertificate),
    key: await readFile(clientKey),
  };
  return {
    hostname,
    port,
    servername,
    path: mode === "ready" ? "/readyz" : "/healthz",
    rejectUnauthorized: true,
    ca: await readFile(caPath),
    timeout: 4_000,
    ...clientTls,
  };
}

async function installedCheck(mode) {
  const options = await buildInstalledRequestOptions(mode);
  const response = await new Promise((resolve, reject) => {
    const request = https.get(options, resolve);
    request.once("timeout", () => request.destroy(new Error("health check timed out")));
    request.once("error", reject);
  });
  const chunks = [];
  for await (const chunk of response) chunks.push(chunk);
  const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (mode === "ready") {
    if (response.statusCode !== 200 || payload.technicalReady !== true) throw new Error("installed edge readiness check failed");
  } else if (response.statusCode !== 200 || payload.status !== "ok" || payload.internet !== "disabled") {
    throw new Error("installed edge liveness check failed");
  }
  process.stdout.write(`PASS installed edge ${mode} check\n`);
}

try {
  if (process.argv[2] === "--live") await installedCheck("live");
  else if (process.argv[2] === "--ready") await installedCheck("ready");
  else await selfTest();
} catch (error) {
  process.stderr.write(`FAIL edge health check: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
