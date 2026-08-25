import { describe, expect, it } from "vitest";
import { verifiedOciReference, validateLoadedOciIdentity } from "../../scripts/oci-candidate-runtime.mjs";

const artifactSha256 = "a".repeat(64);
const identity = {
  ociConfigDigest: `sha256:${"b".repeat(64)}`,
  ociDiffIds: [`sha256:${"c".repeat(64)}`, `sha256:${"d".repeat(64)}`],
};
const inspection = {
  Id: identity.ociConfigDigest,
  Os: "linux",
  Architecture: "amd64",
  RootFS: { Type: "layers", Layers: identity.ociDiffIds },
};

describe("loaded OCI candidate identity", () => {
  it("derives an immutable temporary reference and rejects any loaded config or rootfs mismatch", () => {
    expect(verifiedOciReference(artifactSha256)).toBe(`fac-isr-sms-verified:${artifactSha256}`);
    expect(validateLoadedOciIdentity(inspection, identity)).toEqual({ layerCount: 2 });
    expect(() => validateLoadedOciIdentity({ ...inspection, Id: `sha256:${"e".repeat(64)}` }, identity)).toThrow(/config/u);
    expect(() => validateLoadedOciIdentity({ ...inspection, RootFS: { Type: "layers", Layers: identity.ociDiffIds.slice(1) } }, identity)).toThrow(/rootfs/u);
  });
});
