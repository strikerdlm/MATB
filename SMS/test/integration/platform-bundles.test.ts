import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { chmod, chown, link, mkdir, mkdtemp, readFile, readdir, readlink, rm, stat, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { createServer } from "node:https";
import { promisify } from "node:util";
import { afterEach, describe, expect, test } from "vitest";
import { copyRequiredApp, isOfficialNodeSignatureStatus, validateProductionDependencyName } from "../../scripts/build-native-bundle.mjs";
import { writeDeterministicZip } from "../../scripts/deterministic-zip.mjs";
import { buildInstalledRequestOptions } from "../../scripts/edge-healthcheck.mjs";
import { verifyPlatformInventory } from "../../scripts/verify-platform-inventory.mjs";

const exec = promisify(execFile);
const smsRoot = process.cwd();
const builder = resolve(smsRoot, "scripts/build-native-bundle.mjs");
const linuxInstaller = resolve(smsRoot, "packaging/linux/smsctl");
const ociPreflight = resolve(smsRoot, "docker/preflight.sh");
const healthcheck = resolve(smsRoot, "scripts/edge-healthcheck.mjs");
const temporaryDirectories: string[] = [];
const isWindows = process.platform === "win32";

async function temporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "sms-platform-bundle-"));
  temporaryDirectories.push(directory);
  return directory;
}

async function sha256(path: string): Promise<string> {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

async function createAppFixture(root: string): Promise<void> {
  const lockPackages = {
    "": { name: "fac-isr-sms", version: "0.2.0-rc.1" },
    "node_modules/fastify": { name: "fastify", version: "5.6.1", license: "MIT", dependencies: { "fast-content-type-parse": "2.0.0" } },
    "node_modules/fast-content-type-parse": { name: "fast-content-type-parse", version: "2.0.0", license: "MIT" },
    "node_modules/ajv": { name: "ajv", version: "8.17.1", license: "MIT", dependencies: { "fast-uri": "3.0.6" } },
    "node_modules/ajv/node_modules/fast-uri": { name: "fast-uri", version: "3.0.6", license: "BSD-3-Clause" },
    "node_modules/light-my-request": { name: "light-my-request", version: "6.6.0", license: "BSD-3-Clause", dependencies: { "process-warning": "5.0.0" } },
    "node_modules/light-my-request/node_modules/process-warning": { name: "process-warning", version: "5.0.0", license: "MIT" },
    "node_modules/thread-stream": { name: "thread-stream", version: "3.1.0", license: "MIT", dependencies: { "real-require": "0.2.0" } },
    "node_modules/thread-stream/node_modules/real-require": { name: "real-require", version: "0.2.0", license: "MIT" },
  };
  const files = new Map<string, string>([
    ["package.json", JSON.stringify({ name: "fac-isr-sms", version: "0.2.0-rc.1" })],
    ["package-lock.json", JSON.stringify({ lockfileVersion: 3, packages: lockPackages })],
    ["apps/edge-api/package.json", JSON.stringify({ name: "@fac-isr/edge-api", version: "0.2.0-rc.1", dependencies: { fastify: "5.6.1", ajv: "8.17.1", "light-my-request": "6.6.0", "thread-stream": "3.1.0" } })],
    ["apps/edge-api/dist/server.js", "export const builtEdge = true;\n"],
    ["apps/edge-api/dist/admin/cli.js", "process.stdout.write('sms-admin fixture\\n');\n"],
    ["apps/console/dist/index.html", "<!doctype html><title>SMS</title>\n"],
    ["apps/console/dist/assets/index.js", "document.title='SMS';\n"],
    ["packages/evidence/package.json", JSON.stringify({ name: "@fac-isr/evidence", version: "0.2.0-rc.1" })],
    ["packages/evidence/dist/index.js", "export {};\n"],
    ["packages/safety-kernel/package.json", JSON.stringify({ name: "@fac-isr/safety-kernel", version: "0.2.0-rc.1" })],
    ["packages/safety-kernel/dist/index.js", "export {};\n"],
    ["packages/telemetry/package.json", JSON.stringify({ name: "@fac-isr/telemetry", version: "0.2.0-rc.1" })],
    ["packages/telemetry/dist/index.js", "export {};\n"],
    ["node_modules/fastify/package.json", JSON.stringify({ name: "fastify", version: "5.6.1", license: "MIT", dependencies: { "fast-content-type-parse": "2.0.0" } })],
    ["node_modules/fastify/index.js", "export {};\n"],
    ["node_modules/fast-content-type-parse/package.json", JSON.stringify({ name: "fast-content-type-parse", version: "2.0.0", license: "MIT" })],
    ["node_modules/fast-content-type-parse/index.js", "export {};\n"],
    ["node_modules/ajv/package.json", JSON.stringify({ name: "ajv", version: "8.17.1", type: "module", main: "index.js", license: "MIT", dependencies: { "fast-uri": "3.0.6" } })],
    ["node_modules/ajv/index.js", "import nested from 'fast-uri'; export default nested;\n"],
    ["node_modules/ajv/node_modules/fast-uri/package.json", JSON.stringify({ name: "fast-uri", version: "3.0.6", type: "module", main: "index.js", license: "BSD-3-Clause" })],
    ["node_modules/ajv/node_modules/fast-uri/index.js", "export default 'fast-uri@3.0.6';\n"],
    ["node_modules/light-my-request/package.json", JSON.stringify({ name: "light-my-request", version: "6.6.0", type: "module", main: "index.js", dependencies: { "process-warning": "5.0.0" } })],
    ["node_modules/light-my-request/index.js", "import nested from 'process-warning'; export default nested;\n"],
    ["node_modules/light-my-request/node_modules/process-warning/package.json", JSON.stringify({ name: "process-warning", version: "5.0.0", type: "module", main: "index.js", license: "MIT" })],
    ["node_modules/light-my-request/node_modules/process-warning/index.js", "export default 'process-warning@5.0.0';\n"],
    ["node_modules/thread-stream/package.json", JSON.stringify({ name: "thread-stream", version: "3.1.0", type: "module", main: "index.js", dependencies: { "real-require": "0.2.0" } })],
    ["node_modules/thread-stream/index.js", "import nested from 'real-require'; export default nested;\n"],
    ["node_modules/thread-stream/node_modules/real-require/package.json", JSON.stringify({ name: "real-require", version: "0.2.0", type: "module", main: "index.js", license: "MIT" })],
    ["node_modules/thread-stream/node_modules/real-require/index.js", "export default 'real-require@0.2.0';\n"],
    ["scripts/start-edge.mjs", "import { writeFileSync } from 'node:fs'; import ajvNested from 'ajv'; import requestNested from 'light-my-request'; import threadNested from 'thread-stream';\nif (process.env.SMS_COLD_START_MARKER) writeFileSync(process.env.SMS_COLD_START_MARKER, `offline cold start ${ajvNested} ${requestNested} ${threadNested}\\n`);\nprocess.stdout.write('offline cold start\\n');\n"],
    ["scripts/edge-healthcheck.mjs", "process.stdout.write('ok\\n');\n"],
  ]);
  for (const [relativePath, body] of files) {
    const path = resolve(root, relativePath);
    await mkdir(resolve(path, ".."), { recursive: true });
    await writeFile(path, body.endsWith("\n") ? body : `${body}\n`);
  }
}

async function createRuntimeFixture(root: string, target: "linux-x64" | "win32-x64") {
  const platformName = target === "linux-x64" ? "linux-x64.tar.xz" : "win-x64.zip";
  const archiveName = `node-v22.23.2-${platformName}`;
  const runtimeRoot = resolve(root, `node-v22.23.2-${target === "linux-x64" ? "linux-x64" : "win-x64"}`);
  await mkdir(target === "linux-x64" ? resolve(runtimeRoot, "bin") : runtimeRoot, { recursive: true });
  const executable = target === "linux-x64" ? resolve(runtimeRoot, "bin/node") : resolve(runtimeRoot, "node.exe");
  await writeFile(executable, target === "linux-x64"
    ? "#!/bin/sh\nexec /usr/bin/node \"$@\"\n"
    : "controlled fake Node 22.23.2 runtime\n");
  await chmod(executable, 0o755);
  const archive = resolve(root, archiveName);
  if (target === "linux-x64") {
    await exec("tar", ["-cJf", archive, "-C", root, basename(runtimeRoot)]);
  } else {
    await writeDeterministicZip(archive, [{ archivePath: `${basename(runtimeRoot)}/node.exe`, sourcePath: executable, mode: 0o755 }], 1_700_000_000);
  }
  const checksum = await sha256(archive);
  const checksums = resolve(root, "SHASUMS256.txt");
  await writeFile(checksums, `${checksum}  ${archiveName}\n`);
  return { archive, checksums };
}

async function runBuilder(target: "linux-x64" | "win32-x64", root: string, output: string) {
  const appRoot = resolve(root, "app");
  await createAppFixture(appRoot);
  const runtime = await createRuntimeFixture(root, target);
  return exec(process.execPath, [
    builder,
    "--target", target,
    "--runtime-archive", runtime.archive,
    "--runtime-checksums", runtime.checksums,
    "--output-dir", output,
    "--app-root", appRoot,
    "--test-runtime",
    "--source-date-epoch", "1700000000",
  ], { cwd: smsRoot, env: { ...process.env, TZ: "UTC" } });
}

async function extractArtifact(artifact: string, destination: string): Promise<void> {
  await mkdir(destination, { recursive: true });
  if (artifact.endsWith(".zip")) await exec("unzip", ["-q", artifact, "-d", destination]);
  else await exec("tar", ["-xzf", artifact, "-C", destination]);
}

async function makeTreeWritable(directory: string): Promise<void> {
  try {
    await chmod(directory, 0o700);
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const full = resolve(directory, entry.name);
      if (entry.isDirectory()) await makeTreeWritable(full);
      else if (!entry.isSymbolicLink()) await chmod(full, 0o600);
    }
  } catch (error) {
    if (!(error instanceof Error && "code" in error && error.code === "ENOENT")) throw error;
  }
}

