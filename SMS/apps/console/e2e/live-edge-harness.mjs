import { createHash, generateKeyPairSync, sign, X509Certificate } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { extname, join } from "node:path";
import { buildServer } from "../../edge-api/dist/server.js";
import { openDatabase } from "../../edge-api/dist/db/migrate.js";
import { LocalIdentityStore } from "../../edge-api/dist/auth/identity.js";
import { SessionManager } from "../../edge-api/dist/auth/session.js";
import { DEFAULT_SESSION_POLICY } from "../../edge-api/dist/auth/http.js";
import { SqliteTrustedKeyStore } from "../../edge-api/dist/services/safe-mode.js";
import { DeterministicSafetyEvaluationProvider } from "../../edge-api/dist/services/safety-evaluation.js";
import { manifestContentDigest, signManifest } from "@fac-isr/evidence";

const root = mkdtempSync(join(tmpdir(), "sms-live-console-"));
const databaseUrl = join(root, "edge.sqlite");
const packageDirectory = join(root, "packages");
const certPath = join(root, "server.crt");
const keyPath = join(root, "server.key");
const certificateAuthorityPath = join(root, "ca.crt");
const certificateAuthorityKeyPath = join(root, "ca.key");
const clientCertificatePath = join(root, "client.crt");
const clientKeyPath = join(root, "client.key");
const externalCertificateAuthorityPath = "/tmp/sms-console-e2e-ca.crt";
const externalClientCertificatePath = "/tmp/sms-console-e2e-client.crt";
const externalClientKeyPath = "/tmp/sms-console-e2e-client.key";
const consoleDirectory = new URL("../dist/", import.meta.url).pathname;
const password = "correct horse battery staple";
const nowUtc = "2026-08-25T12:00:00.000Z";
let clockUtc = nowUtc;
mkdirSync(packageDirectory);
const serverRequestPath = join(root, "server.csr");
const clientRequestPath = join(root, "client.csr");
const serverExtensionsPath = join(root, "server.ext");
const clientExtensionsPath = join(root, "client.ext");
writeFileSync(serverExtensionsPath, "subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\n");
writeFileSync(clientExtensionsPath, "extendedKeyUsage=clientAuth\n");
execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=SMS E2E CA", "-keyout", certificateAuthorityKeyPath, "-out", certificateAuthorityPath], { stdio: "ignore" });
execFileSync("openssl", ["req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=127.0.0.1", "-keyout", keyPath, "-out", serverRequestPath], { stdio: "ignore" });
execFileSync("openssl", ["x509", "-req", "-in", serverRequestPath, "-CA", certificateAuthorityPath, "-CAkey", certificateAuthorityKeyPath, "-CAcreateserial", "-days", "1", "-extfile", serverExtensionsPath, "-out", certPath], { stdio: "ignore" });
execFileSync("openssl", ["req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=adapter-e2e", "-keyout", clientKeyPath, "-out", clientRequestPath], { stdio: "ignore" });
execFileSync("openssl", ["x509", "-req", "-in", clientRequestPath, "-CA", certificateAuthorityPath, "-CAkey", certificateAuthorityKeyPath, "-CAcreateserial", "-days", "1", "-extfile", clientExtensionsPath, "-out", clientCertificatePath], { stdio: "ignore" });
writeFileSync(externalCertificateAuthorityPath, readFileSync(certificateAuthorityPath));
writeFileSync(externalClientCertificatePath, readFileSync(clientCertificatePath), { mode: 0o600 });
writeFileSync(externalClientKeyPath, readFileSync(clientKeyPath), { mode: 0o600 });
const fingerprint = new X509Certificate(readFileSync(clientCertificatePath)).fingerprint256.replaceAll(":", "").toLowerCase();

