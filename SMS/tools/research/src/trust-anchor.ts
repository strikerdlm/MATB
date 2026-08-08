import { createHash } from "node:crypto";
import type { SignedPackageManifest } from "@fac-isr/evidence";

/**
 * Production verification anchors are compiled into the verifier rather than
 * read from the evidence directory being verified. Key rotation is an
 * explicit code-reviewed change: add the new key and its immutable fingerprint
 * here, then retire the old entry only after an approved transition period.
 */
export interface PinnedPublicKey {
  keyId: string;
  pem: string;
  fingerprintSha256: string;
}

const P0_KEY: PinnedPublicKey = Object.freeze({
  keyId: "ed25519-sha256-7e01102cfa67dbe1",
  pem: "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAuXhYYnQQTrzQqrWIAGkePHapUFAd8yLhfh0hRNvhsjE=\n-----END PUBLIC KEY-----\n",
  fingerprintSha256: "7e01102cfa67dbe127297bb503d92512c237f65dcb38388ec0643973255cc7e8",
});

/** Immutable verifier trust store. This object is intentionally not package data. */
export const PINNED_PUBLIC_KEYS: Readonly<Record<string, PinnedPublicKey>> = Object.freeze({
  [P0_KEY.keyId]: P0_KEY,
});

function fingerprint(value: string | Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

/**
 * Resolve a manifest key ID to a compiled-in verification key and, when
 * supplied, require the package's informational PEM to match that anchor.
 * The package PEM is therefore corroborating metadata, never the trust root.
 */
export function pinnedPublicKeyFor(
  manifest: Pick<SignedPackageManifest, "keyId">,
  packagePublicKey?: string | Buffer,
): string {
  const anchor = PINNED_PUBLIC_KEYS[manifest.keyId];
  if (anchor === undefined) throw new Error(`evidence package keyId is not pinned: ${manifest.keyId}`);
  if (anchor.keyId !== manifest.keyId || fingerprint(anchor.pem) !== anchor.fingerprintSha256) {
    throw new Error(`compiled evidence trust anchor is inconsistent: ${manifest.keyId}`);
  }
  if (packagePublicKey !== undefined && fingerprint(packagePublicKey) !== anchor.fingerprintSha256) {
    throw new Error(`evidence package public key does not match pinned keyId: ${manifest.keyId}`);
  }
  return anchor.pem;
}
