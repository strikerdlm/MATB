import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, readdir, readlink, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, test } from "vitest";
import { verifyPlatformInventory } from "../../scripts/verify-platform-inventory.mjs";

const exec = promisify(execFile);
const smsRoot = process.cwd();
const builder = resolve(smsRoot, "scripts/build-native-bundle.mjs");
const linuxInstaller = resolve(smsRoot, "packaging/linux/smsctl");
const ociPreflight = resolve(smsRoot, "docker/preflight.sh");
const temporaryDirectories: string[] = [];

async function temporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "sms-platform-bundle-"));
  temporaryDirectories.push(directory);
  return directory;
}

async function sha256(path: string): Promise<string> {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

async function createAppFixture(root: string): Promise<void> {
  const files = new Map<string, string>([
    ["package.json", JSON.stringify({ name: "fac-isr-sms", version: "0.2.0-rc.1" })],
    ["package-lock.json", JSON.stringify({ lockfileVersion: 3, packages: {} })],
    ["apps/edge-api/package.json", JSON.stringify({ name: "@fac-isr/edge-api", version: "0.2.0-rc.1" })],
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
    ["node_modules/fastify/package.json", JSON.stringify({ name: "fastify", version: "5.6.1", license: "MIT" })],
    ["node_modules/fastify/index.js", "export {};\n"],
    ["scripts/start-edge.mjs", "import { writeFileSync } from 'node:fs';\nif (process.env.SMS_COLD_START_MARKER) writeFileSync(process.env.SMS_COLD_START_MARKER, 'offline cold start\\n');\nprocess.stdout.write('offline cold start\\n');\n"],
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
    await exec("zip", ["-X", "-q", "-r", archive, basename(runtimeRoot)], { cwd: root });
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
    const runtime = await createRuntimeFixture(root, "linux-x64");
    await expect(exec(process.execPath, [
      builder,
      "--target", "linux-x64",
      "--runtime-archive", runtime.archive,
      "--runtime-checksums", runtime.checksums,
      "--output-dir", resolve(root, "out"),
      "--source-date-epoch", "1700000000",
    ], { cwd: smsRoot })).rejects.toBeDefined();
  });

  test("rejects runtime bytes not covered by the supplied Node checksum metadata", async () => {
    const root = await temporaryDirectory();
    const appRoot = resolve(root, "app");
    await createAppFixture(appRoot);
    const runtime = await createRuntimeFixture(root, "linux-x64");
    await writeFile(runtime.checksums, `${"0".repeat(64)}  ${basename(runtime.archive)}\n`);

    await expect(exec(process.execPath, [
      builder,
      "--target", "linux-x64",
      "--runtime-archive", runtime.archive,
      "--runtime-checksums", runtime.checksums,
      "--output-dir", resolve(root, "out"),
      "--app-root", appRoot,
      "--test-runtime",
    ], { cwd: smsRoot })).rejects.toThrow(/checksum/i);
  });

  test.each([
    ["linux-x64", "fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz"],
    ["win32-x64", "fac-isr-sms-0.2.0-rc.1-win32-x64.zip"],
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
    expect(verification).toMatchObject({ valid: true, unexpected: [], missing: [], mismatched: [] });
    await expect(stat(resolve(bundleRoot, target === "linux-x64" ? "runtime/bin/node" : "runtime/node.exe"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "app/apps/console/dist/index.html"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "app/apps/edge-api/dist/admin/cli.js"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "notices/THIRD_PARTY_NOTICES.md"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "sbom/runtime-fragment.cdx.json"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, "config/sms.env.template"))).resolves.toBeDefined();
    await expect(stat(resolve(bundleRoot, target === "linux-x64" ? "install/linux/smsctl" : "install/windows/SmsCtl.ps1"))).resolves.toBeDefined();
  });

  test("cold-starts the Linux bundle with the network removed from the child environment", async () => {
    const root = await temporaryDirectory();
    const output = resolve(root, "out");
    await runBuilder("linux-x64", root, output);
    const extracted = resolve(root, "extracted");
    await extractArtifact(resolve(output, "fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz"), extracted);
    const bundleRoot = resolve(extracted, "fac-isr-sms");
    const marker = resolve(root, "cold-start.marker");
    await exec(resolve(bundleRoot, "runtime/bin/node"), [resolve(bundleRoot, "app/scripts/start-edge.mjs")], {
      cwd: bundleRoot,
      env: { PATH: "/nonexistent", HOME: resolve(root, "empty-home"), SMS_NETWORK: "disabled", SMS_COLD_START_MARKER: marker },
    });
    expect(await readFile(marker, "utf8")).toBe("offline cold start\n");
  });
});

async function lifecycleFiles(root: string, current = root): Promise<string[]> {
  const paths: string[] = [];
  for (const entry of await readdir(current, { withFileTypes: true })) {
    const full = resolve(current, entry.name);
    if (entry.isDirectory()) paths.push(...await lifecycleFiles(root, full));
    else if (entry.isFile() && entry.name !== "inventory.json") paths.push(full.slice(root.length + 1).replaceAll("\\", "/"));
  }
  return paths.sort();
}

async function createLifecycleBundle(root: string, buildId: string, migration = "success"): Promise<string> {
  const bundle = resolve(root, `bundle-${buildId}`);
  const files = new Map<string, string>([
    ["release.json", `${JSON.stringify({ release: "fac-isr-sms@0.2.0-rc.1", target: "linux-x64", buildId, operationalReady: false })}\n`],
    ["runtime/bin/node", "#!/bin/sh\nexec /usr/bin/node \"$@\"\n"],
    ["app/scripts/start-edge.mjs", "process.stdout.write('listening\\n');\n"],
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
  const inventory = [];
  for (const path of await lifecycleFiles(bundle)) {
    const info = await stat(resolve(bundle, path));
    inventory.push({ path, sha256: await sha256(resolve(bundle, path)), sizeBytes: info.size, mode: info.mode & 0o777 });
  }
  await writeFile(resolve(bundle, "inventory.json"), `${JSON.stringify({ schemaVersion: "1.0", inventoryPath: "inventory.json", files: inventory }, null, 2)}\n`);
  return bundle;
}

async function runLinux(root: string, ...arguments_: string[]) {
  return exec(linuxInstaller, [...arguments_, "--root", root, "--test-mode"], { cwd: smsRoot, env: { ...process.env, TZ: "UTC" } });
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

describe("Linux native lifecycle", () => {
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
    await runLinux(root, "start");
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
    const backup = (await runLinux(root, "backup")).stdout.trim();
    await writeFile(database, "damaged bytes\n");
    await runLinux(root, "restore", "--backup", backup);
    expect(await readFile(database, "utf8")).toBe("original database bytes\n");

    const second = await createLifecycleBundle(root, "build-b");
    await runLinux(root, "upgrade", "--bundle", second);
    expect(await readFile(resolve(root, "var/lib/fac-isr-sms/migration.marker"), "utf8")).toBe("build-b\n");
    const upgradedLink = await readlink(resolve(root, "opt/fac-isr-sms/current"));

    const failing = await createLifecycleBundle(root, "build-c", "fail");
    await expect(runLinux(root, "upgrade", "--bundle", failing)).rejects.toThrow(/migration/i);
    expect(await readlink(resolve(root, "opt/fac-isr-sms/current"))).toBe(upgradedLink);
    expect(await readFile(database, "utf8")).toBe("original database bytes\n");
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

describe("OCI privileged init and permanent runtime boundary", () => {
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