afterEach(async () => {
  if (process.env.SMS_KEEP_PLATFORM_FIXTURES === "1") return;
  await Promise.all(temporaryDirectories.splice(0).map(async (directory) => {
    await makeTreeWritable(directory);
    await rm(directory, { recursive: true, force: true });
  }));
});

describe("native release bundle builder", () => {
  test("requires signed official Node checksum metadata outside controlled fixture mode", async () => {
    const root = await temporaryDirectory();
    const target = isWindows ? "win32-x64" : "linux-x64";
    const runtime = await createRuntimeFixture(root, target);
    await expect(exec(process.execPath, [
      builder,
      "--target", target,
      "--runtime-archive", runtime.archive,
      "--runtime-checksums", runtime.checksums,
      "--output-dir", resolve(root, "out"),
      "--source-date-epoch", "1700000000",
    ], { cwd: smsRoot })).rejects.toBeDefined();
  });

  test("rejects arbitrary valid signatures and accepts only pinned official Node signer status", () => {
    expect(isOfficialNodeSignatureStatus("[GNUPG:] VALIDSIG AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA 2026-01-01 0 4 0 22 8 00 AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n")).toBe(false);
    expect(isOfficialNodeSignatureStatus("[GNUPG:] VALIDSIG BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB 2026-01-01 0 4 0 22 8 00 5BE8A3F6C8A5C01D106C0AD820B1A390B168D356\n")).toBe(true);
  });

  test("rejects runtime bytes not covered by the supplied Node checksum metadata", async () => {
    const root = await temporaryDirectory();
    const appRoot = resolve(root, "app");
    await createAppFixture(appRoot);
    const target = isWindows ? "win32-x64" : "linux-x64";
    const runtime = await createRuntimeFixture(root, target);
    await writeFile(runtime.checksums, `${"0".repeat(64)}  ${basename(runtime.archive)}\n`);

    await expect(exec(process.execPath, [
      builder,
      "--target", target,
      "--runtime-archive", runtime.archive,
      "--runtime-checksums", runtime.checksums,
      "--output-dir", resolve(root, "out"),
      "--app-root", appRoot,
      "--test-runtime",
    ], { cwd: smsRoot })).rejects.toThrow(/checksum/i);
  });

  test.each([
    ["win32-x64", "TEST-ONLY-fac-isr-sms-0.2.0-rc.1-win32-x64.zip"],
    ...(!isWindows ? [["linux-x64", "TEST-ONLY-fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz"] as const] : []),
  ] as const)("builds and verifies the exact deterministic %s artifact", async (target, artifactName) => {
    const firstRoot = await temporaryDirectory();
    const secondRoot = await temporaryDirectory();
    const firstOutput = resolve(firstRoot, "out");
    const secondOutput = resolve(secondRoot, "out");
    await runBuilder(target, firstRoot, firstOutput);
    await runBuilder(target, secondRoot, secondOutput);
    const firstArtifact = resolve(firstOutput, artifactName);
    const secondArtifact = resolve(secondOutput, artifactName);

    expect(await sha256(firstArtifact)).toBe(await sha256(secondArtifact));
    expect((await readdir(firstOutput)).sort()).toEqual([artifactName]);

    const extracted = resolve(firstRoot, "extracted");
    await extractArtifact(firstArtifact, extracted);
    const bundleRoot = resolve(extracted, "fac-isr-sms");
    const verification = await verifyPlatformInventory(bundleRoot);
    expect(verification).toMatchObject({ valid: true, trustedManifestValid: true, unexpected: [], missing: [], mismatched: [] });
    await expect(stat(resolve(bundleRoot, target === "linux-x64" ? "runtime/bin/node" : "runtime/node.exe"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "app/apps/console/dist/index.html"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "app/apps/edge-api/dist/admin/cli.js"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "notices/THIRD_PARTY_NOTICES.md"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "sbom/runtime-fragment.cdx.json"))).resolves.toBeDefined();
    const sbom = JSON.parse(await readFile(resolve(bundleRoot, "sbom/runtime-fragment.cdx.json"), "utf8"));
    expect(sbom.components.map((component: { name: string; version: string }) => `${component.name}@${component.version}`)).toEqual(expect.arrayContaining([
      "node@22.23.2", "fastify@5.6.1", "fast-content-type-parse@2.0.0", "ajv@8.17.1", "fast-uri@3.0.6",
      "light-my-request@6.6.0", "process-warning@5.0.0", "thread-stream@3.1.0", "real-require@0.2.0",
    ]));
    await expect(stat(resolve(bundleRoot, "app/node_modules/ajv/node_modules/fast-uri/index.js"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "app/node_modules/light-my-request/node_modules/process-warning/index.js"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "app/node_modules/thread-stream/node_modules/real-require/index.js"))).resolves.toBeDefined();
    expect(JSON.parse(await readFile(resolve(bundleRoot, "release.json"), "utf8"))).toMatchObject({ production: false, runtimeProvenance: "controlled-test-fixture" });
    await expect(stat(resolve(bundleRoot, "config/sms.env.template"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, target === "linux-x64" ? "install/linux/smsctl" : "install/windows/SmsCtl.ps1"))).resolves.toBeDefined();
  });

  test.skipIf(isWindows)("cold-starts the Linux bundle with the network removed from the child environment", async () => {
    const root = await temporaryDirectory();
    const output = resolve(root, "out");
    await runBuilder("linux-x64", root, output);
    const extracted = resolve(root, "extracted");
    await extractArtifact(resolve(output, "TEST-ONLY-fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz"), extracted);
    const bundleRoot = resolve(extracted, "fac-isr-sms");
    const marker = resolve(root, "cold-start.marker");
    await exec(resolve(bundleRoot, "runtime/bin/node"), [resolve(bundleRoot, "app/scripts/start-edge.mjs")], {
      cwd: bundleRoot,
      env: { PATH: "/nonexistent", HOME: resolve(root, "empty-home"), SMS_NETWORK: "disabled", SMS_COLD_START_MARKER: marker },
    });
    expect(await readFile(marker, "utf8")).toBe("offline cold start fast-uri@3.0.6 process-warning@5.0.0 real-require@0.2.0\n");
  });

  test("rejects malformed dependency names", () => {
    expect(() => validateProductionDependencyName("../outside")).toThrow(/dependency name/i);
  });

  test.skipIf(isWindows)("rejects dependency paths that resolve outside the application root", async () => {
    const root = await temporaryDirectory();
    const appRoot = resolve(root, "app");
    await createAppFixture(appRoot);
    const externalModules = resolve(root, "external-node-modules");
    await mkdir(resolve(externalModules, "fast-uri"), { recursive: true });
    await writeFile(resolve(externalModules, "fast-uri/package.json"), JSON.stringify({ name: "fast-uri", version: "3.0.6" }));
    await rm(resolve(appRoot, "node_modules/ajv/node_modules"), { recursive: true, force: true });
    await symlink(externalModules, resolve(appRoot, "node_modules/ajv/node_modules"), "dir");

    await expect(copyRequiredApp(appRoot, resolve(root, "bundle-app"))).rejects.toThrow(/unsafe|outside|symbolic/i);
  });
});

