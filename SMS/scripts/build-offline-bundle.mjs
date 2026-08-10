#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import {
  chmod,
  cp,
  lstat,
  mkdir,
  mkdtemp,
  open,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const smsRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const SHA256 = /^[a-f0-9]{64}$/;

function parseArguments(argv) {
  const options = { output: undefined, imageRef: undefined, help: false };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--output" || argument === "--image-ref") {
      const value = argv[index + 1];
      if (value === undefined || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      if (argument === "--output") options.output = value;
      else options.imageRef = value;
      index += 1;
    } else if (argument === "--help") options.help = true;
    else throw new Error(`unknown argument: ${argument}`);
  }
  return options;
}

function safeOutputPath(value) {
  const output = resolve(smsRoot, value);
  const filesystemRoot = resolve(output, sep);
  if (output === filesystemRoot || output === smsRoot || output === dirname(smsRoot)) {
    throw new Error("refusing unsafe bundle output path");
  }
  return output;
}

async function pathExists(path) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error instanceof Error && error.code === "ENOENT") return false;
    throw error;
  }
}

async function run(command, args, { capture = false, cwd = smsRoot } = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: { ...process.env, NO_COLOR: "1" },
      stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
    });
    const stdout = [];
    const stderr = [];
    if (capture) {
      child.stdout.on("data", (chunk) => stdout.push(chunk));
      child.stderr.on("data", (chunk) => stderr.push(chunk));
    }
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      const result = {
        code: code ?? 1,
        signal,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      };
      if (code === 0) resolvePromise(result);
      else reject(new Error(`${command} ${args.join(" ")} failed (${signal ?? code})${capture && result.stderr !== "" ? `: ${result.stderr.trim()}` : ""}`));
    });
  });
}

