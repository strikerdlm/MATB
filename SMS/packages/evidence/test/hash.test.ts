import { createHash } from "node:crypto";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { fileURLToPath } from "node:url";
import { canonicalJson, sha256File } from "../src/hash.js";

describe("sha256File", () => {
  it("hashes a file deterministically", async () => {
    const directory = await mkdtemp(join(tmpdir(), "fac-isr-evidence-"));
    const path = join(directory, "source.txt");
    const contents = "controlled evidence\n";
    await writeFile(path, contents, "utf8");

    const expected = createHash("sha256").update(contents).digest("hex");
    await expect(sha256File(path)).resolves.toBe(expected);
  });

  it("rejects a missing file", async () => {
    await expect(sha256File("/definitely/missing/source.pdf")).rejects.toBeDefined();
  });

  it("matches the known RACAE 94 Amendment 2 checksum when the fixture is present", async () => {
    const fixture = process.env.RACAE94_FIXTURE ?? fileURLToPath(new URL("./fixtures/racae94_enm2.pdf", import.meta.url));
    await expect(sha256File(fixture)).resolves.toBe(
      "312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976",
    );
  });
});

describe("canonicalJson", () => {
  it("sorts keys by locale-independent code-unit order", () => {
    expect(canonicalJson({ z: 1, "ä": 2, a: 3 })).toBe('{"a":3,"z":1,"ä":2}');
  });

  it.each([
    ["undefined", undefined],
    ["function", () => "x"],
    ["bigint", 1n],
    ["symbol", Symbol("x")],
    ["infinity", Infinity],
    ["NaN", NaN],
    ["undefined property", { bad: undefined }],
  ])(
    "rejects unsupported JSON value (%s)",
    (_label, value) => expect(() => canonicalJson(value)).toThrow(TypeError),
  );
});