describe("installed-process readiness", () => {
  test("fails when no installed HTTPS listener is reachable", async () => {
    await expect(exec(process.execPath, [healthcheck, "--ready"], {
      cwd: smsRoot,
      env: { ...process.env, SMS_PORT: "1" },
    })).rejects.toBeDefined();
  });

  test("constructs a verified configurable TLS and mTLS request", async () => {
    const root = await temporaryDirectory();
    const ca = resolve(root, "ca.crt");
    const certificate = resolve(root, "client.crt");
    const key = resolve(root, "client.key");
    await writeFile(ca, "trusted ca"); await writeFile(certificate, "client certificate"); await writeFile(key, "client key");
    const options = await buildInstalledRequestOptions("ready", {
      SMS_HEALTH_HOST: "edge.internal", SMS_HEALTH_SERVERNAME: "sms.example.invalid", SMS_PORT: "9443", SMS_HEALTH_CA_PATH: ca,
      SMS_HEALTH_CLIENT_CERT_PATH: certificate, SMS_HEALTH_CLIENT_KEY_PATH: key,
    });
    expect(options).toMatchObject({ hostname: "edge.internal", servername: "sms.example.invalid", port: 9443, path: "/readyz", rejectUnauthorized: true });
    expect(options.ca).toEqual(Buffer.from("trusted ca"));
    expect(options.cert).toEqual(Buffer.from("client certificate"));
    expect(options.key).toEqual(Buffer.from("client key"));
  });

  test.runIf(process.env.SMS_RUN_LOOPBACK_TLS === "1")("rejects an untrusted server and accepts trusted mutual TLS readiness", async () => {
    const root = await temporaryDirectory();
    const caKey = resolve(root, "ca.key"); const ca = resolve(root, "ca.crt");
    const serverKey = resolve(root, "server.key"); const serverCsr = resolve(root, "server.csr"); const serverCertificate = resolve(root, "server.crt");
    const clientKey = resolve(root, "client.key"); const clientCsr = resolve(root, "client.csr"); const clientCertificate = resolve(root, "client.crt");
    const untrustedKey = resolve(root, "untrusted.key"); const untrustedCa = resolve(root, "untrusted.crt");
    const serverExtensions = resolve(root, "server.ext"); const clientExtensions = resolve(root, "client.ext");
    await writeFile(serverExtensions, "subjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth\n");
    await writeFile(clientExtensions, "extendedKeyUsage=clientAuth\n");
    await exec("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=SMS Test CA", "-keyout", caKey, "-out", ca, "-days", "1"]);
    await exec("openssl", ["req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=localhost", "-keyout", serverKey, "-out", serverCsr]);
    await exec("openssl", ["x509", "-req", "-in", serverCsr, "-CA", ca, "-CAkey", caKey, "-CAcreateserial", "-out", serverCertificate, "-days", "1", "-extfile", serverExtensions]);
    await exec("openssl", ["req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=health-client", "-keyout", clientKey, "-out", clientCsr]);
    await exec("openssl", ["x509", "-req", "-in", clientCsr, "-CA", ca, "-CAkey", caKey, "-CAcreateserial", "-out", clientCertificate, "-days", "1", "-extfile", clientExtensions]);
    await exec("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=Untrusted CA", "-keyout", untrustedKey, "-out", untrustedCa, "-days", "1"]);
    const server = createServer({ key: await readFile(serverKey), cert: await readFile(serverCertificate), ca: await readFile(ca), requestCert: true, rejectUnauthorized: true }, (_request, response) => {
      response.writeHead(200, { "content-type": "application/json" });
      response.end('{"technicalReady":true}');
    });
    await new Promise<void>((accept, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", accept); });
    try {
      const address = server.address();
      if (address === null || typeof address === "string") throw new Error("HTTPS fixture did not expose a TCP port");
      const environment = { ...process.env, SMS_HEALTH_HOST: "127.0.0.1", SMS_HEALTH_SERVERNAME: "localhost", SMS_PORT: String(address.port), SMS_HEALTH_CLIENT_CERT_PATH: clientCertificate, SMS_HEALTH_CLIENT_KEY_PATH: clientKey };
      await expect(exec(process.execPath, [healthcheck, "--ready"], { cwd: smsRoot, env: { ...environment, SMS_HEALTH_CA_PATH: untrustedCa } })).rejects.toBeDefined();
      await expect(exec(process.execPath, [healthcheck, "--ready"], { cwd: smsRoot, env: { ...environment, SMS_HEALTH_CA_PATH: ca } })).resolves.toMatchObject({ stdout: expect.stringContaining("PASS installed edge ready check") });
    } finally {
      await new Promise<void>((accept, reject) => server.close((error) => error ? reject(error) : accept()));
    }
  });

});

