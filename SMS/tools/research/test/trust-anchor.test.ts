import { generateKeyPairSync } from "node:crypto";
import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { PINNED_PUBLIC_KEYS, pinnedPublicKeyFor } from "../src/trust-anchor.js";

const manifest = { keyId: "ed25519-sha256-7e01102cfa67dbe1" };

describe("production evidence trust anchors", () => {
  it("resolves the compiled key and corroborates the package PEM", async () => {
    const packageKey = await readFile(new URL("../../../docs/provenance/evidence-package-public-key.pem", import.meta.url), "utf8");
    expect(pinnedPublicKeyFor(manifest, packageKey)).toBe(PINNED_PUBLIC_KEYS[manifest.keyId].pem);
  });

  it("does not accept an unpinned or package-only verification key", () => {
    const pair = generateKeyPairSync("ed25519");
    const otherKey = pair.publicKey.export({ type: "spki", format: "pem" }).toString();
    expect(() => pinnedPublicKeyFor({ keyId: "untrusted-key" }, otherKey)).toThrow("not pinned");
    expect(() => pinnedPublicKeyFor(manifest, otherKey)).toThrow("does not match pinned");
  });

  it("detects accidental edits to the compiled trust anchor", () => {
    const pinned = PINNED_PUBLIC_KEYS[manifest.keyId];
    expect(pinned.keyId).toBe(manifest.keyId);
    expect(pinned.fingerprintSha256).toBe("7e01102cfa67dbe127297bb503d92512c237f65dcb38388ec0643973255cc7e8");
  });
});
