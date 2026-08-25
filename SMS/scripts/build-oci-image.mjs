#!/usr/bin/env node

import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { copyRequiredApp } from "./build-native-bundle.mjs";

const smsRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const PINNED_BASE = "node:22.23.2-bookworm-slim@sha256:a17d50af28002a160548bd4225b3cfcb12c5efcb171f79e68758f2885fb1b066";

function parse(argv) {
  const options = { timeoutSeconds: "300" };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (["--tag", "--source-commit", "--base-image-tar", "--timeout-seconds"].includes(argument)) {
      const value = argv[++index];
      if (!value || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      options[argument.slice(2).replaceAll(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = value;
    } else throw new Error(`unknown argument: ${argument}`);
  }
  if (!options.tag || !options.sourceCommit || !/^[a-f0-9]{40}$/u.test(options.sourceCommit)) throw new Error("--tag and a 40-character --source-commit are required");
  const timeoutMs = Number(options.timeoutSeconds) * 1000;
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1_000 || timeoutMs > 900_000) throw new Error("--timeout-seconds must be between 1 and 900");
  return { ...options, timeoutMs };
}

function run(command, args, { capture = false, cwd, timeoutMs = 60_000 } = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { cwd, env: { ...process.env, TZ: "UTC" }, stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit" });
    const stdout = [];
    const stderr = [];
    child.stdout?.on("data", (chunk) => stdout.push(chunk));
    child.stderr?.on("data", (chunk) => stderr.push(chunk));
    const timer = setTimeout(() => { child.kill("SIGTERM"); setTimeout(() => child.kill("SIGKILL"), 5_000).unref(); }, timeoutMs);
    child.once("error", (error) => { clearTimeout(timer); reject(error); });
    child.once("close", (code, signal) => {
      clearTimeout(timer);
      const result = { stdout: Buffer.concat(stdout).toString("utf8"), stderr: Buffer.concat(stderr).toString("utf8") };
      if (code === 0) resolvePromise(result);
      else reject(new Error(`${command} failed (${signal ?? code}): ${result.stderr.trim()}`));
    });
  });
}

async function assertBuildOutputs() {
  for (const path of ["apps/edge-api/dist/server.js", "apps/edge-api/dist/admin/cli.js", "apps/console/dist/index.html"]) {
    try { await readFile(resolve(smsRoot, path)); } catch { throw new Error(`required local build output is missing: ${path}`); }
  }
}

async function build(options) {
  if (options.baseImageTar) await run("docker", ["image", "load", "--input", resolve(options.baseImageTar)], { timeoutMs: options.timeoutMs });
  const inspected = JSON.parse((await run("docker", ["image", "inspect", PINNED_BASE], { capture: true })).stdout)[0];
  if (inspected?.Os !== "linux" || inspected?.Architecture !== "amd64") throw new Error("pinned Node 22.23.2 base image is not locally available as linux/amd64");
  await assertBuildOutputs();
  const context = await mkdtemp(resolve(tmpdir(), "sms-oci-context-"));
  try {
    await mkdir(resolve(context, "app"));
    await copyRequiredApp(smsRoot, resolve(context, "app"));
    for (const name of ["Dockerfile", "entrypoint.sh", "healthcheck.sh", "preflight.sh"]) {
      const source = name === "Dockerfile" ? resolve(smsRoot, "Dockerfile") : resolve(smsRoot, "docker", name);
      await cp(source, resolve(context, name));
    }
    await writeFile(resolve(context, ".dockerignore"), "*~\n*.key\n*.p12\n*.pfx\n");
    await run("docker", ["build", "--pull=false", "--network", "none", "--platform", "linux/amd64", "--build-arg", `BUILD_COMMIT=${options.sourceCommit}`, "--tag", options.tag, context], { cwd: context, timeoutMs: options.timeoutMs });
    const image = JSON.parse((await run("docker", ["image", "inspect", options.tag], { capture: true })).stdout)[0];
    if (image?.Os !== "linux" || image?.Architecture !== "amd64" || image?.Config?.User !== "10001:10001") throw new Error("built OCI image does not satisfy the platform/user contract");
    process.stdout.write(`${options.tag} ${image.Id}\n`);
  } finally {
    await rm(context, { recursive: true, force: true });
  }
}

try {
  await build(parse(process.argv.slice(2)));
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