async function lifecycleFiles(root: string, current = root): Promise<string[]> {
  const paths: string[] = [];
  for (const entry of await readdir(current, { withFileTypes: true })) {
    const full = resolve(current, entry.name);
    if (entry.isDirectory()) paths.push(...await lifecycleFiles(root, full));
    else if (entry.isFile() && entry.name !== "inventory.json" && entry.name !== "inventory.tsv") paths.push(full.slice(root.length + 1).replaceAll("\\", "/"));
  }
  return paths.sort();
}

async function refreshLifecycleInventory(bundle: string): Promise<void> {
  const inventory = [];
  for (const path of await lifecycleFiles(bundle)) {
    const info = await stat(resolve(bundle, path));
    inventory.push({ path, sha256: await sha256(resolve(bundle, path)), sizeBytes: info.size, mode: info.mode & 0o777 });
  }
  await writeFile(resolve(bundle, "inventory.json"), `${JSON.stringify({ schemaVersion: "1.0", inventoryPath: "inventory.json", files: inventory }, null, 2)}\n`);
  const jsonInfo = await stat(resolve(bundle, "inventory.json"));
  inventory.push({ path: "inventory.json", sha256: await sha256(resolve(bundle, "inventory.json")), sizeBytes: jsonInfo.size, mode: jsonInfo.mode & 0o777 });
  await writeFile(resolve(bundle, "inventory.tsv"), `${inventory.map((file) => `${file.path}\t${file.sha256}\t${file.sizeBytes}\t${file.mode.toString(8).padStart(3, "0")}`).join("\n")}\n`);
}

