import { readFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { buildServer } from "../apps/edge-api/dist/server.js";

const consoleRoot = "/opt/sms/console";
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

async function staticAsset(relativePath, reply) {
  if (!/^[a-zA-Z0-9._/-]+$/.test(relativePath) || relativePath.split("/").includes("..")) {
    return reply.code(404).send({ error: "asset not found" });
  }
  const path = resolve(consoleRoot, relativePath);
  if (!path.startsWith(`${consoleRoot}/`)) return reply.code(404).send({ error: "asset not found" });
  try {
    const body = await readFile(path);
    return reply.type(contentTypes.get(extname(path)) ?? "application/octet-stream").send(body);
  } catch {
    return reply.code(404).send({ error: "asset not found" });
  }
}

const port = Number(process.env.SMS_PORT ?? "8443");
if (!Number.isInteger(port) || port < 1 || port > 65_535) throw new Error("SMS_PORT must be an integer between 1 and 65535");

const app = await buildServer({
  bindAddress: process.env.SMS_BIND_ADDRESS ?? "0.0.0.0",
  port,
  databaseUrl: requiredEnvironment("SMS_DATABASE_URL"),
  packageDirectory: requiredEnvironment("SMS_PACKAGE_DIRECTORY"),
  internet: "disabled",
  tls: {
    certPath: requiredEnvironment("SMS_TLS_CERT_PATH"),
    keyPath: requiredEnvironment("SMS_TLS_KEY_PATH"),
  },
});

app.get("/", async (_request, reply) => staticAsset("index.html", reply));
app.get("/favicon.svg", async (_request, reply) => staticAsset("favicon.svg", reply));
app.get("/assets/*", async (request, reply) => {
  const wildcard = request.params["*"];
  return staticAsset(`assets/${typeof wildcard === "string" ? wildcard : ""}`, reply);
});

const shutdown = async (signal) => {
  process.stderr.write(`${JSON.stringify({ event: "shutdown", signal })}\n`);
  await app.close();
  process.exit(0);
};
process.once("SIGINT", () => void shutdown("SIGINT"));
process.once("SIGTERM", () => void shutdown("SIGTERM"));

await app.listen({ host: app.edgeConfig.bindAddress, port: app.edgeConfig.port });
process.stdout.write(`${JSON.stringify({
  event: "listening",
  address: app.edgeConfig.bindAddress,
  port: app.edgeConfig.port,
  internet: app.edgeConfig.internet,
  tls: true,
})}\n`);
