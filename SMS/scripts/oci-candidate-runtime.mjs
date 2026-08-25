import { spawn } from "node:child_process";

function assertDigest(value, label) {
  if (!/^sha256:[a-f0-9]{64}$/u.test(value ?? "")) throw new Error(`${label} is not an exact sha256 digest`);
}

function docker(args, timeoutMs = 120_000) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn("docker", args, { windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 5_000).unref();
    }, timeoutMs);
    child.once("error", (error) => { clearTimeout(timer); reject(error); });
    child.once("close", (code, signal) => {
      clearTimeout(timer);
      if (code === 0) resolvePromise({ stdout, stderr });
      else reject(new Error(`docker ${args[0]} failed (${signal ?? code}): ${stderr.trim()}`));
    });
  });
}

export function verifiedOciReference(artifactSha256) {
  if (!/^[a-f0-9]{64}$/u.test(artifactSha256 ?? "")) throw new Error("OCI artifact hash is not an exact sha256");
  return `fac-isr-sms-verified:${artifactSha256}`;
}

export function validateLoadedOciIdentity(loaded, expected) {
  assertDigest(expected.ociConfigDigest, "verified OCI config digest");
  if (!Array.isArray(expected.ociDiffIds) || expected.ociDiffIds.length === 0) throw new Error("verified OCI rootfs is empty");
  expected.ociDiffIds.forEach((digest) => assertDigest(digest, "verified OCI diff ID"));
  if (loaded?.Id !== expected.ociConfigDigest) throw new Error("loaded OCI config digest differs from the verified archive");
  if (loaded?.Os !== "linux" || loaded?.Architecture !== "amd64") throw new Error("loaded OCI platform differs from linux/amd64");
  const layers = loaded?.RootFS?.Layers;
  if (loaded?.RootFS?.Type !== "layers" || !Array.isArray(layers) || JSON.stringify(layers) !== JSON.stringify(expected.ociDiffIds)) {
    throw new Error("loaded OCI rootfs differs from the verified archive");
  }
  return { layerCount: layers.length };
}

export async function prepareVerifiedOciCandidate(sourceReference, expected, runDocker = docker) {
  if (typeof sourceReference !== "string" || sourceReference.length === 0) throw new Error("verified OCI archive has no source reference");
  const inspected = await runDocker(["image", "inspect", sourceReference]);
  const parsed = JSON.parse(inspected.stdout);
  if (!Array.isArray(parsed) || parsed.length !== 1) throw new Error("loaded OCI inspection did not identify exactly one image");
  validateLoadedOciIdentity(parsed[0], expected);
  const reference = verifiedOciReference(expected.artifactSha256);
  await runDocker(["image", "tag", sourceReference, reference], 30_000);
  try {
    const tagged = await runDocker(["image", "inspect", reference], 30_000);
    const taggedParsed = JSON.parse(tagged.stdout);
    if (!Array.isArray(taggedParsed) || taggedParsed.length !== 1) throw new Error("tagged OCI inspection did not identify exactly one image");
    validateLoadedOciIdentity(taggedParsed[0], expected);
    return reference;
  } catch (error) {
    try {
      await runDocker(["image", "rm", "--force", reference], 30_000);
    } catch {
      // The post-tag identity failure is the security-relevant primary error.
    }
    throw error;
  }
}

export async function removeVerifiedOciCandidate(reference) {
  if (!/^fac-isr-sms-verified:[a-f0-9]{64}$/u.test(reference ?? "")) throw new Error("refusing to remove an unowned OCI reference");
  await docker(["image", "rm", "--force", reference], 30_000);
}
