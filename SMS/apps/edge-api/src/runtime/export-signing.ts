import { createPrivateKey, sign } from "node:crypto";
import { readFile } from "node:fs/promises";

export interface MissionExportSigner {
  readonly keyId: string;
  readonly algorithm: "Ed25519";
  sign(payload: Buffer): string;
}

export async function loadMissionExportSigner(path: string | undefined, keyId: string | undefined): Promise<MissionExportSigner | undefined> {
  if (path === undefined || keyId === undefined) return undefined;
  let key;
  try {
    key = createPrivateKey(await readFile(path));
  } catch {
    throw new Error("runtime export signing key could not be loaded");
  }
  if (key.asymmetricKeyType !== "ed25519") throw new Error("runtime export signing key must be Ed25519");
  return Object.freeze({ keyId, algorithm: "Ed25519" as const, sign: (payload: Buffer) => sign(null, payload, key).toString("base64") });
}
