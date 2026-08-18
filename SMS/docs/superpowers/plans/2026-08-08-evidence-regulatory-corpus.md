# Evidence Acquisition and Colombian Regulatory Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Every imported source and normalized rule requires an independent evidence check.

**Goal:** Create an offline-verifiable evidence library and signed regulatory/policy package for FAC ISR State Aviation operations, starting with current AAAES and RACAE material and preserving provenance for every normalized requirement.

**Architecture:** Connected research happens only on a staging workstation through Tavily, Brave, Firecrawl, direct official downloads, and approved academic sources. The resulting immutable originals, extracted text, normalized requirements, controlled translations, and source register are packaged separately; the edge node imports only signed packages and never needs internet access.

**Tech Stack:** Node.js 22 LTS; TypeScript 5.7+ strict; npm workspaces; Zod; Node `crypto` SHA-256/Ed25519; SQLite-compatible JSONL export; Vitest; Firecrawl/Tavily/Brave research logs; ClamAV or approved malware scanner on staging.

## Global Constraints

- Official Colombian State Aviation authority is AAAES; the initial primary corpus is RACAE 94 Amendment 2 and RACAE 219, followed by the applicable RACAE/RAC/RAC 100 sources listed in the approved design.
- The official RACAE 94 Amendment 2 source is `https://aaaes.fac.mil.co/sites/aaaes/files/documentos%20aaaes/racae_94_enmienda_2_reglas_de_vuelo_y_operacion_uasrpas_0.pdf`.
- The downloaded RACAE 94 Amendment 2 fixture must reproduce SHA-256 `312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976` before promotion.
- Discovery results from Tavily, Brave, and Firecrawl are leads; only the underlying primary or scholarly source can satisfy a requirement.
- Originals are immutable; extracted text, normalized requirements, translations, and interpretations are separate versioned artifacts.
- Obsidian notes are copied, never moved, and preserve original vault path and checksum. They do not outrank current official publications.
- Spanish source text remains authoritative; English is labelled as a controlled translation and never drives rule behavior independently.
- Missing, conflicting, stale, unsigned, or unreviewed evidence cannot satisfy a hard safety rule.
- The first package is unclassified controlled safety metadata only.

## File Map

- Create: `SMS/package.json` — workspace scripts and dependency policy.
- Create: `SMS/tsconfig.base.json` — strict shared TypeScript configuration.
- Create: `SMS/packages/evidence/src/types.ts` — source, edition, extraction, review, and claim interfaces.
- Create: `SMS/packages/evidence/src/hash.ts` — streaming SHA-256 and canonical JSON hashing.
- Create: `SMS/packages/evidence/src/manifest.ts` — signed package manifest validation.
- Create: `SMS/packages/evidence/src/source-register.ts` — append-only source-register operations.
- Create: `SMS/packages/evidence/src/claims.ts` — claim-to-evidence traceability.
- Create: `SMS/packages/evidence/src/index.ts` — public package API.
- Create: `SMS/packages/evidence/test/*.test.ts` — hash, manifest, provenance, and immutability tests.
- Create: `SMS/tools/research/src/cli.ts` — staging-only research and package CLI.
- Create: `SMS/tools/research/src/acquire.ts` — acquisition record builder.
- Create: `SMS/tools/research/src/normalize.ts` — extracted-text and normalized-requirement import validation.
- Create: `SMS/tools/research/src/package.ts` — package assembly and signing.
- Create: `SMS/tools/research/test/*.test.ts` — CLI fixture tests.
- Create: `SMS/docs/source-register/sources.jsonl` — registered authority and evidence metadata.
- Create: `SMS/docs/research/query-log.jsonl` — Tavily/Brave/Firecrawl query provenance.
- Create: `SMS/docs/regulations/original/` — immutable official files.
- Create: `SMS/docs/regulations/extracted/` — checksum-linked text extraction.
- Create: `SMS/docs/regulations/normalized/` — reviewed normalized rules.
- Create: `SMS/docs/obsidian-imports/` — copied context notes and discrepancy records.
- Create: `SMS/docs/provenance/` — package manifests, signatures, and review evidence.

## Interfaces

