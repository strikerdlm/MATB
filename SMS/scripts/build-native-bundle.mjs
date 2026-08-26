#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { chmod, cp, lstat, mkdir, mkdtemp, readFile, readdir, realpath, rm, stat, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { writeDeterministicZip } from "./deterministic-zip.mjs";

const RELEASE = "0.2.0-rc.1";
const NODE_VERSION = "22.23.2";
const OFFICIAL_NODE_RELEASE_SIGNERS = new Set([
  "5BE8A3F6C8A5C01D106C0AD820B1A390B168D356", "DD792F5973C6DE52C432CBDAC77ABFA00DDBF2B7",
  "CC68F5A3106FF448322E48ED27F5E38D5B0A215F", "8FCCA13FEF1D0C2E91008E09770F7A9A5AE15600",
  "890C08DB8579162FEE0DF9DB8BEAB4DFCF555EF4", "C82FA3AE1CBEDC6BE46B9360C43CEC45C17AB93C",
  "108F52B48DB57BB0CC439B2997B01419BD92F80A", "655F3B5C1FB3FA8D1A0CA6BDE4A7D232B936D2FD",
  "A363A499291CBBC940DD62E41F10027AF002F8B0",
]);
const smsRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const targetMetadata = Object.freeze({
  "linux-x64": { archive: `node-v${NODE_VERSION}-linux-x64.tar.xz`, executable: "bin/node", artifact: `fac-isr-sms-${RELEASE}-linux-x64.tar.gz` },
  "win32-x64": { archive: `node-v${NODE_VERSION}-win-x64.zip`, executable: "node.exe", artifact: `fac-isr-sms-${RELEASE}-win32-x64.zip` },
});

export function isOfficialNodeSignatureStatus(status) {
  return status.split(/\r?\n/u).filter((line) => line.startsWith("[GNUPG:] VALIDSIG ")).some((line) => {
    const fields = line.trim().split(/\s+/u);
    const primaryFingerprint = fields.at(-1)?.toUpperCase();
    const signingFingerprint = fields[2]?.toUpperCase();
    return OFFICIAL_NODE_RELEASE_SIGNERS.has(primaryFingerprint) || OFFICIAL_NODE_RELEASE_SIGNERS.has(signingFingerprint);
  });
}

export function validateProductionDependencyName(name) {
  if (typeof name !== "string" || !(/^(?:[A-Za-z0-9][A-Za-z0-9._-]*|@[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._-]*)$/u).test(name)) {
    throw new Error(`invalid production dependency name: ${String(name)}`);
  }
  return name;
}

function assertContained(root, candidate, label) {
  const path = relative(root, candidate);
  if (path === "" || path === ".." || path.startsWith(`..${sep}`) || isAbsolute(path)) throw new Error(`${label} resolves outside the application root`);
  return path;
}

async function assertNoSymbolicPath(root, candidate, label) {
  const path = assertContained(root, candidate, label);
  let cursor = root;
  for (const component of path.split(sep)) {
    cursor = resolve(cursor, component);
    if ((await lstat(cursor)).isSymbolicLink()) throw new Error(`${label} contains a symbolic path component`);
  }
}

