#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { lstat, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import { dirname, relative, resolve, sep } from "node:path";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";
import { inspectCandidateArtifact } from "./verify-technical-release.mjs";

const EVIDENCE_TYPES = new Set([
  "dependency-scan", "oci-vulnerability-scan", "malware-scan", "native-linux-smoke",
  "native-windows-smoke", "oci-linux-smoke", "ubuntu-ci", "windows-ci",
]);

function parse(argv) {
  const [command, ...rest] = argv;
  const options = { command, testOnlyFixture: false };
  for (let index = 0; index < rest.length; index += 1) {
    const argument = rest[index];
    if (argument === "--test-only-fixture") options.testOnlyFixture = true;
    else if (argument.startsWith("--")) {
      const value = rest[++index];
      if (!value || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      const key = argument.slice(2).replaceAll(/-([a-z])/gu, (_, letter) => letter.toUpperCase());
      if (key === "artifact") options.artifact = [...(options.artifact ?? []), value];
      else options[key] = value;
    } else throw new Error(`unknown argument: ${argument}`);
  }
  return options;
}

const ARTIFACT_TARGETS = new Set(["linux-x64", "win32-x64", "linux-amd64-oci"]);

function artifactValues(options) {
  return Array.isArray(options.artifact) ? options.artifact : [];
}

async function artifactBindings(options) {
  const bindings = {};
  for (const specification of artifactValues(options)) {
    const separator = specification.indexOf("=");
    if (separator < 1) throw new Error("--artifact must use target=path");
    const target = specification.slice(0, separator);
    const path = specification.slice(separator + 1);
    if (!ARTIFACT_TARGETS.has(target) || !path || Object.hasOwn(bindings, target)) throw new Error(`invalid or duplicate artifact target: ${target}`);
    await lstat(resolve(path));
    bindings[target] = await hashFile(resolve(path));
  }
  return bindings;
}

function requireExactTargets(bindings, expected, type) {
  const actual = Object.keys(bindings).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) throw new Error(`${type} requires exact artifact targets: ${wanted.join(", ")}`);
}

function scannerFindings(type, document, threshold) {
  if (type === "dependency-scan") {
    if (threshold !== "low" || !Number.isSafeInteger(document?.auditReportVersion) || !Number.isInteger(document?.metadata?.vulnerabilities?.total)) throw new Error("dependency scan requires npm-audit JSON and --threshold low");
    return document.metadata.vulnerabilities.total;
  }
  if (type === "oci-vulnerability-scan") {
    if (threshold !== "high" || !Array.isArray(document?.matches)) throw new Error("OCI scan requires Grype JSON and --threshold high");
    return document.matches.filter((match) => new Set(["high", "critical"]).has(String(match?.vulnerability?.severity).toLowerCase())).length;
  }
  if (type === "malware-scan") {
    if (threshold !== "zero-malware" || !Number.isInteger(document?.malwareFound) || !Number.isInteger(document?.errors)) throw new Error("malware scan requires normalized JSON and --threshold zero-malware");
    return document.malwareFound + document.errors;
  }
  throw new Error(`${type} does not accept scanner input`);
}

async function hashFile(path) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) digest.update(chunk);
  return digest.digest("hex");
}

async function json(path, value) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o644 });
}

function source(options) {
  if (!/^[a-f0-9]{40}$/u.test(options.sourceCommit ?? "")) throw new Error("--source-commit must be exactly 40 lowercase hex characters");
  return options.sourceCommit;
}

function timestamp(options) {
  const value = options.generatedAtUtc ?? new Date().toISOString();
  if (new Date(value).toISOString() !== value) throw new Error("--generated-at-utc must be exact UTC");
  return value;
}

function run(command, args, cwd) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { cwd, env: { ...process.env, NO_COLOR: "1" }, stdio: ["ignore", "pipe", "pipe"] });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", reject);
    child.once("close", (code) => {
      if (code === 0) resolvePromise(Buffer.concat(stdout));
      else reject(new Error(`${command} failed (${code}): ${Buffer.concat(stderr).toString("utf8").trim()}`));
    });
  });
}

async function inventory(options) {
  const artifact = artifactValues(options);
  if (artifact.length !== 1 || artifact[0].includes("=") || !options.target || !options.output) throw new Error("inventory requires one path-only --artifact, --target, and --output");
  const inspected = await inspectCandidateArtifact(artifact[0], options.target, { testOnlyFixture: options.testOnlyFixture });
  await json(resolve(options.output), {
    schemaVersion: "1.0",
    ...(options.testOnlyFixture ? { fixtureClassification: "TEST-ONLY-NON-PRODUCTION" } : {}),
    sourceCommit: source(options),
    generatedAtUtc: timestamp(options),
    ...inspected,
  });
}

async function sbom(options) {
  if (!options.output) throw new Error("sbom requires --output");
  const bindings = await artifactBindings(options);
  requireExactTargets(bindings, ARTIFACT_TARGETS, "sbom");
  const output = await run("npm", ["sbom", "--sbom-format", "cyclonedx"], process.cwd());
  const document = JSON.parse(output.toString("utf8"));
  if (document.bomFormat !== "CycloneDX" || !Array.isArray(document.components) || document.components.length === 0) throw new Error("npm returned an incomplete CycloneDX SBOM");
  await json(resolve(options.output), {
    schemaVersion: "1.0",
    type: "sbom",
    sourceCommit: source(options),
    generatedAtUtc: timestamp(options),
    status: "pass",
    artifactSha256s: bindings,
    bomFormat: document.bomFormat,
    specVersion: document.specVersion,
    components: document.components,
  });
}