const exportKeys = generateKeyPairSync("ed25519");
const exportSigner = Object.freeze({ keyId: "console-e2e-export", algorithm: "Ed25519", sign: (payload) => sign(null, payload, exportKeys.privateKey).toString("base64") });
const authorityKeys = generateKeyPairSync("rsa", { modulusLength: 2048 });
const authorityPublic = authorityKeys.publicKey.export({ type: "pkcs1", format: "pem" }).toString();
const authorityPrivate = authorityKeys.privateKey.export({ type: "pkcs1", format: "pem" }).toString();

function authorityFixture(kind, packageId, files) {
  const directory = `${kind}-fixture`;
  const full = join(packageDirectory, directory);
  mkdirSync(full);
  const inventory = Object.entries(files).sort(([left], [right]) => left.localeCompare(right)).map(([path, value]) => {
    const content = Buffer.from(value); writeFileSync(join(full, path), content);
    return { path, sha256: createHash("sha256").update(content).digest("hex"), sizeBytes: content.byteLength };
  });
  const keyId = `${kind}-authority`;
  const manifest = signManifest({ schemaVersion: "1.0", packageId, kind, issuer: "fac-isr-e2e", version: "1.0.0", issuedAtUtc: "2026-08-24T00:00:00.000Z", effectiveFromUtc: "2026-08-24T00:00:00.000Z", expiresAtUtc: "2027-08-24T00:00:00.000Z", geographicScope: "Colombia", contentSha256: manifestContentDigest(inventory), keyId, dependencies: [], files: inventory, qualification: "approved", caveats: [], signature: "" }, authorityPrivate);
  return { directory, keyId, manifest };
}

const packages = [
  authorityFixture("policy", "policy-console-e2e", { "policy.json": JSON.stringify({ packageId: "policy-console-e2e", version: "1.0.0", status: "approved", delegatedAuthorities: [], freshness: { aip: { maxAgeMinutes: 120, critical: true }, notam: { maxAgeMinutes: 120, critical: true }, weather: { maxAgeMinutes: 120, critical: true }, terrain: { maxAgeMinutes: 120, critical: true }, airspace: { maxAgeMinutes: 120, critical: true }, policy: { maxAgeMinutes: 120, critical: true }, regulation: { maxAgeMinutes: 120, critical: true } }, signature: "e2e" }) }),
  authorityFixture("terminology", "terminology-console-e2e", { "terms.json": JSON.stringify({ terms: [] }) }),
  authorityFixture("regulatory", "evidence-console-e2e", { "requirements.json": "[]", "evidence-snapshot.json": JSON.stringify({ snapshotId: "evidence-1", requirementIds: [], acceptedEvidenceIds: [] }) }),
];

{
  const database = openDatabase(databaseUrl);
  const identities = new LocalIdentityStore({ database, now: () => nowUtc });
  const missionIds = ["mission-1", "mission-es", "mission-safe-runtime", "mission-safe-view", "mission-expiry", "mission-a11y-desktop", "mission-a11y-tablet"];
  for (const [userId, roles] of [["maintainer-1", ["maintainer"]], ["operator-1", ["operator"]], ["safety-1", ["safety-officer"]], ["commander-1", ["commander"]]]) identities.register({ userId, displayName: userId, roles, missionIds, password });
  identities.register({ userId: "administrator-1", displayName: "administrator-1", roles: ["administrator"], missionIds: [], password });
  const trust = new SqliteTrustedKeyStore(database);
  for (const pkg of packages) trust.add({ keyId: pkg.keyId, scope: pkg.manifest.kind, algorithm: "rsa-sha256", publicKeyPem: authorityPublic, addedAtUtc: nowUtc, addedByUserId: "offline-e2e-admin" });
  database.close();
}