function parse(argv) {
  const options = { testRuntime: false };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--test-runtime") options.testRuntime = true;
    else if (["--target", "--runtime-archive", "--runtime-checksums", "--runtime-checksums-signature", "--node-release-keyring", "--output-dir", "--app-root", "--source-date-epoch"].includes(argument)) {
      const value = argv[++index];
      if (!value || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      options[argument.slice(2).replaceAll(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = value;
    } else throw new Error(`unknown argument: ${argument}`);
  }
  for (const name of ["target", "runtimeArchive", "runtimeChecksums", "outputDir"]) if (!options[name]) throw new Error(`--${name.replaceAll(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)} is required`);
  if (!(options.target in targetMetadata)) throw new Error("target must be linux-x64 or win32-x64");
  if (!options.testRuntime && (!options.runtimeChecksumsSignature || !options.nodeReleaseKeyring)) throw new Error("production runtime verification requires signed official Node checksum metadata");
  if (!options.testRuntime && options.appRoot) throw new Error("--app-root is reserved for controlled test fixtures");
  return options;
}

function run(command, args, options = {}) {
  return new Promise((resolvePromise, reject) => {
    const stdio = options.capture
      ? [options.input === undefined ? "ignore" : "pipe", "pipe", "pipe"]
      : options.input === undefined ? "inherit" : ["pipe", "inherit", "inherit"];
    const child = spawn(command, args, { cwd: options.cwd, env: { ...process.env, TZ: "UTC", ...options.env }, stdio });
    const stdout = [];
    const stderr = [];
    child.stdout?.on("data", (chunk) => stdout.push(chunk));
    child.stderr?.on("data", (chunk) => stderr.push(chunk));
    child.once("error", reject);
    if (options.input !== undefined) child.stdin.end(options.input);
    child.once("close", (code) => {
      const result = { code, stdout: Buffer.concat(stdout).toString("utf8"), stderr: Buffer.concat(stderr).toString("utf8") };
      if (code === 0) resolvePromise(result);
      else reject(new Error(`${command} failed (${code}): ${result.stderr.trim()}`));
    });
  });
}

async function sha256(path) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) digest.update(chunk);
  return digest.digest("hex");
}

async function walk(root, directory = root) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = resolve(directory, entry.name);
    const path = relative(root, full).split(sep).join("/");
    if (entry.isSymbolicLink()) throw new Error(`symbolic links are forbidden in release bundles: ${path}`);
    if (entry.isDirectory()) found.push(...await walk(root, full));
    else if (entry.isFile()) found.push({ path, full });
    else throw new Error(`unsupported bundle entry: ${path}`);
  }
  return found.sort((left, right) => left.path.localeCompare(right.path));
}

async function makeWritable(directory) {
  try {
    await chmod(directory, 0o700);
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const full = resolve(directory, entry.name);
      if (entry.isDirectory()) await makeWritable(full);
      else if (!entry.isSymbolicLink()) await chmod(full, 0o600);
    }
  } catch (error) {
    if (!(error instanceof Error && error.code === "ENOENT")) throw error;
  }
}