async function sha256File(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

async function walkFiles(root, current = root) {
  const entries = await readdir(current, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = resolve(current, entry.name);
    const path = relative(root, full).split(sep).join("/");
    if (entry.isSymbolicLink()) throw new Error(`bundle source produced a symbolic link: ${path}`);
    if (entry.isDirectory()) files.push(...await walkFiles(root, full));
    else if (entry.isFile()) files.push({ path, full, sizeBytes: (await stat(full)).size });
    else throw new Error(`bundle source produced an unsupported entry: ${path}`);
  }
  return files.sort((left, right) => left.path.localeCompare(right.path));
}

function mediaType(path) {
  if (path.endsWith(".oci.tar")) return "application/vnd.oci.image.layout.v1.tar";
  const types = new Map([
    [".json", "application/json"],
    [".jsonl", "application/x-ndjson"],
    [".md", "text/markdown"],
    [".mjs", "text/javascript"],
    [".pem", "application/x-pem-file"],
    [".sig", "application/octet-stream"],
    [".yml", "application/yaml"],
  ]);
  return types.get(extname(path)) ?? "application/octet-stream";
}

async function readOciManifestDigest(path) {
  const handle = await open(path, "r");
  try {
    const info = await handle.stat();
    let offset = 0;
    while (offset + 512 <= info.size) {
      const header = Buffer.alloc(512);
      const result = await handle.read(header, 0, 512, offset);
      if (result.bytesRead !== 512) throw new Error("truncated OCI tar header");
      if (header.every((byte) => byte === 0)) break;
      const name = header.subarray(0, 100).toString("utf8").replace(/\0.*$/s, "");
      const prefix = header.subarray(345, 500).toString("utf8").replace(/\0.*$/s, "");
      const entryPath = prefix === "" ? name : `${prefix}/${name}`;
      const size = Number.parseInt(header.subarray(124, 136).toString("ascii").replace(/\0.*$/s, "").trim() || "0", 8);
      if (!Number.isSafeInteger(size) || size < 0 || offset + 512 + size > info.size) throw new Error(`invalid OCI tar entry: ${entryPath}`);
      if (entryPath === "index.json") {
        const body = Buffer.alloc(size);
        const bodyResult = await handle.read(body, 0, size, offset + 512);
        if (bodyResult.bytesRead !== size) throw new Error("truncated OCI index");
        const index = JSON.parse(body.toString("utf8"));
        const digest = index?.manifests?.[0]?.digest;
        if (typeof digest !== "string" || !/^sha256:[a-f0-9]{64}$/.test(digest)) throw new Error("OCI index has no valid image manifest digest");
        return digest;
      }
      offset += 512 + Math.ceil(size / 512) * 512;
    }
  } finally {
    await handle.close();
  }
  throw new Error("OCI archive does not contain index.json");
}

async function copyRegulatoryPackage(stage) {
  const source = resolve(smsRoot, "docs/provenance");
  const destination = resolve(stage, "packages/regulatory");
  await mkdir(destination, { recursive: true, mode: 0o755 });
  await cp(resolve(source, "package-content"), resolve(destination, "package-content"), { recursive: true, errorOnExist: true, force: false });
  for (const name of [
    "evidence-package-manifest.json",
    "evidence-package-manifest.sig",
    "evidence-package-public-key.pem",
  ]) {
    await cp(resolve(source, name), resolve(destination, name), { errorOnExist: true, force: false });
  }
  const manifest = JSON.parse(await readFile(resolve(destination, "evidence-package-manifest.json"), "utf8"));
  await writeFile(resolve(stage, "packages/package-index.json"), `${JSON.stringify({
    schemaVersion: "1.0",
    packages: [{
      packageId: manifest.packageId,
      kind: manifest.kind,
      version: manifest.version,
      contentSha256: manifest.contentSha256,
      qualification: manifest.qualification,
      path: "packages/regulatory",
    }],
  }, null, 2)}\n`, { encoding: "utf8", mode: 0o644 });
  return manifest;
}

async function writeSbom(stage, builtAtUtc) {
  const result = await run("npm", ["sbom", "--sbom-format", "cyclonedx"], { capture: true });
  const sbom = JSON.parse(result.stdout);
  if (sbom.bomFormat !== "CycloneDX") throw new Error("npm did not produce a CycloneDX SBOM");
  delete sbom.serialNumber;
  if (sbom.metadata !== undefined) sbom.metadata.timestamp = builtAtUtc;
  await writeFile(resolve(stage, "sbom/npm.cdx.json"), `${JSON.stringify(sbom, null, 2)}\n`, { encoding: "utf8", mode: 0o644 });
}

async function writeLicenseNotices(stage) {
  const lock = JSON.parse(await readFile(resolve(smsRoot, "package-lock.json"), "utf8"));
  const licenses = new Map();
  for (const [path, metadata] of Object.entries(lock.packages ?? {})) {
    if (!path.startsWith("node_modules/") || typeof metadata?.license !== "string") continue;
    const license = metadata.license;
    licenses.set(license, (licenses.get(license) ?? 0) + 1);
  }
  const rows = [...licenses.entries()].sort(([left], [right]) => left.localeCompare(right));
  const notice = [
    "# Third-party notices and font handling",
    "",
    "This transfer bundle includes the exact dependency inventory in `../sbom/npm.cdx.json`.",
    "The console bundles no external font binaries; it uses the receiving workstation's system font stack.",
    "Provider-specific map, terrain, and font licenses must be accepted before those separately signed packages are added.",
    "",
    "| Declared license | Locked packages |",
    "| --- | ---: |",
    ...rows.map(([license, count]) => `| ${license.replaceAll("|", "\\|")} | ${count} |`),
    "",
  ].join("\n");
  await writeFile(resolve(stage, "licenses/THIRD_PARTY_NOTICES.md"), notice, { encoding: "utf8", mode: 0o644 });
}

async function writeInstallFiles(stage, imageRef, releaseId) {
  await cp(resolve(smsRoot, "docker/compose.edge.yml"), resolve(stage, "install/compose.edge.yml"), { errorOnExist: true, force: false });
  await writeFile(resolve(stage, "install/.env.example"), [
    `SMS_EDGE_IMAGE=${imageRef}`,
    "SMS_EDGE_PORT=8443",
    "SMS_DATA_DIR=/srv/fac-isr-sms/data",
    "SMS_PACKAGE_DIR=/srv/fac-isr-sms/packages",
    "SMS_TLS_DIR=/srv/fac-isr-sms/tls",
    "",
  ].join("\n"), { encoding: "utf8", mode: 0o644 });
  const instructions = `# FAC ISR SMS disconnected installation — ${releaseId}

1. On the disconnected receiving host, verify the transfer directory before loading anything:
   \`node bin/verify-offline.mjs --bundle . --no-network\`.
2. Place the database directory on an institutionally approved encrypted volume and set \`SMS_DATA_DIR\`.
3. Place separately approved signed data packages under \`SMS_PACKAGE_DIR\`; do not replace the bundled regulatory evidence in place.
4. Provision a local TLS certificate and a private key outside this bundle as \`server.crt\` and \`server.key\`; set the key mode to 0400 or 0600.
5. Load the locked image with \`docker load --input images/fac-isr-sms-edge.oci.tar\` and set \`SMS_EDGE_IMAGE=${imageRef}\`.
6. Start with \`docker compose --env-file install/.env -f install/compose.edge.yml up -d\`.

The compose network is internal and publishes TLS only on loopback. The root filesystem is read-only, Linux capabilities are dropped, package mounts are read-only, and the service runs as UID/GID 10001. Host encryption, backup encryption, key custody, and qualified operational package acceptance remain receiving-site controls.

This bundle is not an operational acceptance artifact. Planned map/terrain sources and the unsigned P6.2 release manifest keep \`operationalReady\` false until later qualified release tasks are completed.
`;
  await writeFile(resolve(stage, "install/README.md"), instructions, { encoding: "utf8", mode: 0o644 });
}

async function buildBundle(output, imageRef) {
  if (await pathExists(output)) throw new Error(`output already exists; refusing to overwrite: ${output}`);
  const parent = dirname(output);
  await mkdir(parent, { recursive: true, mode: 0o700 });
  const stage = await mkdtemp(join(parent, ".offline-bundle-"));
  let published = false;
  try {
    for (const directory of ["bin", "images", "install", "licenses", "packages", "provenance", "reports", "runtime", "sbom"]) {
      await mkdir(resolve(stage, directory), { recursive: true, mode: 0o755 });
    }

    const commitResult = await run("git", ["rev-parse", "HEAD"], { capture: true, cwd: resolve(smsRoot, "..") });
    const commit = commitResult.stdout.trim();
    if (!/^[a-f0-9]{40}$/.test(commit)) throw new Error("could not resolve the build commit");
    const timeResult = await run("git", ["show", "-s", "--format=%cI", commit], { capture: true, cwd: resolve(smsRoot, "..") });
    const builtAtUtc = new Date(timeResult.stdout.trim()).toISOString();
    const releaseId = `sms-${commit.slice(0, 12)}`;

    process.stdout.write(`Building ${imageRef} for linux/amd64...\n`);
    await run("docker", [
      "build",
      "--platform", "linux/amd64",
      "--build-arg", `BUILD_COMMIT=${commit}`,
      "--tag", imageRef,
      ".",
    ]);

    const smoke = await run("docker", [
      "run",
      "--rm",
      "--network", "none",
      "--read-only",
      "--cap-drop", "ALL",
      "--security-opt", "no-new-privileges:true",
      "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,uid=10001,gid=10001,mode=0700",
      imageRef,
      "/opt/sms/bin/healthcheck",
    ], { capture: true });
    await writeFile(resolve(stage, "reports/image-smoke.json"), `${JSON.stringify({
      schemaVersion: "1.0",
      status: "pass",
      imageRef,
      testedAtUtc: builtAtUtc,
      networkMode: "none",
      readOnlyRoot: true,
      output: smoke.stdout.trim(),
    }, null, 2)}\n`, { encoding: "utf8", mode: 0o644 });

    const imagePath = resolve(stage, "images/fac-isr-sms-edge.oci.tar");
    process.stdout.write("Exporting OCI-compatible image archive...\n");
    await run("docker", ["image", "save", "--output", imagePath, imageRef]);
    const archiveSha256 = await sha256File(imagePath);
    const manifestDigest = await readOciManifestDigest(imagePath);
    if (!SHA256.test(archiveSha256)) throw new Error("OCI archive digest is invalid");

    const regulatory = await copyRegulatoryPackage(stage);
    await cp(resolve(smsRoot, "docs/provenance/map-package-register.jsonl"), resolve(stage, "provenance/map-package-register.jsonl"), { errorOnExist: true, force: false });
    await cp(resolve(smsRoot, "docs/provenance/kernel-golden-case-report.md"), resolve(stage, "provenance/kernel-golden-case-report.md"), { errorOnExist: true, force: false });
    await cp(resolve(smsRoot, "scripts/verify-offline.mjs"), resolve(stage, "bin/verify-offline.mjs"), { errorOnExist: true, force: false });
    await chmod(resolve(stage, "bin/verify-offline.mjs"), 0o555);
    await writeFile(resolve(stage, "runtime/schema.json"), `${JSON.stringify({
      schemaVersion: 1,
      journalMode: "WAL",
      foreignKeys: true,
      busyTimeoutMs: 5_000,
      databasePath: "/var/lib/fac-isr/data/edge.sqlite",
    }, null, 2)}\n`, { encoding: "utf8", mode: 0o644 });
    await writeSbom(stage, builtAtUtc);
    await writeLicenseNotices(stage);
    await writeInstallFiles(stage, imageRef, releaseId);

    const artifacts = await walkFiles(stage);
    const fileRecords = [];
    for (const artifact of artifacts) {
      fileRecords.push({
        path: artifact.path,
        sha256: await sha256File(artifact.full),
        sizeBytes: artifact.sizeBytes,
        mediaType: mediaType(artifact.path),
      });
    }
    const manifest = {
      schemaVersion: "1.0",
      releaseId,
      commit,
      builtAtUtc,
      nodeVersion: "22.23.2",
      image: {
        path: "images/fac-isr-sms-edge.oci.tar",
        ref: imageRef,
        platform: "linux/amd64",
        archiveSha256,
        manifestDigest,
      },
      packageIds: [regulatory.packageId],
      files: fileRecords,
      limitations: [
        "Release manifest signing is implemented in P6.3; this P6.2 checksum manifest is unsigned.",
        "Approved terrain, map, AIP, terminology-policy, and operational policy packages must be staged separately.",
        "Qualified FAC/AAAES operational acceptance is not represented by this bundle.",
      ],
    };
    await writeFile(resolve(stage, "bundle-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, { encoding: "utf8", mode: 0o644 });

    const verification = await run(process.execPath, [
      resolve(stage, "bin/verify-offline.mjs"),
      "--bundle", stage,
      "--no-network",
      "--as-of", builtAtUtc,
      "--json",
    ], { capture: true });
    const report = JSON.parse(verification.stdout);
    if (report.ok !== true) throw new Error("new bundle did not pass its standalone integrity verifier");

    await rename(stage, output);
    published = true;
    process.stdout.write(`PASS offline bundle integrity (${report.checks.length} checks; operationalReady=${report.operationalReady})\n`);
    process.stdout.write(`${output}\n`);
  } finally {
    if (!published) await rm(stage, { recursive: true, force: true });
  }
}

async function main() {
  let options;
  try {
    options = parseArguments(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
    return;
  }
  if (options.help) {
    process.stdout.write("Usage: node scripts/build-offline-bundle.mjs --output <directory> [--image-ref <name:tag>]\n");
    return;
  }
  if (options.output === undefined) {
    process.stderr.write("--output is required\n");
    process.exitCode = 2;
    return;
  }
  const output = safeOutputPath(options.output);
  const imageRef = options.imageRef ?? `fac-isr-sms-edge:${process.env.SMS_IMAGE_TAG ?? "offline"}`;
  if (!/^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*$/u.test(imageRef)) {
    process.stderr.write("--image-ref is not a safe local image reference\n");
    process.exitCode = 2;
    return;
  }
  try {
    await buildBundle(output, imageRef);
  } catch (error) {
    process.stderr.write(`FAIL offline bundle build: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}

await main();
