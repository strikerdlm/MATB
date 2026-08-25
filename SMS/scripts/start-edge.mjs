import { readFile } from "node:fs/promises";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".svg", "image/svg+xml"],
]);

function requiredEnvironment(name) {
  const value = process.env[name];
  if (typeof value !== "string" || value.trim() === "") throw new Error(`${name} is required`);
  return value;
}

async function configuredTelemetryAdapters(configDirectory) {
  const configuredPath = process.env.SMS_TELEMETRY_ADAPTERS_PATH;
  if (configuredPath === undefined || configuredPath.trim() === "") return [];
  const path = resolve(configDirectory, configuredPath);
  const parsed = JSON.parse(await readFile(path, "utf8"));
  if (!Array.isArray(parsed)) throw new Error("SMS_TELEMETRY_ADAPTERS_PATH must contain a JSON array");
  return parsed;
}

let app;
try {
const [{ buildServer }, { installGracefulShutdown }, { resolveContainedRuntimePath }] = await Promise.all([
  import("../apps/edge-api/dist/server.js"),
  import("../apps/edge-api/dist/runtime/lifecycle.js"),
  import("../apps/edge-api/dist/runtime/paths.js"),
]);
const deploymentMode = requiredEnvironment("SMS_DEPLOYMENT_MODE");
if (deploymentMode !== "standalone" && deploymentMode !== "tactical") throw new Error("SMS_DEPLOYMENT_MODE must be standalone or tactical");
const configDirectory = resolve(moduleDirectory, process.env.SMS_CONFIG_DIRECTORY ?? ".");
const port = Number(process.env.SMS_PORT ?? "8443");
if (!Number.isInteger(port) || port < 1 || port > 65_535) throw new Error("SMS_PORT must be an integer between 1 and 65535");

app = await buildServer({
  deploymentMode,
  configDirectory,
  consoleDirectory: process.env.SMS_CONSOLE_DIRECTORY ?? resolve(moduleDirectory, "../apps/console/dist"),
  bindAddress: process.env.SMS_BIND_ADDRESS ?? "127.0.0.1",
  port,
  databaseUrl: requiredEnvironment("SMS_DATABASE_URL"),
  packageDirectory: requiredEnvironment("SMS_PACKAGE_DIRECTORY"),
  exportKeyPath: requiredEnvironment("SMS_EXPORT_KEY_PATH"),
  exportKeyId: requiredEnvironment("SMS_EXPORT_KEY_ID"),
  telemetryAdapters: await configuredTelemetryAdapters(configDirectory),
  internet: "disabled",
  tls: {
    certPath: requiredEnvironment("SMS_TLS_CERT_PATH"),
    keyPath: requiredEnvironment("SMS_TLS_KEY_PATH"),
    ...(deploymentMode === "tactical"
      ? { clientCaPath: requiredEnvironment("SMS_TLS_CLIENT_CA_PATH") }
      : process.env.SMS_TLS_CLIENT_CA_PATH === undefined ? {} : { clientCaPath: process.env.SMS_TLS_CLIENT_CA_PATH }),
  },
}, {
  logSink: (entry) => process.stdout.write(`${JSON.stringify(entry)}\n`),
});

async function staticAsset(relativePath, reply) {
  if (!/^[a-zA-Z0-9._/\\-]+$/.test(relativePath) || relativePath.split(/[\\/]/).includes("..")) return reply.code(404).send({ error: "NOT_FOUND", message: "asset not found" });
  let path;
  try {
    path = resolveContainedRuntimePath(app.edgeConfig.consoleDirectory, relativePath);
  } catch {
    return reply.code(404).send({ error: "NOT_FOUND", message: "asset not found" });
  }
  try {
    const body = await readFile(path);
    return reply.type(contentTypes.get(extname(path)) ?? "application/octet-stream").send(body);
  } catch {
    return reply.code(404).send({ error: "NOT_FOUND", message: "asset not found" });
  }
}

app.get("/", async (_request, reply) => staticAsset("index.html", reply));
app.get("/favicon.svg", async (_request, reply) => staticAsset("favicon.svg", reply));
app.get("/assets/*", async (request, reply) => staticAsset(`assets/${typeof request.params["*"] === "string" ? request.params["*"] : ""}`, reply));

installGracefulShutdown(app, process, (entry) => process.stderr.write(`${JSON.stringify(entry)}\n`));
await app.listen({ host: app.edgeConfig.bindAddress, port: app.edgeConfig.port });
process.stdout.write(`${JSON.stringify({ event: "listening", address: app.edgeConfig.bindAddress, port: app.edgeConfig.port, internet: app.edgeConfig.internet, tls: true, deploymentMode: app.edgeConfig.deploymentMode })}\n`);
} catch {
  try { await app?.close(); } catch { /* startup failure remains sanitized below */ }
  process.stderr.write(`${JSON.stringify({ event: "startup.failed", code: "STARTUP_FAILED" })}\n`);
  process.exitCode = 1;
}