async function createLifecycleBundle(root: string, buildId: string, migration = "success", startup = "success"): Promise<string> {
  const bundle = resolve(root, `bundle-${buildId}`);
  const files = new Map<string, string>([
    ["release.json", `${JSON.stringify({ release: "fac-isr-sms@0.2.0-rc.1", target: "linux-x64", nodeVersion: "22.23.2", internet: "disabled", operationalReady: false, production: true, runtimeProvenance: "official-node-signed-checksums" }, null, 2)}\n`],
    ["runtime/bin/node", "#!/bin/sh\nexec /usr/bin/node \"$@\"\n"],
    ["app/scripts/start-edge.mjs", startup === "success" ? "import { writeFileSync } from 'node:fs'; if (process.env.SMS_TEST_ENV_MARKER) writeFileSync(process.env.SMS_TEST_ENV_MARKER, process.env.SMS_EXPORT_KEY_ID ?? 'missing'); process.stdout.write('listening\\n');\n" : "process.exit(74);\n"],
    ["app/apps/edge-api/dist/admin/cli.js", "process.stdout.write('admin\\n');\n"],
    ["app/apps/console/dist/index.html", "<!doctype html><title>SMS</title>\n"],
    ["config/sms.env.template", "SMS_DEPLOYMENT_MODE=standalone\nSMS_NETWORK=disabled\n"],
    ["install/linux/migrate", migration === "success"
      ? "#!/bin/sh\nset -eu\nprintf '%s\\n' \"${SMS_RELEASE_BUILD_ID:?}\" > \"${SMS_DATA_DIRECTORY:?}/migration.marker\"\n"
      : "#!/bin/sh\nexit 72\n"],
  ]);
  for (const [relativePath, body] of files) {
    const path = resolve(bundle, relativePath);
    await mkdir(resolve(path, ".."), { recursive: true });
    await writeFile(path, body);
  }
  for (const path of await lifecycleFiles(bundle)) await chmod(resolve(bundle, path), path === "runtime/bin/node" || path === "install/linux/migrate" ? 0o555 : path === "config/sms.env.template" ? 0o640 : 0o444);
  await refreshLifecycleInventory(bundle);
  return bundle;
}

async function runLinux(root: string, ...arguments_: string[]) {
  return exec(linuxInstaller, [...arguments_, "--root", root, "--test-mode"], { cwd: smsRoot, env: { ...process.env, TZ: "UTC" } });
}

async function runLinuxWithEnvironment(root: string, environment: NodeJS.ProcessEnv, ...arguments_: string[]) {
  return exec(linuxInstaller, [...arguments_, "--root", root, "--test-mode"], { cwd: smsRoot, env: { ...process.env, ...environment, TZ: "UTC" } });
}

async function provisionTls(root: string, mode = 0o600): Promise<void> {
  const directory = resolve(root, "etc/fac-isr-sms/tls");
  await mkdir(directory, { recursive: true });
  await writeFile(resolve(directory, "server.crt"), "controlled certificate\n");
  await writeFile(resolve(directory, "server.key"), "controlled private key\n");
  await writeFile(resolve(directory, "export.key"), "controlled export key\n");
  await chmod(resolve(directory, "server.crt"), 0o644);
  await chmod(resolve(directory, "server.key"), mode);
  await chmod(resolve(directory, "export.key"), 0o600);
}

