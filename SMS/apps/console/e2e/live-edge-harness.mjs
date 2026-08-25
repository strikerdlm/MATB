import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { extname, join } from "node:path";
import { buildServer } from "../../edge-api/dist/server.js";
import { openDatabase } from "../../edge-api/dist/db/migrate.js";
import { LocalIdentityStore } from "../../edge-api/dist/auth/identity.js";
import { SqliteTrustedKeyStore } from "../../edge-api/dist/services/safe-mode.js";
import { DeterministicSafetyEvaluationProvider } from "../../edge-api/dist/services/safety-evaluation.js";
import { manifestContentDigest, signManifest } from "@fac-isr/evidence";

const root = mkdtempSync(join(tmpdir(), "sms-live-console-"));
const databaseUrl = join(root, "edge.sqlite");
const packageDirectory = join(root, "packages");
const certPath = join(root, "server.crt");
const keyPath = join(root, "server.key");
const consoleDirectory = new URL("../dist/", import.meta.url).pathname;
const password = "correct horse battery staple";
const nowUtc = "2026-08-25T12:00:00.000Z";
const fingerprint = "a".repeat(64);
mkdirSync(packageDirectory);
execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1", "-keyout", keyPath, "-out", certPath], { stdio: "ignore" });

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
  for (const [userId, roles] of [["maintainer-1", ["maintainer"]], ["operator-1", ["operator"]], ["safety-1", ["safety-officer"]], ["commander-1", ["commander"]], ["administrator-1", ["administrator"]]]) identities.register({ userId, displayName: userId, roles, missionIds: ["mission-1"], password });
  const trust = new SqliteTrustedKeyStore(database);
  for (const pkg of packages) trust.add({ keyId: pkg.keyId, scope: pkg.manifest.kind, algorithm: "rsa-sha256", publicKeyPem: authorityPublic, addedAtUtc: nowUtc, addedByUserId: "offline-e2e-admin" });
  database.close();
}

const safetyEvaluationProvider = new DeterministicSafetyEvaluationProvider({ now: () => nowUtc, resolve: async () => ({ requirements: [], policy: { packageId: "policy-console-e2e", version: "1.0.0", status: "approved", delegatedAuthorities: [], freshness: { aip: { maxAgeMinutes: 120, critical: true }, notam: { maxAgeMinutes: 120, critical: true }, weather: { maxAgeMinutes: 120, critical: true }, terrain: { maxAgeMinutes: 120, critical: true }, airspace: { maxAgeMinutes: 120, critical: true }, policy: { maxAgeMinutes: 120, critical: true }, regulation: { maxAgeMinutes: 120, critical: true } }, signature: "e2e" }, evidenceSnapshot: { snapshotId: "evidence-1", acceptedEvidenceIds: [] }, policyPackage: { packageId: "policy-console-e2e", version: "1.0.0" }, terminologyPackage: { packageId: "terminology-console-e2e", version: "1.0.0" }, evidencePackage: { packageId: "evidence-console-e2e", version: "1.0.0" } }) });

const mission = { id: "mission-1:r0", missionId: "mission-1", revision: 0, profileId: "fac-state-aviation", state: "Draft", aircraft: [{ aircraftId: "aircraft-1", aircraftClass: "II", configuration: "unarmed-isr", operatorUserId: "operator-1", maintenanceReleaseId: "maintenance-1" }], gcs: { gcsId: "gcs-1", configurationHash: "gcs-hash-1" }, payload: { payloadId: "payload-1", configurationHash: "payload-hash-1" }, battery: { batteryId: "battery-1", chemistry: "li-po", capacityWh: 500, cycleCount: 12 }, software: { componentId: "flight-software", version: "1.0.0", integrityHash: "software-hash-1" }, flightRule: "VFR", visualCondition: "VLOS", altitude: { minimumMetersAgl: 30, maximumMetersAgl: 120 }, schedule: { plannedStartUtc: nowUtc, plannedEndUtc: "2026-08-25T13:00:00.000Z" }, configuration: "unarmed-isr", route: { areaId: "area-1", routeHash: "route-hash-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" }, crew: [{ userId: "operator-1", role: "operator", aircraftId: "aircraft-1", qualified: true, recencyCurrent: true, dutyStatus: "available" }, { userId: "maintainer-1", role: "maintainer", qualified: true, recencyCurrent: true, dutyStatus: "available" }, { userId: "safety-1", role: "safety", qualified: true, recencyCurrent: true, dutyStatus: "available" }, { userId: "commander-1", role: "commander", qualified: true, recencyCurrent: true, dutyStatus: "available" }], evidenceSnapshotId: "evidence-1", policyPackageId: "policy-console-e2e", dataSnapshots: [{ snapshotId: "weather-1", kind: "weather", packageId: "weather-pack", status: "current", capturedAtUtc: nowUtc }], riskAssessment: { hazardIds: ["hazard-1"], mitigationIds: ["mitigation-1"], status: "complete", reserve: { recoveryPercent: 30, diversionPercent: 20, contingencyPercent: 10 } } };