function assertSafeArchivePaths(lines) {
  for (const raw of lines.split(/\r?\n/u)) {
    const path = raw.trim();
    if (!path) continue;
    const normalized = path.replaceAll("\\", "/");
    if (normalized.startsWith("/") || /^[a-zA-Z]:\//u.test(normalized) || normalized.split("/").includes("..")) throw new Error(`unsafe runtime archive path: ${path}`);
  }
}

async function verifyRuntime(options, metadata) {
  const runtimeArchive = resolve(options.runtimeArchive);
  if (basename(runtimeArchive) !== metadata.archive) throw new Error(`runtime archive must be named ${metadata.archive}`);
  const checksumText = await readFile(resolve(options.runtimeChecksums), "utf8");
  const matching = checksumText.split(/\r?\n/u).map((line) => line.match(/^([a-f0-9]{64})\s+\*?(.+)$/u)).find((match) => match?.[2] === metadata.archive);
  if (!matching) throw new Error("Node checksum metadata does not cover the runtime archive");
  if (await sha256(runtimeArchive) !== matching[1]) throw new Error("Node runtime checksum mismatch");
  if (!options.testRuntime) {
    const signatureStage = await mkdtemp(join(tmpdir(), "sms-node-signature-"));
    try {
      const verifiedChecksums = resolve(signatureStage, "SHASUMS256.txt");
      let verified;
      try {
        verified = await run("gpgv", ["--status-fd", "1", "--keyring", resolve(options.nodeReleaseKeyring), "--output", verifiedChecksums, resolve(options.runtimeChecksumsSignature)], { capture: true });
        if (await readFile(verifiedChecksums, "utf8") !== checksumText) throw new Error("signed Node checksum content does not match supplied checksum metadata");
      } catch (clearSignedError) {
        await rm(verifiedChecksums, { force: true });
        try {
          verified = await run("gpgv", ["--status-fd", "1", "--keyring", resolve(options.nodeReleaseKeyring), resolve(options.runtimeChecksumsSignature), resolve(options.runtimeChecksums)], { capture: true });
        } catch {
          throw clearSignedError;
        }
      }
      if (!isOfficialNodeSignatureStatus(verified.stdout)) throw new Error("Node checksum signature is not from a pinned official Node release signer");
    } finally {
      await rm(signatureStage, { recursive: true, force: true });
    }
  }
  return runtimeArchive;
}

async function extractRuntime(archive, target, destination, bundleRuntime) {
  const isLinux = target === "linux-x64";
  const listing = await run(isLinux ? "tar" : "unzip", isLinux ? ["-tJf", archive] : ["-Z1", archive], { capture: true });
  assertSafeArchivePaths(listing.stdout);
  if (isLinux) {
    const verbose = await run("tar", ["-tvJf", archive], { capture: true });
    if (verbose.stdout.split(/\r?\n/u).some((line) => /^[lh]/u.test(line))) throw new Error("runtime archive symbolic and hard links are forbidden");
    await run("tar", ["-xJf", archive, "-C", destination, "--no-same-owner", "--no-same-permissions"]);
  } else {
    const verbose = await run("zipinfo", ["-l", archive], { capture: true });
    if (verbose.stdout.split(/\r?\n/u).some((line) => /^l/u.test(line))) throw new Error("runtime archive symbolic links are forbidden");
    await run("unzip", ["-q", archive, "-d", destination]);
  }
  const directories = (await readdir(destination, { withFileTypes: true })).filter((entry) => entry.isDirectory());
  if (directories.length !== 1) throw new Error("runtime archive must contain exactly one root directory");
  await cp(resolve(destination, directories[0].name), bundleRuntime, { recursive: true, errorOnExist: true, force: false, verbatimSymlinks: true });
}

export async function copyRequiredApp(appRoot, destination) {
  const required = [
    "package.json", "package-lock.json", "apps/edge-api/package.json", "apps/edge-api/dist", "apps/console/dist",
    "packages/evidence/package.json", "packages/evidence/dist", "packages/safety-kernel/package.json", "packages/safety-kernel/dist",
    "packages/telemetry/package.json", "packages/telemetry/dist", "scripts/start-edge.mjs", "scripts/edge-healthcheck.mjs",
  ];
  for (const path of required) {
    const source = resolve(appRoot, path);
    const contained = relative(appRoot, source);
    if (contained.startsWith("..") || (await lstat(source)).isSymbolicLink()) throw new Error(`unsafe application input: ${path}`);
    await mkdir(dirname(resolve(destination, path)), { recursive: true });
    await cp(source, resolve(destination, path), { recursive: true, errorOnExist: true, force: false, verbatimSymlinks: true });
  }

  const runtimePackages = await Promise.all([
    "apps/edge-api/package.json",
    "packages/evidence/package.json",
    "packages/safety-kernel/package.json",
    "packages/telemetry/package.json",
  ].map(async (path) => JSON.parse(await readFile(resolve(appRoot, path), "utf8"))));
  const runtimePackagePaths = ["apps/edge-api", "packages/evidence", "packages/safety-kernel", "packages/telemetry"];
  const queue = runtimePackages.flatMap((metadata, index) => Object.keys({ ...metadata.dependencies, ...metadata.optionalDependencies })
    .filter((name) => !name.startsWith("@fac-isr/"))
    .map((name) => ({ name, requester: resolve(appRoot, runtimePackagePaths[index]) })));
  const copied = new Set();
  async function resolveDependencyInstance(name, requester) {
    validateProductionDependencyName(name);
    let directory = requester;
    for (;;) {
      const candidate = resolve(directory, "node_modules", ...name.split("/"));
      assertContained(appRoot, candidate, `production dependency ${name}`);
      try {
        const info = await lstat(candidate);
        if (info.isSymbolicLink() || !info.isDirectory()) throw new Error(`production dependency is not a real directory: ${name}`);
        await assertNoSymbolicPath(appRoot, candidate, `production dependency ${name}`);
        const canonical = await realpath(candidate);
        assertContained(appRoot, canonical, `production dependency ${name}`);
        return canonical;
      } catch (error) {
        if (!(error instanceof Error && error.code === "ENOENT")) throw error;
      }
      if (directory === appRoot) break;
      const parent = dirname(directory);
      if (relative(appRoot, parent).startsWith("..")) break;
      directory = parent;
    }
    throw new Error(`production dependency cannot be resolved from ${relative(appRoot, requester)}: ${name}`);
  }
  while (queue.length > 0) {
    const request = queue.shift();
    const source = await resolveDependencyInstance(request.name, request.requester);
    const instancePath = relative(appRoot, source).split(sep).join("/");
    if (!instancePath.startsWith("node_modules/") && !instancePath.includes("/node_modules/")) throw new Error(`unsafe production dependency instance path: ${instancePath}`);
    if (copied.has(instancePath)) continue;
    const target = resolve(destination, instancePath);
    assertContained(destination, target, `production dependency destination ${request.name}`);
    await mkdir(dirname(target), { recursive: true });
    await cp(source, target, {
      recursive: true, errorOnExist: true, force: false, verbatimSymlinks: true,
      filter: (path) => {
        const nestedPath = relative(source, path);
        return nestedPath === "" || (!nestedPath.split(sep).includes("node_modules") && basename(path) !== ".bin");
      },
    });
    copied.add(instancePath);
    const metadata = JSON.parse(await readFile(resolve(source, "package.json"), "utf8"));
    queue.push(...Object.keys({ ...metadata.dependencies, ...metadata.optionalDependencies })
      .filter((dependency) => !dependency.startsWith("@fac-isr/"))
      .map((name) => ({ name, requester: source })));
  }
  for (const name of ["evidence", "safety-kernel", "telemetry"]) {
    const packageRoot = resolve(destination, "node_modules/@fac-isr", name);
    await mkdir(packageRoot, { recursive: true });
    await cp(resolve(destination, `packages/${name}/package.json`), resolve(packageRoot, "package.json"));
    await cp(resolve(destination, `packages/${name}/dist`), resolve(packageRoot, "dist"), { recursive: true });
  }
}

async function writeMetadata(bundle, target, appRoot, testRuntime) {
  await mkdir(resolve(bundle, "config"), { recursive: true });
  const platformPaths = target === "linux-x64" ? {
    config: "/etc/fac-isr-sms", database: "/var/lib/fac-isr-sms/data/edge.sqlite", packages: "/var/lib/fac-isr-sms/packages",
    tls: "/etc/fac-isr-sms/tls", console: "/opt/fac-isr-sms/current/app/apps/console/dist",
  } : {
    config: "@PROGRAMDATA_SMS@\\config", database: "@PROGRAMDATA_SMS@\\data\\edge.sqlite", packages: "@PROGRAMDATA_SMS@\\packages",
    tls: "@PROGRAMDATA_SMS@\\config\\tls", console: "@PROGRAMFILES_SMS@\\current\\app\\apps\\console\\dist",
  };
  await writeFile(resolve(bundle, "config/sms.env.template"), [
    "SMS_DEPLOYMENT_MODE=standalone", "SMS_BIND_ADDRESS=127.0.0.1", "SMS_PORT=8443", `SMS_CONFIG_DIRECTORY=${platformPaths.config}`,
    `SMS_DATABASE_URL=${platformPaths.database}`, `SMS_PACKAGE_DIRECTORY=${platformPaths.packages}`, `SMS_CONSOLE_DIRECTORY=${platformPaths.console}`,
    `SMS_TLS_CERT_PATH=${platformPaths.tls}${target === "linux-x64" ? "/" : "\\"}server.crt`, `SMS_TLS_KEY_PATH=${platformPaths.tls}${target === "linux-x64" ? "/" : "\\"}server.key`,
    "SMS_HEALTH_HOST=127.0.0.1", "SMS_HEALTH_SERVERNAME=localhost", `SMS_HEALTH_CA_PATH=${platformPaths.tls}${target === "linux-x64" ? "/" : "\\"}server.crt`,
    `SMS_EXPORT_KEY_PATH=${platformPaths.tls}${target === "linux-x64" ? "/" : "\\"}export.key`, "SMS_EXPORT_KEY_ID=replace-with-institutional-key-id", "SMS_NETWORK=disabled", "",
  ].join(target === "linux-x64" ? "\n" : "\r\n"), { mode: 0o640 });
  await mkdir(resolve(bundle, "notices"), { recursive: true });
  const lock = JSON.parse(await readFile(resolve(appRoot, "package-lock.json"), "utf8"));
  const licenses = new Map();
  for (const metadata of Object.values(lock.packages ?? {})) if (typeof metadata?.license === "string") licenses.set(metadata.license, (licenses.get(metadata.license) ?? 0) + 1);
  await writeFile(resolve(bundle, "notices/THIRD_PARTY_NOTICES.md"), `# Third-party notices\n\nBundled production dependencies are enumerated in the SBOM fragment. No external fonts are bundled.\n\n${[...licenses].sort().map(([name, count]) => `- ${name}: ${count}`).join("\n")}\n`);
  await mkdir(resolve(bundle, "sbom"), { recursive: true });
  const components = [{ type: "framework", name: "node", version: NODE_VERSION, properties: [{ name: "fac-isr:target", value: target }] }];
  for (const packageJson of (await walk(resolve(bundle, "app/node_modules"))).filter(({ path }) => path.endsWith("package.json"))) {
    const metadata = JSON.parse(await readFile(packageJson.full, "utf8"));
    if (typeof metadata.name === "string" && typeof metadata.version === "string") components.push({ type: "library", name: metadata.name, version: metadata.version, ...(typeof metadata.license === "string" ? { licenses: [{ license: { id: metadata.license } }] } : {}) });
  }
  components.sort((left, right) => left.name.localeCompare(right.name));
  await writeFile(resolve(bundle, "sbom/runtime-fragment.cdx.json"), `${JSON.stringify({ bomFormat: "CycloneDX", specVersion: "1.6", version: 1, metadata: { component: { type: "application", name: "fac-isr-sms", version: RELEASE } }, components }, null, 2)}\n`);
  await writeFile(resolve(bundle, "release.json"), `${JSON.stringify({ release: `fac-isr-sms@${RELEASE}`, target, nodeVersion: NODE_VERSION, internet: "disabled", operationalReady: false, production: !testRuntime, runtimeProvenance: testRuntime ? "controlled-test-fixture" : "official-node-signed-checksums" }, null, 2)}\n`);
  await mkdir(resolve(bundle, "bin"), { recursive: true });
  await writeFile(resolve(bundle, target === "linux-x64" ? "bin/sms-admin" : "bin/sms-admin.cmd"), target === "linux-x64"
    ? "#!/bin/sh\nset -eu\nHERE=$(CDPATH= cd -- \"$(dirname -- \"$0\")/..\" && pwd)\nexec \"$HERE/runtime/bin/node\" \"$HERE/app/apps/edge-api/dist/admin/cli.js\" \"$@\"\n"
    : "@echo off\r\n\"%~dp0..\\runtime\\node.exe\" \"%~dp0..\\app\\apps\\edge-api\\dist\\admin\\cli.js\" %*\r\n");
  const installFiles = target === "linux-x64"
    ? [["packaging/linux/smsctl", "install/linux/smsctl"], ["packaging/linux/migrate", "install/linux/migrate"]]
    : [["packaging/windows/SmsCtl.ps1", "install/windows/SmsCtl.ps1"], ["packaging/windows/Migrate.ps1", "install/windows/Migrate.ps1"], ["packaging/windows/Start-Sms.ps1", "install/windows/Start-Sms.ps1"]];
  for (const [source, destination] of installFiles) {
    await mkdir(dirname(resolve(bundle, destination)), { recursive: true });
    await cp(resolve(smsRoot, source), resolve(bundle, destination), { errorOnExist: true, force: false });
  }
}

async function normalizeAndInventory(bundle, epoch, target) {
  const date = new Date(epoch * 1000);
  const executablePaths = new Set(target === "linux-x64" ? ["runtime/bin/node", "bin/sms-admin", "install/linux/smsctl", "install/linux/migrate"] : ["runtime/node.exe", "bin/sms-admin.cmd"]);
  const entries = await walk(bundle);
  for (const { path, full } of entries) {
    await chmod(full, executablePaths.has(path) ? 0o555 : path === "config/sms.env.template" ? 0o640 : 0o444);
    await utimes(full, date, date);
  }
  async function normalizeDirectories(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) if (entry.isDirectory()) await normalizeDirectories(resolve(directory, entry.name));
    await chmod(directory, 0o755);
    await utimes(directory, date, date);
  }
  await normalizeDirectories(bundle);
  const files = [];
  for (const { path, full } of await walk(bundle)) {
    const info = await stat(full);
    files.push({ path, sha256: await sha256(full), sizeBytes: info.size, mode: info.mode & 0o777 });
  }
  await chmod(bundle, 0o755);
  await writeFile(resolve(bundle, "inventory.json"), `${JSON.stringify({ schemaVersion: "1.0", release: `fac-isr-sms@${RELEASE}`, target, inventoryPath: "inventory.json", files }, null, 2)}\n`, { mode: 0o444 });
  await utimes(resolve(bundle, "inventory.json"), date, date);
  const inventoryInfo = await stat(resolve(bundle, "inventory.json"));
  const trustedFiles = [...files, { path: "inventory.json", sha256: await sha256(resolve(bundle, "inventory.json")), sizeBytes: inventoryInfo.size, mode: inventoryInfo.mode & 0o777 }];
  await writeFile(resolve(bundle, "inventory.tsv"), `${trustedFiles.map((file) => `${file.path}\t${file.sha256}\t${file.sizeBytes}\t${file.mode.toString(8).padStart(3, "0")}`).join("\n")}\n`, { mode: 0o444 });
  await utimes(resolve(bundle, "inventory.tsv"), date, date);
  await chmod(bundle, 0o755);
  await utimes(bundle, date, date);
}