describe.skipIf(isWindows)("Linux native lifecycle", () => {
  test("rejects controlled runtime provenance even when the extracted directory is renamed", async () => {
    const fixtureRoot = await temporaryDirectory();
    const output = resolve(fixtureRoot, "out");
    await runBuilder("linux-x64", fixtureRoot, output);
    const extracted = resolve(fixtureRoot, "renamed-production-looking-input");
    await extractArtifact(resolve(output, "TEST-ONLY-fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz"), extracted);
    const installRoot = await temporaryDirectory();
    await expect(runLinux(installRoot, "install", "--bundle", resolve(extracted, "fac-isr-sms"))).rejects.toBeDefined();
    await expect(stat(resolve(installRoot, "opt/fac-isr-sms/current"))).rejects.toMatchObject({ code: "ENOENT" });
  });

  test("rejects nonportable inventory paths and duplicate manifest records", async () => {
    const root = await temporaryDirectory();
    const nonportable = await createLifecycleBundle(root, "build-a");
    await writeFile(resolve(nonportable, "app/ambiguous:name"), "unsafe\n");
    await refreshLifecycleInventory(nonportable);
    await expect(runLinux(root, "install", "--bundle", nonportable)).rejects.toBeDefined();

    const secondRoot = await temporaryDirectory();
    const duplicate = await createLifecycleBundle(secondRoot, "build-b");
    const manifest = await readFile(resolve(duplicate, "inventory.tsv"), "utf8");
    await writeFile(resolve(duplicate, "inventory.tsv"), `${manifest}${manifest.split("\n")[0]}\n`);
    await expect(runLinux(secondRoot, "install", "--bundle", duplicate)).rejects.toBeDefined();
  });

  test("verifies source and staged bytes with trusted host tools without executing bundle contents", async () => {
    const root = await temporaryDirectory();
    const bundle = await createLifecycleBundle(root, "build-a");
    const executionMarker = resolve(root, "untrusted-runtime-executed");
    await chmod(resolve(bundle, "runtime/bin/node"), 0o755);
    await writeFile(resolve(bundle, "runtime/bin/node"), `#!/bin/sh\nprintf executed > ${executionMarker}\nexit 90\n`);
    await chmod(resolve(bundle, "runtime/bin/node"), 0o555);
    await refreshLifecycleInventory(bundle);
    await runLinux(root, "install", "--bundle", bundle);
    await expect(stat(executionMarker)).rejects.toMatchObject({ code: "ENOENT" });

    const secondRoot = await temporaryDirectory();
    await expect(runLinuxWithEnvironment(secondRoot, { SMS_TEST_TAMPER_STAGE: "1" }, "install", "--bundle", await createLifecycleBundle(secondRoot, "build-b"))).rejects.toBeDefined();
    await expect(stat(resolve(secondRoot, "opt/fac-isr-sms/current"))).rejects.toMatchObject({ code: "ENOENT" });
  });

  test("installs configuration only from the verified immutable staged release", async () => {
    const root = await temporaryDirectory();
    const bundle = await createLifecycleBundle(root, "build-a");
    const expected = await readFile(resolve(bundle, "config/sms.env.template"), "utf8");
    await runLinuxWithEnvironment(root, { SMS_TEST_MUTATE_SOURCE_AFTER_STAGE: "1" }, "install", "--bundle", bundle);
    expect(await readFile(resolve(bundle, "config/sms.env.template"), "utf8")).toContain("SMS_SOURCE_MUTATED=1");
    expect(await readFile(resolve(root, "etc/fac-isr-sms/sms.env"), "utf8")).toBe(expected);
  });

  test("rejects config-directory traversal and provisions service-owned private paths", async () => {
    const root = await temporaryDirectory();
    const external = resolve(root, "external-config");
    await mkdir(resolve(root, "etc"), { recursive: true });
    await mkdir(external, { mode: 0o755 });
    await symlink(external, resolve(root, "etc/fac-isr-sms"));
    await expect(runLinux(root, "install", "--bundle", await createLifecycleBundle(root, "build-a"))).rejects.toThrow(/symbolic|unsafe/i);
    expect((await stat(external)).mode & 0o777).toBe(0o755);

    const cleanRoot = await temporaryDirectory();
    await runLinux(cleanRoot, "install", "--bundle", await createLifecycleBundle(cleanRoot, "build-b"));
    expect((await stat(resolve(cleanRoot, "etc/fac-isr-sms"))).mode & 0o777).toBe(0o750);
  });

  test("installs immutable application files, private mutable paths, and a dedicated service identity", async () => {
    const root = await temporaryDirectory();
    const bundle = await createLifecycleBundle(root, "build-a");
    await runLinux(root, "install", "--bundle", bundle);

    const releaseLink = await readlink(resolve(root, "opt/fac-isr-sms/current"));
    const installed = resolve(root, "opt/fac-isr-sms", releaseLink);
    expect((await stat(resolve(installed, "app/scripts/start-edge.mjs"))).mode & 0o222).toBe(0);
    expect((await stat(resolve(root, "etc/fac-isr-sms/sms.env"))).mode & 0o777).toBe(0o640);
    expect((await stat(resolve(root, "var/lib/fac-isr-sms"))).mode & 0o777).toBe(0o700);
    expect(await readFile(resolve(root, "etc/fac-isr-sms/service-account"), "utf8")).toBe("fac-isr-sms:10001:10001\n");
    const unit = await readFile(resolve(root, "etc/systemd/system/fac-isr-sms.service"), "utf8");
    expect(unit).toContain("NoNewPrivileges=true");
    expect(unit).toContain("ProtectSystem=strict");
    expect(unit).toContain("ReadWritePaths=/var/lib/fac-isr-sms");
  });

  test("rejects an exposed TLS key, then starts, reports readiness, and recovers on restart", async () => {
    const root = await temporaryDirectory();
    await runLinux(root, "install", "--bundle", await createLifecycleBundle(root, "build-a"));
    await provisionTls(root, 0o644);
    await expect(runLinux(root, "start")).rejects.toThrow(/TLS private key permissions/i);
    await chmod(resolve(root, "etc/fac-isr-sms/tls/server.key"), 0o600);
    const environmentMarker = resolve(root, "loaded-environment");
    const executionMarker = resolve(root, "configuration-code-executed");
    await writeFile(resolve(root, "etc/fac-isr-sms/sms.env"), `SMS_EXPORT_KEY_ID=$(touch ${executionMarker})\n`);
    await runLinuxWithEnvironment(root, { SMS_TEST_ENV_MARKER: environmentMarker }, "start");
    expect(await readFile(environmentMarker, "utf8")).toBe(`$(touch ${executionMarker})`);
    await expect(stat(executionMarker)).rejects.toMatchObject({ code: "ENOENT" });
    expect((await runLinux(root, "status")).stdout).toContain("running ready");
    await writeFile(resolve(root, "run/fac-isr-sms/service.state"), "failed\n");
    await runLinux(root, "restart");
    expect((await runLinux(root, "status")).stdout).toContain("running ready");
  });

  test("backs up and restores data, upgrades only after migration, and rolls back a failed upgrade", async () => {
    const root = await temporaryDirectory();
    const first = await createLifecycleBundle(root, "build-a");
    await runLinux(root, "install", "--bundle", first);
    await provisionTls(root);
    const database = resolve(root, "var/lib/fac-isr-sms/data/edge.sqlite");
    await mkdir(resolve(database, ".."), { recursive: true });
    await writeFile(database, "original database bytes\n");
    await provisionTls(root);
    await runLinux(root, "start");
    const backup = (await runLinux(root, "backup")).stdout.trim();
    const backupListing = (await exec("tar", ["-tzf", backup])).stdout;
    expect(backupListing).toContain("data/.service-stopped-for-test");
    expect((await runLinux(root, "status")).stdout).toContain("running ready");
    await writeFile(database, "damaged bytes\n");
    await runLinux(root, "restore", "--backup", backup);
    expect(await readFile(database, "utf8")).toBe("original database bytes\n");
    expect((await runLinux(root, "status")).stdout).toContain("running ready");

    const second = await createLifecycleBundle(root, "build-b");
    await runLinux(root, "start");
    await runLinux(root, "upgrade", "--bundle", second);
    expect(await readFile(resolve(root, "var/lib/fac-isr-sms/migration.marker"), "utf8")).toMatch(/^[a-f0-9]{16}\n$/u);
    expect((await runLinux(root, "status")).stdout).toContain("running ready");

    const failedStart = await createLifecycleBundle(root, "build-d", "success", "fail");
    const pointerBeforeFailedStart = await readlink(resolve(root, "opt/fac-isr-sms/current"));
    await expect(runLinux(root, "upgrade", "--bundle", failedStart)).rejects.toBeDefined();
    expect(await readlink(resolve(root, "opt/fac-isr-sms/current"))).toBe(pointerBeforeFailedStart);
    expect(await readFile(database, "utf8")).toBe("original database bytes\n");
    expect((await runLinux(root, "status")).stdout).toContain("running ready");
    const upgradedLink = await readlink(resolve(root, "opt/fac-isr-sms/current"));

    const failing = await createLifecycleBundle(root, "build-c", "fail");
    await expect(runLinux(root, "upgrade", "--bundle", failing)).rejects.toThrow(/migration/i);
    expect(await readlink(resolve(root, "opt/fac-isr-sms/current"))).toBe(upgradedLink);
    expect(await readFile(database, "utf8")).toBe("original database bytes\n");
    expect((await runLinux(root, "status")).stdout).toContain("running ready");
  });

  test("restores exact pre-restore paths and running state after a partial replacement failure", async () => {
    const root = await temporaryDirectory();
    await runLinux(root, "install", "--bundle", await createLifecycleBundle(root, "build-a"));
    await provisionTls(root);
    const database = resolve(root, "var/lib/fac-isr-sms/data/edge.sqlite");
    const activePackage = resolve(root, "var/lib/fac-isr-sms/packages/active-policy.json");
    await writeFile(database, "backup database bytes\n");
    await writeFile(activePackage, "backup package bytes\n");
    await runLinux(root, "start");
    const backup = (await runLinux(root, "backup")).stdout.trim();
    await writeFile(database, "pre-failure database bytes\n");
    await writeFile(activePackage, "pre-failure package bytes\n");
    await expect(runLinuxWithEnvironment(root, { SMS_TEST_FAIL_RESTORE_AFTER_DATA_MOVE: "1" }, "restore", "--backup", backup)).rejects.toThrow(/restore/i);
    expect(await readFile(database, "utf8")).toBe("pre-failure database bytes\n");
    expect(await readFile(activePackage, "utf8")).toBe("pre-failure package bytes\n");
    await expect(stat(resolve(root, "var/lib/fac-isr-sms/data/data"))).rejects.toMatchObject({ code: "ENOENT" });
    expect((await runLinux(root, "status")).stdout).toContain("running ready");

    await writeFile(database, "pre-original-move database bytes\n");
    await writeFile(activePackage, "pre-original-move package bytes\n");
    await expect(runLinuxWithEnvironment(root, { SMS_TEST_FAIL_RESTORE_AFTER_OLD_DATA_MOVE: "1" }, "restore", "--backup", backup)).rejects.toThrow(/restore/i);
    expect(await readFile(database, "utf8")).toBe("pre-original-move database bytes\n");
    expect(await readFile(activePackage, "utf8")).toBe("pre-original-move package bytes\n");
    expect((await runLinux(root, "status")).stdout).toContain("running ready");
  });

  test("keeps the active immutable release on a failed same-artifact upgrade", async () => {
    const root = await temporaryDirectory();
    const bundle = await createLifecycleBundle(root, "build-a");
    await runLinux(root, "install", "--bundle", bundle);
    await provisionTls(root);
    await runLinux(root, "start");
    const pointer = await readlink(resolve(root, "opt/fac-isr-sms/current"));
    await expect(runLinuxWithEnvironment(root, { SMS_TEST_FAIL_MIGRATION_AFTER_STAGE: "1" }, "upgrade", "--bundle", bundle)).rejects.toThrow(/migration/i);
    expect(await readlink(resolve(root, "opt/fac-isr-sms/current"))).toBe(pointer);
    await expect(stat(resolve(root, "opt/fac-isr-sms", pointer, "release.json"))).resolves.toBeDefined();
    expect((await runLinux(root, "status")).stdout).toContain("running ready");
  });

  test("rejects link entries in restore archives without changing installed data", async () => {
    const root = await temporaryDirectory();
    await runLinux(root, "install", "--bundle", await createLifecycleBundle(root, "build-a"));
    const database = resolve(root, "var/lib/fac-isr-sms/data/edge.sqlite");
    await writeFile(database, "preserved bytes\n");
    await provisionTls(root);
    await runLinux(root, "start");
    const maliciousRoot = resolve(root, "malicious-backup");
    await mkdir(resolve(maliciousRoot, "data"), { recursive: true });
    await mkdir(resolve(maliciousRoot, "packages"), { recursive: true });
    await symlink("/etc/passwd", resolve(maliciousRoot, "data/edge.sqlite"));
    const archive = resolve(root, "malicious.tar.gz");
    await exec("tar", ["-czf", archive, "-C", maliciousRoot, "data", "packages"]);
    await expect(runLinux(root, "restore", "--backup", archive)).rejects.toThrow(/link|unsafe/i);
    expect(await readFile(database, "utf8")).toBe("preserved bytes\n");
    expect((await runLinux(root, "status")).stdout).toContain("running ready");

    await rm(maliciousRoot, { recursive: true, force: true });
    await mkdir(resolve(maliciousRoot, "data"), { recursive: true });
    await mkdir(resolve(maliciousRoot, "packages"), { recursive: true });
    await writeFile(resolve(maliciousRoot, "data/shared"), "hard-linked bytes\n");
    await link(resolve(maliciousRoot, "data/shared"), resolve(maliciousRoot, "data/edge.sqlite"));
    const hardlinkArchive = resolve(root, "malicious-hardlink.tar.gz");
    await exec("tar", ["-czf", hardlinkArchive, "-C", maliciousRoot, "data", "packages"]);
    await expect(runLinux(root, "restore", "--backup", hardlinkArchive)).rejects.toThrow(/link|unsafe/i);
    expect(await readFile(database, "utf8")).toBe("preserved bytes\n");
  });

  test("stops and uninstalls immutable/config state while preserving operational data by default", async () => {
    const root = await temporaryDirectory();
    await runLinux(root, "install", "--bundle", await createLifecycleBundle(root, "build-a"));
    await provisionTls(root);
    await mkdir(resolve(root, "var/lib/fac-isr-sms/data"), { recursive: true });
    await writeFile(resolve(root, "var/lib/fac-isr-sms/data/edge.sqlite"), "preserve me\n");
    await runLinux(root, "start");
    await runLinux(root, "stop");
    await runLinux(root, "uninstall");
    await expect(stat(resolve(root, "opt/fac-isr-sms"))).rejects.toMatchObject({ code: "ENOENT" });
    await expect(stat(resolve(root, "etc/fac-isr-sms"))).rejects.toMatchObject({ code: "ENOENT" });
    expect(await readFile(resolve(root, "var/lib/fac-isr-sms/data/edge.sqlite"), "utf8")).toBe("preserve me\n");
  });
});

