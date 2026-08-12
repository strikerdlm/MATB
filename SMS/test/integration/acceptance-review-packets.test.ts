import { createHash } from "node:crypto";
import { cp, mkdtemp, readFile, readdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { canonicalJson } from "../../scripts/acceptance-contracts.mjs";
import { generateAcceptanceReviewPackets } from "../../scripts/generate-acceptance-review-packets.mjs";

const temporaryDirectories: string[] = [];
const smsRoot = process.cwd();
const options = { asOfUtc: "2026-08-12T16:00:00.000Z" } as const;

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function temporaryRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "fac-isr-review-packets-"));
  temporaryDirectories.push(root);
  return root;
}

async function authoritativeHashes(root: string): Promise<readonly { readonly path: string; readonly sha256: string }[]> {
  return Promise.all([
    "docs/release/operational-readiness-record.json",
    "docs/release/verification-signatures.jsonl",
  ].map(async (path) => ({
    path,
    sha256: createHash("sha256").update(await readFile(join(root, path))).digest("hex"),
  })));
}

async function directoryDigest(directory: string): Promise<string> {
  const files: { path: string; sha256: string }[] = [];
  async function visit(path: string): Promise<void> {
    for (const entry of await readdir(path, { withFileTypes: true })) {
      const child = join(path, entry.name);
      if (entry.isDirectory()) await visit(child);
      else if (entry.isFile()) files.push({
        path: relative(directory, child).replaceAll("\\", "/"),
        sha256: createHash("sha256").update(await readFile(child)).digest("hex"),
      });
    }
  }
  await visit(directory);
  return createHash("sha256").update(canonicalJson(files.sort((left, right) => left.path.localeCompare(right.path)))).digest("hex");
}

async function copiedSmsRoot(): Promise<string> {
  const root = await temporaryRoot();
  await cp(join(smsRoot, "docs"), join(root, "docs"), { recursive: true });
  return root;
}

describe("institutional acceptance review packets", () => {
  it("generates deterministic complete packets without changing authoritative acceptance evidence", async () => {
    const root = await temporaryRoot();
    const before = await authoritativeHashes(smsRoot);
    const first = await generateAcceptanceReviewPackets(smsRoot, join(root, "first"), options);
    await generateAcceptanceReviewPackets(smsRoot, join(root, "second"), options);

    expect(first.packets).toHaveLength(9);
    expect(await directoryDigest(join(root, "first"))).toBe(await directoryDigest(join(root, "second")));
    expect(await authoritativeHashes(smsRoot)).toEqual(before);
    for (const packet of first.packets) {
      expect(packet.manifest.recordType).toBe("review-packet");
      expect(packet.manifest.asOfUtc).toBe(options.asOfUtc);
      expect(packet.manifest.requiredReviewerRoles.length).toBeGreaterThan(0);
      expect(packet.manifest.blockers).toHaveLength(19);
      expect(packet.template.recordType).toBe("unsigned-decision-template");
      expect(packet.template.signatureId).toBeNull();
    }
  });

  it("generates only an explicitly selected approved scope", async () => {
    const root = await temporaryRoot();
    const result = await generateAcceptanceReviewPackets(smsRoot, join(root, "selected"), {
      ...options,
      scopes: ["risk-authority"],
    });

    expect(result.packetCount).toBe(1);
    expect(result.packets.map(({ manifest }) => manifest.scope)).toEqual(["risk-authority"]);
    expect((await readdir(join(root, "selected"))).length).toBe(1);
  });

  it("rejects an unknown scope", async () => {
    const root = await temporaryRoot();
    await expect(generateAcceptanceReviewPackets(smsRoot, join(root, "unknown"), {
      ...options,
      scopes: ["unapproved-scope"],
    })).rejects.toThrow(/scope/u);
  });

  it("refuses an output directory inside the release evidence tree", async () => {
    const root = await copiedSmsRoot();
    await expect(generateAcceptanceReviewPackets(root, join(root, "docs/release/acceptance-packets"), options))
      .rejects.toThrow(/docs\/release/u);
  });

  it("refuses an output path that resolves through a symlink into the release evidence tree", async () => {
    const root = await copiedSmsRoot();
    const outputLink = join(root, "release-link");
    await symlink(join(root, "docs/release"), outputLink);
    await expect(generateAcceptanceReviewPackets(root, join(outputLink, "acceptance-packets"), options))
      .rejects.toThrow(/docs\/release/u);
  });

  it.each([undefined, "2026-08-12T24:00:00.000Z", "not-a-time"])
  ("rejects a missing or non-exact UTC asOfUtc value: %s", async (asOfUtc) => {
    const root = await temporaryRoot();
    await expect(generateAcceptanceReviewPackets(smsRoot, join(root, "invalid-time"), {
      asOfUtc: asOfUtc as string,
    })).rejects.toThrow(/asOfUtc/u);
  });

  it("changes the acceptance-state fingerprint when readiness-record bytes change", async () => {
    const root = await copiedSmsRoot();
    const before = await generateAcceptanceReviewPackets(root, join(root, "before"), options);
    const recordPath = join(root, "docs/release/operational-readiness-record.json");
    await writeFile(recordPath, `${await readFile(recordPath, "utf8")}\n`, "utf8");
    const after = await generateAcceptanceReviewPackets(root, join(root, "after"), options);

    expect(after.packets[0]?.manifest.acceptanceStateFingerprint)
      .not.toBe(before.packets[0]?.manifest.acceptanceStateFingerprint);
  });

  it("derives each packet ID from the canonical manifest without its packetId", async () => {
    const root = await temporaryRoot();
    const result = await generateAcceptanceReviewPackets(smsRoot, join(root, "packets"), options);

    for (const { manifest } of result.packets) {
      const { packetId: _packetId, ...unsignedManifest } = manifest;
      expect(manifest.packetId).toBe(createHash("sha256").update(canonicalJson(unsignedManifest)).digest("hex"));
    }
  });
});
