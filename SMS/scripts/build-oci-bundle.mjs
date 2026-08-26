#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { chmod, copyFile, mkdir, mkdtemp, readFile, readdir, rm, stat, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";

const ARTIFACT = "fac-isr-sms-0.2.0-rc.1-linux-amd64.oci.tar";

function parse(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (["--image-ref", "--output-dir", "--source-date-epoch"].includes(argument)) {
      const value = argv[++index];
      if (!value || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      options[argument.slice(2).replaceAll(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = value;
    } else throw new Error(`unknown argument: ${argument}`);
  }
  if (!options.imageRef || !options.outputDir) throw new Error("--image-ref and --output-dir are required");
  const epoch = Number(options.sourceDateEpoch ?? process.env.SOURCE_DATE_EPOCH);
  if (!Number.isInteger(epoch) || epoch < 315532800) throw new Error("a deterministic --source-date-epoch is required");
  return { ...options, epoch };
}

function run(command, args, options = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { cwd: options.cwd, env: { ...process.env, TZ: "UTC", ...options.env }, stdio: options.capture ? ["ignore", "pipe", "pipe"] : "inherit" });
    const stdout = [];
    const stderr = [];
    child.stdout?.on("data", (chunk) => stdout.push(chunk));
    child.stderr?.on("data", (chunk) => stderr.push(chunk));
    child.once("error", reject);
    child.once("close", (code) => {
      const result = { stdout: Buffer.concat(stdout).toString("utf8"), stderr: Buffer.concat(stderr).toString("utf8") };
      if (code === 0) resolvePromise(result);
      else reject(new Error(`${command} failed (${code}): ${result.stderr.trim()}`));
    });
  });
}

async function digest(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

async function putBlob(layout, source) {
  const sha256 = await digest(source);
  const destination = resolve(layout, "blobs/sha256", sha256);
  await mkdir(dirname(destination), { recursive: true });
  await copyFile(source, destination);
  return { digest: `sha256:${sha256}`, size: (await stat(source)).size };
}

async function normalize(directory, date) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) await normalize(path, date);
    else if (entry.isFile()) { await chmod(path, 0o444); await utimes(path, date, date); }
    else throw new Error(`unsupported OCI layout entry: ${path}`);
  }
  await chmod(directory, 0o755);
  await utimes(directory, date, date);
}

async function makeWritable(directory) {
  try {
    await chmod(directory, 0o700);
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) await makeWritable(path);
      else await chmod(path, 0o600);
    }
  } catch (error) {
    if (!(error instanceof Error && error.code === "ENOENT")) throw error;
  }
}

async function build(options) {
  const inspection = JSON.parse((await run("docker", ["image", "inspect", options.imageRef], { capture: true })).stdout)[0];
  if (inspection?.Os !== "linux" || inspection?.Architecture !== "amd64") throw new Error("OCI input image must be linux/amd64");
  const stage = await mkdtemp(join(tmpdir(), "sms-oci-stage-"));
  try {
    const dockerArchive = resolve(stage, "docker-image.tar");
    const extracted = resolve(stage, "docker-image");
    const layout = resolve(stage, "oci-layout-root");
    await mkdir(extracted);
    await mkdir(layout);
    await run("docker", ["image", "save", "--platform", "linux/amd64", "--output", dockerArchive, options.imageRef]);
    const listing = (await run("tar", ["-tf", dockerArchive], { capture: true })).stdout;
    for (const path of listing.split(/\r?\n/u).filter(Boolean)) if (path.startsWith("/") || path.split("/").includes("..")) throw new Error(`unsafe Docker archive path: ${path}`);
    await run("tar", ["-xf", dockerArchive, "-C", extracted]);
    const dockerManifest = JSON.parse(await readFile(resolve(extracted, "manifest.json"), "utf8"));
    if (!Array.isArray(dockerManifest) || dockerManifest.length !== 1) throw new Error("Docker archive must contain exactly one image");
    const record = dockerManifest[0];
    const config = await putBlob(layout, resolve(extracted, record.Config));
    const layers = [];
    for (const layer of record.Layers) {
      const blob = await putBlob(layout, resolve(extracted, layer));
      layers.push({ mediaType: "application/vnd.oci.image.layer.v1.tar", ...blob });
    }
    const manifestBody = Buffer.from(`${JSON.stringify({ schemaVersion: 2, mediaType: "application/vnd.oci.image.manifest.v1+json", config: { mediaType: "application/vnd.oci.image.config.v1+json", ...config }, layers }, null, 2)}\n`);
    const manifestSha = createHash("sha256").update(manifestBody).digest("hex");
    const manifestPath = resolve(layout, "blobs/sha256", manifestSha);
    await writeFile(manifestPath, manifestBody);
    await writeFile(resolve(layout, "oci-layout"), '{"imageLayoutVersion":"1.0.0"}\n');
    await writeFile(resolve(layout, "index.json"), `${JSON.stringify({ schemaVersion: 2, mediaType: "application/vnd.oci.image.index.v1+json", manifests: [{ mediaType: "application/vnd.oci.image.manifest.v1+json", digest: `sha256:${manifestSha}`, size: manifestBody.length, platform: { architecture: "amd64", os: "linux" }, annotations: { "org.opencontainers.image.ref.name": "fac-isr-sms:0.2.0-rc.1" } }] }, null, 2)}\n`);
    const date = new Date(options.epoch * 1000);
    await normalize(layout, date);
    const output = resolve(options.outputDir);
    await mkdir(output, { recursive: true });
    const artifact = resolve(output, ARTIFACT);
    await rm(artifact, { force: true });
    await run("tar", ["--sort=name", `--mtime=@${options.epoch}`, "--owner=0", "--group=0", "--numeric-owner", "--format=posix", "--pax-option=delete=atime,delete=ctime", "-cf", artifact, "blobs", "index.json", "oci-layout"], { cwd: layout });
    process.stdout.write(`${artifact}\n`);
  } finally {
    await makeWritable(stage);
    await rm(stage, { recursive: true, force: true });
  }
}

try {
  await build(parse(process.argv.slice(2)));
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
