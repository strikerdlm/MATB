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
      options[argument.slice(2).replaceAll(/-([a-z])/gu, (_, letter) => letter.toUpperCase())] = value;
    } else throw new Error(`unknown argument: ${argument}`);
  }
  return options;
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
  if (!options.artifact || !options.target || !options.output) throw new Error("inventory requires --artifact, --target, and --output");
  const inspected = await inspectCandidateArtifact(options.artifact, options.target, { testOnlyFixture: options.testOnlyFixture });
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
  const output = await run("npm", ["sbom", "--sbom-format", "cyclonedx"], process.cwd());
  const document = JSON.parse(output.toString("utf8"));
  if (document.bomFormat !== "CycloneDX" || !Array.isArray(document.components) || document.components.length === 0) throw new Error("npm returned an incomplete CycloneDX SBOM");
  await json(resolve(options.output), {
    schemaVersion: "1.0",
    type: "sbom",
    sourceCommit: source(options),
    generatedAtUtc: timestamp(options),
    status: "pass",
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
  if (options.artifact) {
    await lstat(resolve(options.artifact));
    record.artifactSha256 = await hashFile(resolve(options.artifact));
  }
  if (options.scanner) record.scanner = options.scanner;
  if (options.input) {
    await lstat(resolve(options.input));
    record.scannerOutputSha256 = await hashFile(resolve(options.input));
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
    if (typeof record.type === "string") evidence.push({ type: record.type, path: `evidence/${item.path}`, sha256: await hashFile(item.full) });
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
