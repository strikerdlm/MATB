import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, it } from "vitest";

const execute = promisify(execFile);
const temporaryDirectories: string[] = [];
const sourceCommit = "a".repeat(40);

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("release evidence writer", () => {
  it("hash-locks a clean scanner result to every exact target artifact", async () => {
    const root = await mkdtemp(join(tmpdir(), "sms-evidence-writer-"));
    temporaryDirectories.push(root);
    const artifacts = {
      "linux-x64": "linux bundle",
      "win32-x64": "windows bundle",
      "linux-amd64-oci": "oci bundle",
    };
    const args: string[] = [];
    const expectedHashes: Record<string, string> = {};
    for (const [target, contents] of Object.entries(artifacts)) {
      const path = join(root, `${target}.artifact`);
      await writeFile(path, contents);
      expectedHashes[target] = createHash("sha256").update(contents).digest("hex");
      args.push("--artifact", `${target}=${path}`);
    }
    const scannerOutput = join(root, "npm-audit.json");
    await writeFile(scannerOutput, JSON.stringify({ auditReportVersion: 2, metadata: { vulnerabilities: { total: 0 } }, vulnerabilities: {} }));
    const output = join(root, "dependency-scan.json");

    await execute(process.execPath, [
      resolve("scripts/write-release-evidence.mjs"), "attest",
      "--type", "dependency-scan", "--source-commit", sourceCommit,
      "--scanner", "npm-audit-node-22.23.2", "--input", scannerOutput,
      "--scanner-output-path", "scan-output/npm-audit.json", "--threshold", "low",
      ...args, "--output", output,
    ], { cwd: resolve(".") });

    const record = JSON.parse(await readFile(output, "utf8"));
    expect(record).toMatchObject({
      type: "dependency-scan",
      scanner: "npm-audit-node-22.23.2",
      scannerOutputPath: "scan-output/npm-audit.json",
      threshold: "low",
      findingsAtOrAboveThreshold: 0,
      artifactSha256s: expectedHashes,
    });
    expect(record.scannerOutputSha256).toMatch(/^[a-f0-9]{64}$/u);
  });
});