```ts
export type EvidenceId = string & { readonly __brand: "EvidenceId" };
export type SourceId = string & { readonly __brand: "SourceId" };

export interface SourceRecord {
  sourceId: SourceId;
  title: string;
  authority: string;
  authorityRank: 1 | 2 | 3 | 4 | 5 | 6 | 7;
  canonicalUri: string;
  localPath: string;
  mediaType: string;
  language: "es" | "en" | "multi";
  publicationDate?: string;
  amendmentDate?: string;
  effectiveFromUtc?: string;
  retrievedAtUtc: string;
  sha256: string;
  extractionSha256?: string;
  sensitivity: "unclassified-controlled";
  licenseOrRestriction: string;
  review: "unreviewed" | "in-review" | "accepted" | "superseded" | "rejected";
  supersededBy?: SourceId;
}

export interface EvidenceReference {
  evidenceId: EvidenceId;
  sourceId: SourceId;
  edition: string;
  locator: { section?: string; page?: number; paragraph?: string };
  quoteLanguage: "es" | "en";
  extractionSha256: string;
  reviewerId?: string;
  reviewState: "unreviewed" | "accepted" | "rejected";
}

export interface NormalizedRequirement {
  requirementId: string;
  sourceRefs: EvidenceReference[];
  Spanish: string;
  EnglishControlled: string;
  applicabilityExpression: string;
  severity: "hard" | "soft" | "advisory";
  evidenceRequired: boolean;
  effectiveFromUtc: string;
  interpretationStatus: "draft" | "qualified-review" | "approved" | "superseded";
  reviewerIds: string[];
}

export interface RequirementTranslation {
  requirementId: string;
  sourceLanguage: "es";
  targetLanguage: "en";
  translatedText: string;
  translationStatus: "draft" | "reviewed" | "approved";
  reviewerIds: readonly string[];
}

export interface SignedPackageManifest {
  packageId: string;
  kind: "regulatory" | "policy" | "map" | "weather" | "notam" | "terminology" | "software";
  issuer: string;
  version: string;
  issuedAtUtc: string;
  effectiveFromUtc: string;
  expiresAtUtc?: string;
  geographicScope?: string;
  contentSha256: string;
  signature: string;
  keyId: string;
  dependencies: string[];
}

export interface VerificationReport {
  ok: boolean;
  checks: readonly { id: string; status: "pass" | "fail" | "warn"; reason?: string }[];
  packageId: string;
}
```

### Task 1: Establish the isolated TypeScript workspace

**Files:**
- Create: `SMS/package.json`
- Create: `SMS/tsconfig.base.json`
- Create: `SMS/vitest.workspace.ts`
- Create: `SMS/.gitignore`
- Create: `SMS/packages/evidence/package.json`
- Create: `SMS/packages/evidence/src/index.ts`
- Test: `SMS/packages/evidence/test/workspace.test.ts`

**Interfaces:**
- Produces the `@fac-isr/evidence` package consumed by every later plan.

- [ ] **Step 1: Write the failing package-export test**

```ts
import { describe, expect, it } from "vitest";
import { canonicalJson } from "../src/index.js";

describe("evidence workspace", () => {
  it("exports deterministic canonical JSON", () => {
    expect(canonicalJson({ b: 2, a: 1 })).toBe('{"a":1,"b":2}');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd SMS && npm test --workspace packages/evidence -- --run`
Expected: FAIL because the workspace and `canonicalJson` export do not exist.

- [ ] **Step 3: Add strict workspace configuration and the minimal export**

```json
{
  "name": "fac-isr-sms",
  "private": true,
  "workspaces": ["packages/*", "apps/*", "tools/*"],
  "scripts": {
    "typecheck": "tsc -b",
    "test": "vitest run",
    "lint": "eslint .",
    "verify:offline": "node tools/research/dist/cli.js verify-offline",
    "verify:no-c2": "node tools/research/dist/cli.js verify-no-c2"
  },
  "engines": { "node": ">=22.0.0" },
  "author": "Dr Diego Malpica — Aerospace Medicine and Human Performance — Subdirectorate of Aerospace Sciences — Colombian Aerospace Force"
}
```

