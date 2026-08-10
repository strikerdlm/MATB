export interface LocalMapPackageDirectory {
  readonly packageId: string;
  readonly version: string;
  readonly manifestHash: string;
  readonly freshness: string;
}

export interface LocalMapVerification {
  readonly ok: boolean;
  readonly source: "local-package" | "none";
  readonly reason: string;
}

/**
 * Verifies the small manifest envelope before a local map source is mounted.
 * The browser never resolves a network tile URL; the edge package is the only
 * permitted map source for this shell.
 */
export function verifyLocalMapPackage(directory: LocalMapPackageDirectory): LocalMapVerification {
  if (directory.packageId.trim() === "") return { ok: false, source: "none", reason: "map package ID is missing" };
  if (!/^sha256:[a-f0-9-]+$/i.test(directory.manifestHash)) return { ok: false, source: "none", reason: "map manifest hash is not verified" };
  if (directory.version.trim() === "") return { ok: false, source: "none", reason: "map package version is missing" };
  if (directory.freshness.trim() === "") return { ok: false, source: "none", reason: "map package freshness is unknown" };
  return { ok: true, source: "local-package", reason: "verified local package" };
}

export function localMapSource(directory: LocalMapPackageDirectory): string {
  const verification = verifyLocalMapPackage(directory);
  return verification.ok ? `${verification.source}:${directory.packageId}:${directory.version}` : "none";
}
