import { describe, expect, it } from "vitest";
import { prepareVerifiedOciCandidate, verifiedOciReference, validateLoadedOciIdentity } from "../../scripts/oci-candidate-runtime.mjs";

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

  it("removes the owned hash-derived tag when post-tag identity inspection fails", async () => {
    const sourceReference = `fac-isr-sms-edge:${"f".repeat(40)}`;
    const verifiedReference = `fac-isr-sms-verified:${artifactSha256}`;
    const tags = new Set([sourceReference]);
    const runDocker = async (args: readonly string[]): Promise<{ stdout: string; stderr: string }> => {
      if (args[0] === "image" && args[1] === "inspect" && args[2] === sourceReference) {
        return { stdout: JSON.stringify([inspection]), stderr: "" };
      }
      if (args[0] === "image" && args[1] === "tag") {
        tags.add(String(args[3]));
        return { stdout: "", stderr: "" };
      }
      if (args[0] === "image" && args[1] === "inspect" && args[2] === verifiedReference) {
        throw new Error("post-tag inspect failed");
      }
      if (args[0] === "image" && args[1] === "rm") {
        tags.delete(String(args.at(-1)));
        return { stdout: "", stderr: "" };
      }
      throw new Error(`unexpected Docker arguments: ${args.join(" ")}`);
    };

    await expect(prepareVerifiedOciCandidate(sourceReference, {
      artifactSha256,
      ociReference: "fac-isr-sms:0.2.0-rc.1",
      ...identity,
    }, runDocker)).rejects.toThrow("post-tag inspect failed");
    expect(tags.has(verifiedReference)).toBe(false);
  });
});
