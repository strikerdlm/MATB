import type { SourceRecord } from "./types.js";

export { SourceRegister } from "./source-register.js";
export { assertClaimTraceable } from "./claims.js";

export { canonicalJson, sha256File } from "./hash.js";
export { assertSignedPackageManifest, manifestContentDigest, rejectDowngrade, signManifest, verifyPackage } from "./manifest.js";
export type {
  EvidenceId,
  EvidenceReference,
  NormalizedRequirement,
  RequirementTranslation,
  ManifestFile,
  PackageDependency,
  SignedPackageManifest,
  SourceId,
  SourceRecord,
  SupersessionRelationship,
} from "./types.js";
export type { VerificationReport } from "./manifest.js";
export { assertSourceRecord } from "./source-validation.js";