describe.skipIf(isWindows)("OCI privileged init and permanent runtime boundary", () => {
  test("normalizes existing mounted data recursively and rejects symbolic entries", async () => {
    if (process.getuid?.() !== 0) return;
    const root = await temporaryDirectory();
    const data = resolve(root, "data");
    const tls = resolve(root, "tls");
    const packages = resolve(root, "packages");
    await mkdir(resolve(data, "nested"), { recursive: true, mode: 0o777 });
    await writeFile(resolve(data, "nested/state.sqlite"), "state\n", { mode: 0o666 });
    await mkdir(tls); await mkdir(packages, { mode: 0o555 });
    for (const [name, mode] of [["server.crt", 0o444], ["server.key", 0o400], ["export.key", 0o400]] as const) {
      await writeFile(resolve(tls, name), name); await chmod(resolve(tls, name), mode);
      try { await chown(resolve(tls, name), 10001, 10001); } catch (error) {
        if (error instanceof Error && "code" in error && error.code === "EINVAL") return;
        throw error;
      }
    }
    const environment = { ...process.env, SMS_DATA_DIRECTORY: data, SMS_PACKAGE_DIRECTORY: packages, SMS_TLS_CERT_PATH: resolve(tls, "server.crt"), SMS_TLS_KEY_PATH: resolve(tls, "server.key"), SMS_EXPORT_KEY_PATH: resolve(tls, "export.key") };
    await exec(ociPreflight, ["init"], { env: environment });
    expect(await stat(resolve(data, "nested"))).toMatchObject({ uid: 10001, gid: 10001 });
    expect((await stat(resolve(data, "nested"))).mode & 0o777).toBe(0o700);
    expect((await stat(resolve(data, "nested/state.sqlite"))).mode & 0o777).toBe(0o600);
    await symlink("/etc/passwd", resolve(data, "unsafe-link"));
    await expect(exec(ociPreflight, ["init"], { env: environment })).rejects.toBeDefined();
  });
  test("rejects unsafe TLS mode and ownership before changing mounted state", async () => {
    const root = await temporaryDirectory();
    const data = resolve(root, "data");
    const tls = resolve(root, "tls");
    const packages = resolve(root, "packages");
    await mkdir(data);
    await mkdir(tls);
    await mkdir(packages);
    await writeFile(resolve(tls, "server.crt"), "controlled certificate\n");
    await writeFile(resolve(tls, "server.key"), "controlled key\n");
    await writeFile(resolve(tls, "export.key"), "controlled export key\n");
    await chmod(resolve(tls, "export.key"), 0o400);
    await chmod(resolve(tls, "server.key"), 0o644);
    const environment = { ...process.env, SMS_DATA_DIRECTORY: data, SMS_PACKAGE_DIRECTORY: packages, SMS_TLS_CERT_PATH: resolve(tls, "server.crt"), SMS_TLS_KEY_PATH: resolve(tls, "server.key"), SMS_EXPORT_KEY_PATH: resolve(tls, "export.key") };
    await expect(exec(ociPreflight, ["init"], { env: environment })).rejects.toThrow(/TLS private key/i);

    await chmod(resolve(tls, "server.key"), 0o400);
    await expect(exec(ociPreflight, ["init"], { env: environment })).rejects.toThrow(/ownership.*10001:10001/i);
    expect((await stat(data)).uid).toBe(process.getuid?.());
  });

  test("refuses a root permanent process before it can start the service", async () => {
    const root = await temporaryDirectory();
    const data = resolve(root, "data");
    const tls = resolve(root, "tls");
    const packages = resolve(root, "packages");
    await mkdir(data, { mode: 0o700 });
    await mkdir(tls, { mode: 0o755 });
    await mkdir(packages, { mode: 0o555 });
    await writeFile(resolve(tls, "server.crt"), "controlled certificate\n");
    await writeFile(resolve(tls, "server.key"), "controlled key\n");
    await writeFile(resolve(tls, "export.key"), "controlled export key\n");
    await chmod(resolve(tls, "server.key"), 0o400);
    await chmod(resolve(tls, "export.key"), 0o400);
    const environment = { ...process.env, SMS_DATA_DIRECTORY: data, SMS_PACKAGE_DIRECTORY: packages, SMS_TLS_CERT_PATH: resolve(tls, "server.crt"), SMS_TLS_KEY_PATH: resolve(tls, "server.key"), SMS_EXPORT_KEY_PATH: resolve(tls, "export.key") };
    await expect(exec(ociPreflight, ["runtime", "/bin/true"], { env: environment })).rejects.toThrow(/UID 10001/i);
  });
});