const safetyEvaluationProvider = new DeterministicSafetyEvaluationProvider({ now: () => nowUtc, resolve: async () => ({ requirements: [], policy: { packageId: "policy-console-e2e", version: "1.0.0", status: "approved", delegatedAuthorities: [], freshness: { aip: { maxAgeMinutes: 120, critical: true }, notam: { maxAgeMinutes: 120, critical: true }, weather: { maxAgeMinutes: 120, critical: true }, terrain: { maxAgeMinutes: 120, critical: true }, airspace: { maxAgeMinutes: 120, critical: true }, policy: { maxAgeMinutes: 120, critical: true }, regulation: { maxAgeMinutes: 120, critical: true } }, signature: "e2e" }, evidenceSnapshot: { snapshotId: "evidence-1", acceptedEvidenceIds: [] }, policyPackage: { packageId: "policy-console-e2e", version: "1.0.0" }, terminologyPackage: { packageId: "terminology-console-e2e", version: "1.0.0" }, evidencePackage: { packageId: "evidence-console-e2e", version: "1.0.0" } }) });

const contentTypes = new Map([[".css", "text/css; charset=utf-8"], [".html", "text/html; charset=utf-8"], [".js", "text/javascript; charset=utf-8"], [".svg", "image/svg+xml"]]);
let app;
async function build() {
  const authDatabase = openDatabase(databaseUrl);
  const identityStore = new LocalIdentityStore({ database: authDatabase, now: () => clockUtc });
  const sessionManager = new SessionManager({ ...DEFAULT_SESSION_POLICY, database: authDatabase, now: () => clockUtc });
  const next = await buildServer({ deploymentMode: "standalone", bindAddress: "127.0.0.1", port: 4173, databaseUrl, packageDirectory, consoleDirectory, tls: { certPath, keyPath, clientCaPath: certificateAuthorityPath }, telemetryAdapters: [{ fingerprintSha256: fingerprint, adapterId: "adapter-e2e", aircraftIds: ["aircraft-1", "aircraft-expiry"] }] }, { now: () => clockUtc, identityStore, sessionManager, safetyEvaluationProvider, exportSigner, readiness: { tlsConfigured: true, exportKeyConfigured: true } });
  next.addHook("onClose", async () => { authDatabase.close(); });
  if ((await next.safeModeService.getPackageState()).active.length === 0) { for (const pkg of packages) { await next.safeModeService.importPackage({ directory: pkg.directory, manifest: pkg.manifest, keyId: pkg.keyId }, { actorUserId: "offline-e2e-admin", clientSessionId: "offline", occurredAtUtc: nowUtc }); await next.safeModeService.activatePackage({ packageId: pkg.manifest.packageId, version: pkg.manifest.version, keyId: pkg.keyId }, { actorUserId: "offline-e2e-admin", clientSessionId: "offline", occurredAtUtc: nowUtc }); } }
  const asset = (relative, reply) => { try { const body = readFileSync(join(consoleDirectory, relative)); return reply.type(contentTypes.get(extname(relative)) ?? "application/octet-stream").send(body); } catch { return reply.code(404).send({ error: "NOT_FOUND" }); } };
  next.get("/", async (_request, reply) => asset("index.html", reply)); next.get("/favicon.svg", async (_request, reply) => asset("favicon.svg", reply)); next.get("/assets/*", async (request, reply) => asset(`assets/${request.params["*"]}`, reply));
  next.post("/__test/restart", async (_request, reply) => { reply.code(202).send({ restarting: true }); setTimeout(async () => { next.server.closeAllConnections(); await next.close(); app = await build(); await app.listen({ host: "127.0.0.1", port: 4173 }); }, 100); });
  next.post("/__test/clock", async (request, reply) => { const value = request.body?.nowUtc; if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return reply.code(400).send({ error: "INVALID_CLOCK" }); clockUtc = value; return reply.code(204).send(); });
  return next;
}
app = await build(); await app.listen({ host: "127.0.0.1", port: 4173 }); process.stdout.write("live HTTPS Edge harness ready\n");
for (const signalName of ["SIGTERM", "SIGINT"]) process.on(signalName, async () => { try { await app?.close(); } finally { for (const path of [externalCertificateAuthorityPath, externalClientCertificatePath, externalClientKeyPath]) rmSync(path, { force: true }); rmSync(root, { recursive: true, force: true }); process.exit(0); } });
