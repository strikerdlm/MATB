import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  canonicalJson,
  exactUtc,
  resolveContainedExistingFile,
  sha256Bytes,
} from "../../scripts/acceptance-contracts.mjs";

const roots: string[] = [];
afterEach(async () => Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))));

describe("acceptance contracts", () => {
  it("canonicalizes object keys recursively without reordering arrays", () => {
    const value = { z: [{ b: 2, a: 1 }], a: "value" };
    expect(canonicalJson(value)).toBe('{"a":"value","z":[{"a":1,"b":2}]}');
    expect(sha256Bytes(Buffer.from("verified\n"))).toBe("672eb8316fec83f94119a4193f9fc552513d56a147502f8be4830e017d817831");
  });

  it.each([
    ["2026-08-12T16:00:00Z", true],
    ["2026-08-12T16:00:00.000Z", true],
    ["2026-02-30T00:00:00Z", false],
    ["2026-08-12 16:00:00Z", false],
  ] as const)("validates exact UTC %s", (value, expected) => {
    expect(exactUtc(value)).toBe(expected);
  });

  it("rejects traversal and every symlink even when its target remains contained", async () => {
    const root = await mkdtemp(join(tmpdir(), "acceptance-contracts-"));
    roots.push(root);
    await mkdir(join(root, "docs/release"), { recursive: true });
    await writeFile(join(root, "outside.txt"), "outside\n", "utf8");
    await symlink(join(root, "outside.txt"), join(root, "docs/release/link.txt"));
    await expect(resolveContainedExistingFile(root, "../escape.txt", "evidence")).rejects.toThrow(/relative|traversal/u);
    await expect(resolveContainedExistingFile(root, "docs/release/link.txt", "evidence")).rejects.toThrow(/symbolic link/u);
  });
});
