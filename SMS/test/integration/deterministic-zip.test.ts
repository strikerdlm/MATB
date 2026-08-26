import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, it } from "vitest";
import { writeDeterministicZip } from "../../scripts/deterministic-zip.mjs";

const execute = promisify(execFile);
const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("deterministic ZIP writer", () => {
  it("writes portable reproducible ZIP bytes without invoking a system zip executable", async () => {
    const root = await mkdtemp(join(tmpdir(), "sms-deterministic-zip-"));
    temporaryDirectories.push(root);
    const alpha = join(root, "alpha.txt");
    const nested = join(root, "nested.txt");
    await writeFile(alpha, "alpha\n");
    await writeFile(nested, "nested\n");
    const entries = [
      { archivePath: "bundle/zeta.txt", sourcePath: nested, mode: 0o444 },
      { archivePath: "bundle/alpha.txt", sourcePath: alpha, mode: 0o444 },
    ];
    const first = join(root, "first.zip");
    const second = join(root, "second.zip");

    await writeDeterministicZip(first, entries, 1_700_000_000);
    await writeDeterministicZip(second, [...entries].reverse(), 1_700_000_000);

    expect(await readFile(second)).toEqual(await readFile(first));
    expect((await execute("unzip", ["-Z1", first])).stdout.trim().split(/\r?\n/u)).toEqual([
      "bundle/alpha.txt",
      "bundle/zeta.txt",
    ]);
    expect((await execute("unzip", ["-p", first, "bundle/zeta.txt"])).stdout).toBe("nested\n");
  });
});
