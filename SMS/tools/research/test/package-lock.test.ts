import { constants as fsConstants } from "node:fs";
import { generateKeyPairSync } from "node:crypto";
import { lstat, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

const closeInjection = vi.hoisted(() => ({
  parentPath: undefined as string | undefined,
  injected: false,
}));

vi.mock("node:fs/promises", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs/promises")>();
  return {
    ...actual,
    open: async (...args: Parameters<typeof actual.open>) => {
      const handle = await actual.open(...args);
      const flags = args[1];
      if (typeof flags === "number" && (flags & fsConstants.O_DIRECTORY) !== 0 && closeInjection.parentPath !== undefined) {
        const target = await actual.readlink(`/proc/self/fd/${handle.fd}`).catch(() => "");
        if (target === closeInjection.parentPath) {
          const close = handle.close.bind(handle);
          handle.close = async () => {
            const result = await close();
            if (!closeInjection.injected) {
              closeInjection.injected = true;
              throw new Error("injected parent close failure");
            }
            return result;
          };
        }
      }
      return handle;
    },
  };
});

import { assembleEvidencePackage } from "../src/package.js";

const paths: string[] = [];
const pair = generateKeyPairSync("ed25519");
const privateKey = pair.privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const isWindows = process.platform === "win32";

afterEach(async () => {
  closeInjection.parentPath = undefined;
  closeInjection.injected = false;
  await Promise.all(paths.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

function input(sourceRoot: string, outputDirectory: string) {
  return {
    sourceRoot,
    outputDirectory,
    files: [{ sourcePath: "rule.json" }],
    privateKey,
    manifest: {
      schemaVersion: "1.0" as const,
      packageId: "fac-package-lock-test",
      kind: "regulatory" as const,
      issuer: "test issuer",
      version: "1.0.0",
      issuedAtUtc: "2026-08-08T00:00:00Z",
      effectiveFromUtc: "2026-08-08T00:00:00Z",
      geographicScope: "Colombia",
      keyId: "test",
      dependencies: [],
      qualification: "qualified-review" as const,
      caveats: ["test only"],
    },
  };
}

describe.skipIf(isWindows)("publish-lock cleanup", () => {
  it("releases the lock when final parent-handle cleanup fails", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-lock-source-"));
    const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-lock-output-"));
    const output = join(outputParent, "package");
    paths.push(root, outputParent);
    await writeFile(join(root, "rule.json"), "{}\n");
    closeInjection.parentPath = outputParent;

    await expect(assembleEvidencePackage(input(root, output))).rejects.toThrow("injected parent close failure");
    await expect(lstat(output)).resolves.toBeDefined();

    const retry = assembleEvidencePackage(input(root, output)).then(
      () => { throw new Error("unexpected package replacement"); },
      (error: unknown) => { throw error; },
    );
    await expect(Promise.race([
      retry,
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error("publish lock was not released")), 1000)),
    ])).rejects.toThrow("already exists");
  });
});