async function build(options) {
  const metadata = targetMetadata[options.target];
  const archive = await verifyRuntime(options, metadata);
  const output = resolve(options.outputDir);
  const appRoot = await realpath(resolve(options.appRoot ?? smsRoot));
  const epoch = Number(options.sourceDateEpoch ?? process.env.SOURCE_DATE_EPOCH);
  if (!Number.isInteger(epoch) || epoch < 315532800) throw new Error("--source-date-epoch or SOURCE_DATE_EPOCH must be a deterministic epoch at or after 1980");
  const stage = await mkdtemp(join(tmpdir(), "sms-native-stage-"));
  try {
    const bundle = resolve(stage, "fac-isr-sms");
    await mkdir(bundle, { recursive: true });
    const runtimeStage = resolve(stage, "runtime-input");
    await mkdir(runtimeStage);
    await extractRuntime(archive, options.target, runtimeStage, resolve(bundle, "runtime"));
    await mkdir(resolve(bundle, "app"));
    await copyRequiredApp(appRoot, resolve(bundle, "app"));
    await writeMetadata(bundle, options.target, appRoot, options.testRuntime);
    await normalizeAndInventory(bundle, epoch, options.target);
    await mkdir(output, { recursive: true });
    const artifactName = options.testRuntime ? `TEST-ONLY-${metadata.artifact}` : metadata.artifact;
    const artifact = resolve(output, artifactName);
    await rm(artifact, { force: true });
    if (options.target === "linux-x64") {
      await run("tar", ["--sort=name", `--mtime=@${epoch}`, "--owner=0", "--group=0", "--numeric-owner", "--format=posix", "--pax-option=delete=atime,delete=ctime", "-czf", artifact, "fac-isr-sms"], { cwd: stage, env: { GZIP: "-n" } });
    } else {
      const entries = (await walk(bundle)).map(({ path, full }) => ({
        archivePath: `fac-isr-sms/${path}`,
        sourcePath: full,
        mode: new Set(["runtime/node.exe", "bin/sms-admin.cmd"]).has(path) ? 0o555 : path === "config/sms.env.template" ? 0o640 : 0o444,
      }));
      await writeDeterministicZip(artifact, entries, epoch);
    }
    process.stdout.write(`${artifact}\n`);
  } finally {
    await makeWritable(stage);
    await rm(stage, { recursive: true, force: true });
  }
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    await build(parse(process.argv.slice(2)));
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