```ts
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`);
  return `{${entries.join(",")}}`;
}
```

- [ ] **Step 4: Run the focused test and typecheck**

Run: `cd SMS && npm install && npm test --workspace packages/evidence -- --run && npm run typecheck`
Expected: PASS; strict compilation succeeds with no implicit `any`.

- [ ] **Step 5: Commit**

```bash
git add SMS/package.json SMS/tsconfig.base.json SMS/vitest.workspace.ts SMS/.gitignore SMS/packages/evidence
git commit -m "chore(sms): scaffold evidence workspace"
```

### Task 2: Implement checksummed source and extraction records

**Files:**
- Create: `SMS/packages/evidence/src/types.ts`
- Create: `SMS/packages/evidence/src/hash.ts`
- Modify: `SMS/packages/evidence/src/index.ts`
- Test: `SMS/packages/evidence/test/hash.test.ts`
- Test: `SMS/packages/evidence/test/source-record.test.ts`

**Interfaces:**
- Produces `sha256File(path): Promise<string>`, `canonicalJson(value): string`, `assertSourceRecord(record): SourceRecord`, and the types shown above.

- [ ] **Step 1: Write tests for deterministic hashing and the known official fixture**

```ts
it("matches the known RACAE 94 Amendment 2 checksum when the fixture is present", async () => {
  const fixture = process.env.RACAE94_FIXTURE ?? "test/fixtures/racae94_enm2.pdf";
  await expect(sha256File(fixture)).resolves.toBe(
    "312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976",
  );
});
```

- [ ] **Step 2: Run the tests to verify the missing implementation or fixture fails**

Run: `cd SMS && npm test --workspace packages/evidence -- hash.test.ts source-record.test.ts --run`
Expected: FAIL with a missing export or missing fixture; do not weaken the expected checksum.

- [ ] **Step 3: Implement streaming SHA-256 and runtime validation**

Use `createReadStream` and `createHash("sha256")`; reject missing files, empty source IDs, non-HTTPS external URIs, and sensitivity values other than `unclassified-controlled`.

- [ ] **Step 4: Run tests and typecheck**

Run: `cd SMS && npm test --workspace packages/evidence -- hash.test.ts source-record.test.ts --run && npm run typecheck`
Expected: PASS for valid fixtures and explicit failures for tampered or malformed records.

- [ ] **Step 5: Commit**

```bash
git add SMS/packages/evidence/src SMS/packages/evidence/test
git commit -m "feat(sms-evidence): add source hashing and validation"
```

### Task 3: Build the append-only source register and claim traceability

**Files:**
- Create: `SMS/packages/evidence/src/source-register.ts`
- Create: `SMS/packages/evidence/src/claims.ts`
- Modify: `SMS/packages/evidence/src/index.ts`
- Test: `SMS/packages/evidence/test/source-register.test.ts`
- Test: `SMS/packages/evidence/test/claims.test.ts`

**Interfaces:**
- `SourceRegister.append(record): void`
- `SourceRegister.get(sourceId): SourceRecord | undefined`
- `SourceRegister.listActive(): SourceRecord[]`
- `assertClaimTraceable(claim, register): void`

- [ ] **Step 1: Write the append-only and traceability tests**

```ts
it("rejects a second write for an existing source ID", () => {
  const register = new SourceRegister();
  register.append(validRecord);
  expect(() => register.append({ ...validRecord, sha256: "different" })).toThrow("immutable");
});