async function attest(options) {
  if (!EVIDENCE_TYPES.has(options.type) || !options.output) throw new Error("attest requires a supported --type and --output");
  const record = {
    schemaVersion: "1.0",
    ...(options.testOnlyFixture ? { fixtureClassification: "TEST-ONLY-NON-PRODUCTION" } : {}),
    type: options.type,
    sourceCommit: source(options),
    generatedAtUtc: timestamp(options),
    status: "pass",
  };
  if (options.platform) record.platform = options.platform;
  const bindings = await artifactBindings(options);
  const targetRequirements = {
    "dependency-scan": ARTIFACT_TARGETS,
    "oci-vulnerability-scan": new Set(["linux-amd64-oci"]),
    "malware-scan": ARTIFACT_TARGETS,
    "native-linux-smoke": new Set(["linux-x64"]),
    "native-windows-smoke": new Set(["win32-x64"]),
    "oci-linux-smoke": new Set(["linux-amd64-oci"]),
  };
  if (targetRequirements[options.type]) requireExactTargets(bindings, targetRequirements[options.type], options.type);
  if (options.type.endsWith("-smoke")) {
    record.artifactSha256 = Object.values(bindings)[0];
  } else if (Object.keys(bindings).length > 0) {
    record.artifactSha256s = bindings;
  }
  if (options.scanner) record.scanner = options.scanner;
  if (options.input) {
    if (!options.scanner || !options.scannerOutputPath || !options.threshold) throw new Error("scanner attestations require --scanner, --scanner-output-path, and --threshold");
    if (options.scannerOutputPath.startsWith("/") || options.scannerOutputPath.split(/[\\/]/u).includes("..")) throw new Error("--scanner-output-path must be a contained relative path");
    const input = resolve(options.input);
    const document = JSON.parse(await readFile(input, "utf8"));
    const findings = scannerFindings(options.type, document, options.threshold);
    if (findings !== 0) throw new Error(`${options.type} found ${findings} findings at or above ${options.threshold}`);
    record.scannerOutputPath = options.scannerOutputPath.replaceAll("\\", "/");
    record.scannerOutputSha256 = await hashFile(input);
    record.threshold = options.threshold;
    record.findingsAtOrAboveThreshold = findings;
  }
  if (options.clean === "true") record.clean = true;
  await json(resolve(options.output), record);
}

async function files(root, directory = root) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = resolve(directory, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`symbolic evidence path is forbidden: ${full}`);
    if (entry.isDirectory()) found.push(...await files(root, full));
    else if (entry.isFile()) found.push({ path: relative(root, full).split(sep).join("/"), full });
    else throw new Error(`unsupported evidence entry: ${full}`);
  }
  return found.sort((left, right) => left.path.localeCompare(right.path));
}

async function assemble(options) {
  if (!options.candidate || !options.output) throw new Error("assemble requires --candidate and --output");
  const root = resolve(options.candidate);
  const prefix = options.testOnlyFixture ? "TEST-ONLY-" : "";
  const targetFiles = [
    ["linux-x64", "native", `${prefix}fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz`],
    ["win32-x64", "native", `${prefix}fac-isr-sms-0.2.0-rc.1-win32-x64.zip`],
    ["linux-amd64-oci", "oci", `${prefix}fac-isr-sms-0.2.0-rc.1-linux-amd64.oci.tar`],
  ];
  const artifacts = [];
  for (const [target, kind, name] of targetFiles) {
    const artifact = resolve(root, "artifacts", name);
    const inventoryPath = resolve(root, "inventories", `${target}.json`);
    const inventory = JSON.parse(await readFile(inventoryPath, "utf8"));
    const info = await stat(artifact);
    artifacts.push({
      target, kind, path: `artifacts/${name}`, sha256: await hashFile(artifact), sizeBytes: info.size,
      inventoryPath: `inventories/${target}.json`, inventorySha256: await hashFile(inventoryPath),
    });
    if (inventory.artifactSha256 !== artifacts.at(-1).sha256) throw new Error(`${target} inventory is stale`);
  }
  const evidence = [];
  for (const item of await files(resolve(root, "evidence"))) {
    const record = JSON.parse(await readFile(item.full, "utf8"));
    if (typeof record.type === "string") evidence.push({
      type: record.type,
      path: `evidence/${item.path}`,
      sha256: await hashFile(item.full),
      ...(record.scannerOutputPath ? {
        scannerOutputPath: record.scannerOutputPath,
        scannerOutputSha256: record.scannerOutputSha256,
      } : {}),
    });
  }
  evidence.sort((left, right) => left.type.localeCompare(right.type));
  await json(resolve(options.output), {
    schemaVersion: "1.0",
    ...(options.testOnlyFixture ? { fixtureClassification: "TEST-ONLY-NON-PRODUCTION" } : {}),
    releaseId: `${prefix}fac-isr-sms@0.2.0-rc.1`,
    version: "0.2.0-rc.1",
    sourceCommit: source(options),
    generatedAtUtc: timestamp(options),
    technicalReady: true,
    operationalReady: false,
    artifacts,
    evidence,
  });
}

async function main() {
  const options = parse(process.argv.slice(2));
  if (options.command === "inventory") await inventory(options);
  else if (options.command === "sbom") await sbom(options);
  else if (options.command === "attest") await attest(options);
  else if (options.command === "assemble") await assemble(options);
  else throw new Error("command must be inventory, sbom, attest, or assemble");
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
