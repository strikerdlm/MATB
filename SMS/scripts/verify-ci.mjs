#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";
import { prepareVerifiedOciCandidate, removeVerifiedOciCandidate } from "./oci-candidate-runtime.mjs";
import { inspectCandidateArtifact } from "./verify-technical-release.mjs";

function parse(argv) {
  const options = { local: false };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--local") options.local = true;
    else if (["--platform", "--native-artifact", "--oci-artifact", "--oci-image", "--source-commit", "--attestation-output"].includes(argument)) {
      const value = argv[++index];
      if (!value || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      options[argument.slice(2).replaceAll(/-([a-z])/gu, (_, letter) => letter.toUpperCase())] = value;
    } else throw new Error(`unknown argument: ${argument}`);
  }
  if (!new Set(["linux", "windows"]).has(options.platform)) throw new Error("--platform must be linux or windows");
  if (!options.local && !/^[a-f0-9]{40}$/u.test(options.sourceCommit ?? "")) throw new Error("production CI requires exact --source-commit");
  if (!options.local && !options.nativeArtifact) throw new Error("production CI requires --native-artifact");
  if (!options.local && options.platform === "linux" && (!options.ociArtifact || !options.ociImage)) throw new Error("Linux production CI requires --oci-artifact and --oci-image");
  if (!options.local && options.platform === "linux" && options.ociImage !== `fac-isr-sms-edge:${options.sourceCommit}`) throw new Error("Linux production CI requires the source-commit-specific build image");
  return options;
}

function npmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

function run(command, args, options = {}) {
  return new Promise((resolvePromise, reject) => {
    process.stdout.write(`CI gate: ${command} ${args.join(" ")}\n`);
    const child = spawn(command, args, {
      cwd: process.cwd(),
      env: { ...process.env, NO_COLOR: "1", ...options.env },
      stdio: "inherit",
      windowsHide: true,
    });
    const timeoutMs = options.timeoutMs ?? 15 * 60 * 1000;
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 5_000).unref();
    }, timeoutMs);
    child.once("error", (error) => { clearTimeout(timer); reject(error); });
    child.once("close", (code, signal) => {
      clearTimeout(timer);
      if (code === 0) resolvePromise();
      else reject(new Error(`${command} failed (${signal ?? code})`));
    });
  });
}

async function main() {
  const options = parse(process.argv.slice(2));
  const npm = npmCommand();
  await run(process.execPath, ["scripts/clean-release-build.mjs"]);
  await run(npm, ["run", "build"]);
  await run(npm, ["run", "typecheck"]);
  await run(npm, ["run", "lint"]);
  await run(process.execPath, ["node_modules/vitest/vitest.mjs", "run"]);
  await run(npm, ["run", "test:e2e", "--workspace", "@fac-isr/console"], { timeoutMs: 10 * 60 * 1000 });
  await run(npm, ["run", "test:a11y", "--workspace", "@fac-isr/console"], { timeoutMs: 10 * 60 * 1000 });
  await run(npm, ["run", "verify:no-c2"]);
  await run(npm, ["run", "verify:data-separation"]);

  if (options.local) {
    if (options.platform !== "linux") throw new Error("--local is supported only for truthful Linux controller verification");
    await run(npm, ["run", "verify:platform"]);
    process.stdout.write("PASS verify:ci Linux-local (controlled platform fixtures; no production artifact claim)\n");
    return;
  }

  const nativeTarget = options.platform === "linux" ? "linux-x64" : "win32-x64";
  const nativeInspection = await inspectCandidateArtifact(options.nativeArtifact, nativeTarget, { expectedSourceCommit: options.sourceCommit });
  let ociInspection;
  if (options.platform === "linux") {
    await run(npm, ["run", "verify:linux-native"], {
      timeoutMs: 5 * 60 * 1000,
      env: { SMS_LINUX_BUNDLE_PATH: resolve(options.nativeArtifact) },
    });
    ociInspection = await inspectCandidateArtifact(options.ociArtifact, "linux-amd64-oci", { expectedSourceCommit: options.sourceCommit });
    const verifiedReference = await prepareVerifiedOciCandidate(options.ociImage, ociInspection);
    try {
      await run(npm, ["run", "verify:oci-native", "--", verifiedReference], { timeoutMs: 180_000 });
    } finally {
      await removeVerifiedOciCandidate(verifiedReference);
    }
  } else {
    await run(npm, ["run", "verify:windows-native"], {
      timeoutMs: 10 * 60 * 1000,
      env: { SMS_WINDOWS_BUNDLE_PATH: resolve(options.nativeArtifact) },
    });
  }

  if (!options.attestationOutput) throw new Error("production CI requires --attestation-output");
  const output = resolve(options.attestationOutput);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify({
    schemaVersion: "1.0",
    type: options.platform === "linux" ? "ubuntu-ci" : "windows-ci",
    sourceCommit: options.sourceCommit,
    generatedAtUtc: new Date().toISOString(),
    status: "pass",
    platform: options.platform === "linux" ? "ubuntu-24.04" : "windows-2022",
    clean: true,
    artifactSha256s: options.platform === "linux"
      ? { "linux-x64": nativeInspection.artifactSha256, "linux-amd64-oci": ociInspection.artifactSha256 }
      : { "win32-x64": nativeInspection.artifactSha256 },
  }, null, 2)}\n`);
  process.stdout.write(`PASS verify:ci ${options.platform} (exact production candidates)\n`);
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