it("rejects a normalized requirement with no accepted evidence", () => {
  expect(() => assertClaimTraceable(unreviewedClaim, register)).toThrow("accepted evidence");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd SMS && npm test --workspace packages/evidence -- source-register.test.ts claims.test.ts --run`
Expected: FAIL because the register and claim validator are absent.

- [ ] **Step 3: Implement append-only in-memory and JSONL serialization**

Use a `Map<SourceId, SourceRecord>`; freeze records on append; serialize in stable source-ID order. A source can be superseded only by appending a new source and a separate relationship record; existing records are never edited.

- [ ] **Step 4: Run tests, including a reload round-trip**

Run: `cd SMS && npm test --workspace packages/evidence -- source-register.test.ts claims.test.ts --run`
Expected: PASS; serialized and reloaded registers preserve hashes, review states, and supersession links.

- [ ] **Step 5: Commit**

```bash
git add SMS/packages/evidence/src SMS/packages/evidence/test
git commit -m "feat(sms-evidence): add immutable source traceability"
```

### Task 4: Acquire and register the primary Colombian corpus

**Files:**
- Create: `SMS/docs/source-register/sources.jsonl`
- Create: `SMS/docs/research/query-log.jsonl`
- Create: `SMS/docs/regulations/original/racae_94_enmienda_2_reglas_de_vuelo_y_operacion_uasrpas_0.pdf`
- Create: `SMS/docs/regulations/original/racae_219_sistema_de_gestion_de_seguridad_operacional.pdf`
- Create: `SMS/docs/regulations/extracted/*.txt`
- Create: `SMS/docs/obsidian-imports/*.md`
- Create: `SMS/docs/obsidian-imports/discrepancies.md`
- Create: `SMS/tools/research/src/acquire.ts`
- Create: `SMS/tools/research/src/cli.ts`
- Test: `SMS/tools/research/test/acquire.test.ts`

**Interfaces:**
- `acquireOfficialSource(input): Promise<SourceRecord>`
- `copyObsidianNote(input): Promise<SourceRecord>`
- CLI commands: `research record-query`, `research acquire`, `research copy-obsidian`, `research extract`, `research verify`.

- [ ] **Step 1: Record the bounded research queries before downloading**

On the connected staging workstation, run and save results plus timestamps for:

```text
site:aaaes.fac.mil.co RACAE 94 enmienda 2 UAS RPAS
site:aaaes.fac.mil.co RACAE 219 sistema de gestión de seguridad operacional
site:aerocivil.gov.co RAC 100 UAS resolución vigente
AAAES RACAE 94 94.201 94.250 swarm one operator
offline MapLibre PMTiles Colombia terrain official aeronautical data
UAS human factors fatigue screen exposure multi-UAS workload systematic review
```

Use Tavily for bounded discovery, Brave for independent verification, and Firecrawl only on selected official pages to extract readable Markdown. Store query, tool, filters, result URLs, and reviewer in `query-log.jsonl`.

- [ ] **Step 2: Download and hash the official primary sources**

Save the official RACAE 94 Amendment 2 PDF at the exact path above and verify the known SHA-256. Register RACAE 219 from `https://aaaes.fac.mil.co/sites/aaaes/files/AAAES/documentos/RACAE/2025/racae_219_sistema_de_gestion_de_seguridad_operacional.pdf`. Record retrieval date, publication/amendment/effective dates, media type, license/restriction, and review state.

- [ ] **Step 3: Copy the Obsidian candidate notes without moving them**

Copy these exact vault paths into `SMS/docs/obsidian-imports/`, preserving the original path in front matter:

```text
Private Pilot & UAS School/Reglamentos Aeronáuticos de Colombia RAC 100.md
Private Pilot & UAS School/UAS Notes.md
Research/Drone and Health/rac100_vs_faa_comparison.md
Research/Drone and Health/FAA_vs_RAC100_sUAS_comparison.md
AI Projects/SMS/Components.md
```

Compute checksums before and after copying. Record any amendment mismatch or unsupported claim in `discrepancies.md`; do not silently correct the notes.

- [ ] **Step 4: Run acquisition tests and an offline verification**

Run: `cd SMS && npm test --workspace tools/research -- --run && npm run verify:offline`
Expected: PASS for intact sources; verification fails with a named reason for any checksum mismatch, missing provenance, unsigned package, or changed original.

- [ ] **Step 5: Commit the evidence artifact**

```bash
git add SMS/docs SMS/tools/research
git commit -m "docs(sms-evidence): register Colombian regulatory corpus"
```

### Task 5: Extract, normalize, translate, and review the first safety rules

**Files:**
- Create: `SMS/docs/regulations/extracted/racae_94_enm2.txt`
- Create: `SMS/docs/regulations/normalized/racae94-amendment-2.json`
- Create: `SMS/docs/regulations/normalized/racae219-sms.json`
- Create: `SMS/docs/regulations/normalized/review-record.jsonl`
- Create: `SMS/docs/translations/controlled-terms.json`
- Create: `SMS/tools/research/src/normalize.ts`
- Test: `SMS/tools/research/test/normalize.test.ts`

**Interfaces:**
- `normalizeRequirement(input): NormalizedRequirement`
- `validateRequirementCitations(requirements, register): void`
- `buildControlledTranslation(sourceText, translation, evidence): RequirementTranslation`

- [ ] **Step 1: Create golden normalization tests for the confirmed RACAE 94 controls**

The fixture set must include the exact source locators and Spanish source text for:

```text
94.155 — autonomous mode prohibited; supervised automation may be used with human supervision and intervention capability
94.201(a) — one operator/pilot may not command more than one UAS/RPAS simultaneously
94.250 — swarm operations reserved
94.705 — risk matrix, NASO, telemetry review/preservation and minimum retention
94.710 — emergency response plan requirements
94.715 — fatigue and screen exposure controls
```

Each expected requirement must assert source ID, edition, section, extraction hash, applicability expression, severity, and review state.

- [ ] **Step 2: Run tests to verify normalization is absent or incomplete**

Run: `cd SMS && npm test --workspace tools/research -- normalize.test.ts --run`
Expected: FAIL until extraction and normalized artifacts are present.

- [ ] **Step 3: Extract original PDFs with a reproducible toolchain**

Use `pdftotext -layout` or the approved PDF extraction tool, record extractor version and output checksum, inspect pages containing each rule, and preserve page/paragraph locators. If extraction is ambiguous, mark the evidence unresolved and block promotion rather than guessing.

- [ ] **Step 4: Add bilingual normalized requirements and review records**

Spanish source text is copied or precisely cited; controlled English translation is labelled and reviewed separately. Every interpretation has two reviewer fields: source-language review and operational applicability review. An AI-generated draft is never marked approved without qualified human review.

- [ ] **Step 5: Run normalization, citation, and language-equivalence tests**

Run: `cd SMS && npm test --workspace tools/research -- normalize.test.ts --run && npm run typecheck`
Expected: PASS; every approved requirement has at least one accepted evidence reference, and changing locale does not change requirement IDs or predicates.

- [ ] **Step 6: Commit the reviewed corpus package**

```bash
git add SMS/docs/regulations SMS/docs/translations SMS/tools/research
git commit -m "feat(sms-evidence): normalize reviewed state-aviation rules"
```

### Task 6: Sign, import-test, and publish the first evidence package

**Files:**
- Create: `SMS/packages/evidence/src/manifest.ts`
- Create: `SMS/tools/research/src/package.ts`
- Create: `SMS/docs/provenance/evidence-package-manifest.json`
- Create: `SMS/docs/provenance/evidence-package-manifest.sig`
- Test: `SMS/packages/evidence/test/manifest.test.ts`
- Test: `SMS/tools/research/test/package.test.ts`

**Interfaces:**
- `signManifest(manifest, privateKey): SignedPackageManifest`
- `verifyPackage(directory, manifest, publicKey): VerificationReport`
- `rejectDowngrade(current, incoming): void`

- [ ] **Step 1: Write tamper, expiry, dependency, and downgrade tests**

```ts
it("rejects an altered normalized rule", () => {
  const altered = copyPackageWithChangedFile("racae94-amendment-2.json");
  expect(verifyPackage(altered, manifest, publicKey).ok).toBe(false);
});

it("rejects a package older than the installed version", () => {
  expect(() => rejectDowngrade(installedManifest, olderManifest)).toThrow("downgrade");
});
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `cd SMS && npm test --workspace packages/evidence -- manifest.test.ts --run && npm test --workspace tools/research -- package.test.ts --run`
Expected: FAIL until signing and verification are implemented.

- [ ] **Step 3: Implement Ed25519 signing over canonical manifest JSON**

Sign the manifest plus sorted file-hash list. Store only a key ID and signature in the package; private keys stay on staging hardware. Validate issuer, schema, effective period, geographic scope, dependencies, content hash, signature, and no-downgrade rules before import.

- [ ] **Step 4: Run the full P0 verification**

Run: `cd SMS && npm run typecheck && npm test --workspaces -- --run && npm run verify:offline`
Expected: PASS; a copied package verifies with the public key, while changed, expired, unsigned, partial, or downgraded packages are quarantined.

- [ ] **Step 5: Commit and request qualified corpus review**

```bash
git add SMS/packages/evidence SMS/tools/research SMS/docs/provenance
git commit -m "feat(sms-evidence): sign offline regulatory package"
```

The next gate is qualified FAC/AAAES review of source edition, normalized interpretation, translation, and applicability—not merely passing automated tests.

## P0 Completion Evidence

P0 is complete only when the repository contains the two official primary PDFs, copied Obsidian notes with checksums, research query log, extracted text, reviewed normalized requirements, controlled translations, signed manifest, and a reproducible offline verification report. The signed package becomes the only source of active regulatory rules for P1.