const contentTypes = new Map([[".css", "text/css; charset=utf-8"], [".html", "text/html; charset=utf-8"], [".js", "text/javascript; charset=utf-8"], [".svg", "image/svg+xml"]]);
let app;
async function build() {
  const next = await buildServer({ deploymentMode: "standalone", bindAddress: "127.0.0.1", port: 4173, databaseUrl, packageDirectory, consoleDirectory, tls: { certPath, keyPath, clientCaPath: certPath }, telemetryAdapters: [{ fingerprintSha256: fingerprint, adapterId: "adapter-e2e", aircraftIds: ["aircraft-1"] }] }, { now: () => nowUtc, safetyEvaluationProvider, exportSigner, telemetryPeerIdentity: () => ({ authorized: true, fingerprintSha256: fingerprint }), readiness: { tlsConfigured: true, exportKeyConfigured: true } });
  if ((await next.safeModeService.getPackageState()).active.length === 0) { for (const pkg of packages) { await next.safeModeService.importPackage({ directory: pkg.directory, manifest: pkg.manifest, keyId: pkg.keyId }, { actorUserId: "offline-e2e-admin", clientSessionId: "offline", occurredAtUtc: nowUtc }); await next.safeModeService.activatePackage({ packageId: pkg.manifest.packageId, version: pkg.manifest.version, keyId: pkg.keyId }, { actorUserId: "offline-e2e-admin", clientSessionId: "offline", occurredAtUtc: nowUtc }); } }
  const unseeded = next.missionService.listMissions().length === 0;
  if (unseeded) await next.missionService.createMission(mission, { actorUserId: "commander-1", clientSessionId: "e2e-provision", occurredAtUtc: nowUtc });
  if (unseeded) next.telemetryService.ingest({ revisionId: "mission-1:r0", sequence: 1, event: { eventId: "telemetry-e2e-1", aircraftId: "aircraft-1", observedAtUtc: nowUtc, position: { lat: 4.7, lon: -74.1, altitudeMslM: 1250 }, energy: { stateOfChargePercent: 72 }, platform: { propulsion: "normal", gnss: "normal", c2Link: "normal" }, sourcePackageIds: ["policy-console-e2e"] } }, { authorized: true, fingerprintSha256: fingerprint }, ["aircraft-1"]);
  const asset = (relative, reply) => { try { const body = readFileSync(join(consoleDirectory, relative)); return reply.type(contentTypes.get(extname(relative)) ?? "application/octet-stream").send(body); } catch { return reply.code(404).send({ error: "NOT_FOUND" }); } };
  next.get("/", async (_request, reply) => asset("index.html", reply)); next.get("/favicon.svg", async (_request, reply) => asset("favicon.svg", reply)); next.get("/assets/*", async (request, reply) => asset(`assets/${request.params["*"]}`, reply));
  next.post("/__test/restart", async (_request, reply) => { reply.code(202).send({ restarting: true }); setTimeout(async () => { next.server.closeAllConnections(); await next.close(); app = await build(); await app.listen({ host: "127.0.0.1", port: 4173 }); }, 100); });
  return next;
}
app = await build(); await app.listen({ host: "127.0.0.1", port: 4173 }); process.stdout.write("live HTTPS Edge harness ready\n");
for (const signalName of ["SIGTERM", "SIGINT"]) process.on(signalName, async () => { try { await app?.close(); } finally { rmSync(root, { recursive: true, force: true }); process.exit(0); } });
