# Future Operator Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not activate either future profile until the State Aviation baseline is institutionally accepted and the current RAC 100 evidence has been reviewed.

**Goal:** Add the future profiles in the approved order—Private Certified Operator under current RAC 100, then Civil Public Entity—without changing the deterministic safety kernel or allowing a mission to switch profiles after approval.

**Architecture:** Profiles are signed policy/evidence packages that supply authority hierarchy, terminology, applicability predicates, roles, checklists, risk authorities, data requirements, and export rules. The same kernel evaluates each profile; profile-specific differences remain data/configuration, not duplicated decision logic. A mission is permanently tied to its profile and must be cloned into a new mission to change profile.

**Tech Stack:** TypeScript strict; `@fac-isr/evidence`; `@fac-isr/safety-kernel`; Zod; Vitest; Playwright; signed Ed25519 policy packages.

## Global Constraints

- State Aviation/FAC remains the first and active profile during initial delivery.
- Private Certified Operator is second and uses the current qualified RAC 100 corpus from P0; no stale local note may be promoted over an official source.
- Civil Public Entity is third and uses its current applicable RAC 100/public-entity provisions and competent-authority coordination evidence.
- A profile change after first approval requires cloning; no mission may mutate profile in place.
- Profile policy packages cannot weaken a higher-ranked binding requirement or remove the no-C2, no-classified-content, no-armed-operational-scope, or evidence-traceability constraints.
- A missing or unreviewed profile package blocks mission readiness.

## File Map

- Create: `SMS/packages/profiles/package.json`
- Create: `SMS/packages/profiles/src/types.ts`
- Create: `SMS/packages/profiles/src/registry.ts`
- Create: `SMS/packages/profiles/src/clone.ts`
- Create: `SMS/packages/profiles/src/private-certified.ts`
- Create: `SMS/packages/profiles/src/civil-public.ts`
- Create: `SMS/packages/profiles/src/index.ts`
- Create: `SMS/docs/profiles/private-certified/requirements.json`
- Create: `SMS/docs/profiles/private-certified/review-record.jsonl`
- Create: `SMS/docs/profiles/civil-public/requirements.json`
- Create: `SMS/docs/profiles/civil-public/review-record.jsonl`
- Test: `SMS/packages/profiles/test/*.test.ts`
- Test: `SMS/apps/console/test/ProfileSelection.test.tsx`

## Interfaces

```ts
export interface OperatorProfile {
  id: "fac-state-aviation" | "private-certified" | "civil-public";
  displayNameEs: string;
  displayNameEn: string;
  authoritySources: readonly string[];
  policyPackageId: string;
  terminologyPackageId: string;
  roleModelVersion: string;
  requiredEvidence: readonly string[];
  status: "draft" | "qualified-review" | "approved" | "retired";
}

export interface ProfileCloneResult {
  sourceMissionId: string;
  newMissionId: string;
  sourceProfileId: string;
  targetProfileId: string;
  state: "Draft";
  copiedFields: readonly string[];
  excludedApprovals: readonly string[];
  excludedExceptions: readonly string[];
}
```

### Task 1: Add profile registry and immutable profile binding

**Files:**
- Create: `SMS/packages/profiles/package.json`
- Create: `SMS/packages/profiles/src/types.ts`
- Create: `SMS/packages/profiles/src/registry.ts`
- Create: `SMS/packages/profiles/src/clone.ts`
- Test: `SMS/packages/profiles/test/registry.test.ts`
- Test: `SMS/packages/profiles/test/clone.test.ts`

**Interfaces:**
- `getProfile(profileId): OperatorProfile`
- `bindProfile(mission, profile): MissionRevision`
- `cloneMissionToProfile(mission, targetProfile): ProfileCloneResult`

- [ ] **Step 1: Write profile-binding and clone tests**

```ts
it("does not permit an approved mission to switch profile in place", () => {
  expect(() => bindProfile(approvedFacMission, privateProfile)).toThrow("clone");
});

it("clones a mission as Draft and excludes approvals and exceptions", () => {
  const result = cloneMissionToProfile(approvedFacMission, privateProfile);
  expect(result.state).toBe("Draft");
  expect(result.excludedApprovals.length).toBeGreaterThan(0);
  expect(result.excludedExceptions.length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Run tests to verify missing registry fails**

Run: `cd SMS && npm test --workspace packages/profiles -- registry.test.ts clone.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement signed registry and clone semantics**

Require an approved profile package, source/policy/terminology IDs, review state, and effective period. Preserve route/fleet draft data only when schema-compatible; clear gate approvals, exceptions, safety acceptance, command authorization, and profile-specific evidence.

- [ ] **Step 4: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/profiles -- registry.test.ts clone.test.ts --run`
Expected: PASS.

```bash
git add SMS/packages/profiles
git commit -m "feat(profiles): bind missions to immutable operator profiles"
```

### Task 2: Normalize and review the Private Certified Operator RAC 100 profile

**Files:**
- Create: `SMS/packages/profiles/src/private-certified.ts`
- Create: `SMS/docs/profiles/private-certified/requirements.json`
- Create: `SMS/docs/profiles/private-certified/review-record.jsonl`
- Test: `SMS/packages/profiles/test/private-certified.test.ts`

**Interfaces:**
- `buildPrivateCertifiedProfile(evidencePackage): OperatorProfile`
- `privateCertifiedApplicability(mission, requirements): RuleEvaluation[]`

- [ ] **Step 1: Acquire current official RAC 100 and related Aerocivil sources in P0**

Use the official Aerocivil RAC collection and resolutions pages, direct official documents, and independent Tavily/Brave/Firecrawl discovery. Record source edition, effective date, checksum, authority rank, and discrepancies against Obsidian notes. Do not use a search-result snippet as evidence.

- [ ] **Step 2: Write profile-specific golden tests from reviewed requirements**

Cover operator certification, registration, aircraft/operation class, VFR/VLOS/BVLOS/IFR applicability, airspace/coordination, maintenance, records, emergency, occurrence, privacy, and export requirements only where the reviewed RAC 100 evidence says they apply.

- [ ] **Step 3: Run tests to verify the profile is not activated prematurely**

Run: `cd SMS && npm test --workspace packages/profiles -- private-certified.test.ts --run`
Expected: FAIL or remain blocked while the profile package is draft/unreviewed.

- [ ] **Step 4: Implement profile data and controlled translations**

Supply rules, roles, terminology, evidence requirements, risk authorities, checklist references, and export labels as signed data. Reuse P1 predicates; do not fork evaluator logic.

- [ ] **Step 5: Run reviewed-profile tests and commit**

Run: `cd SMS && npm test --workspace packages/profiles -- private-certified.test.ts --run`
Expected: PASS only after qualified review records are present; a stale/unsigned profile remains blocked.

```bash
git add SMS/packages/profiles/src/private-certified.ts SMS/docs/profiles/private-certified SMS/packages/profiles/test/private-certified.test.ts
git commit -m "feat(profiles): add reviewed private certified operator profile"
```

### Task 3: Normalize and review the Civil Public Entity profile

**Files:**
- Create: `SMS/packages/profiles/src/civil-public.ts`
- Create: `SMS/docs/profiles/civil-public/requirements.json`
- Create: `SMS/docs/profiles/civil-public/review-record.jsonl`
- Test: `SMS/packages/profiles/test/civil-public.test.ts`

**Interfaces:**
- `buildCivilPublicProfile(evidencePackage): OperatorProfile`
- `civilPublicApplicability(mission, requirements): RuleEvaluation[]`

- [ ] **Step 1: Acquire and register current public-entity evidence**

Use current official RAC 100/public-entity provisions, competent-authority coordination material, and applicable Aerocivil/AAAES sources. Record the exact public-purpose authority and scope; do not infer a public-entity exemption from organizational identity.

- [ ] **Step 2: Write profile-specific golden tests**

Cover public-entity mission authority, aircraft/crew/airspace/maintenance/records/emergency/occurrence requirements, and any special coordination evidence. Include negative tests proving that a public label cannot bypass missing authorization or risk acceptance.

- [ ] **Step 3: Run tests to verify draft profile remains blocked**

Run: `cd SMS && npm test --workspace packages/profiles -- civil-public.test.ts --run`
Expected: FAIL or remain blocked until qualified review is recorded.

- [ ] **Step 4: Implement profile data and controlled translations**

Keep all profile behavior in reviewed data packages and shared kernel predicates. Store source language and controlled translation separately.

- [ ] **Step 5: Run reviewed-profile tests and commit**

Run: `cd SMS && npm test --workspace packages/profiles -- civil-public.test.ts --run`
Expected: PASS only after review and signatures.

```bash
git add SMS/packages/profiles/src/civil-public.ts SMS/docs/profiles/civil-public SMS/packages/profiles/test/civil-public.test.ts
git commit -m "feat(profiles): add reviewed civil public entity profile"
```

### Task 4: Add profile selection and cross-profile verification to the console

**Files:**
- Create: `SMS/apps/console/src/components/ProfileSelection.tsx`
- Create: `SMS/apps/console/src/components/ProfileBadge.tsx`
- Test: `SMS/apps/console/test/ProfileSelection.test.tsx`
- Test: `SMS/packages/profiles/test/cross-profile.test.ts`

**Interfaces:**
- `ProfileSelection({ available, onSelect }): JSX.Element`
- `ProfileBadge({ profile }): JSX.Element`

- [ ] **Step 1: Write selection and cross-profile tests**

```tsx
it("shows profiles in the approved order and marks unapproved profiles unavailable", () => {
  render(<ProfileSelection available={fixtures} onSelect={vi.fn()} />);
  expect(screen.getAllByRole("option").map((node) => node.textContent)).toEqual([
    expect.stringContaining("State Aviation"),
    expect.stringContaining("Private Certified"),
    expect.stringContaining("Civil Public"),
  ]);
});
```

- [ ] **Step 2: Run tests to verify missing selector fails**

Run: `cd SMS && npm test --workspace apps/console -- ProfileSelection.test.tsx --run`
Expected: FAIL.

- [ ] **Step 3: Implement explicit profile binding and clone flow**

Show active profile, source/policy package, status, effective period, and review state in the Mission Safety Strip and mission creation flow. Selecting an unapproved profile explains the blocker; changing an approved mission offers clone-to-new-profile only.

- [ ] **Step 4: Run cross-profile equivalence tests**

Run: `cd SMS && npm test --workspace packages/profiles -- cross-profile.test.ts --run && npm test --workspace apps/console -- ProfileSelection.test.tsx --run`
Expected: PASS; profile changes alter documented applicability/roles, not kernel determinism or safety boundary constraints.

- [ ] **Step 5: Commit**

```bash
git add SMS/apps/console/src/components/ProfileSelection.tsx SMS/apps/console/src/components/ProfileBadge.tsx SMS/apps/console/test SMS/packages/profiles/test/cross-profile.test.ts
git commit -m "feat(console): add reviewed operator profile selection"
```

## P7 Completion Evidence

P7 is complete only when current official profile corpora are reviewed and signed, profile-specific golden cases pass, approved missions cannot switch profiles in place, cloning clears approvals/exceptions, the console displays profile provenance, and State Aviation constraints continue to apply at the kernel boundary.
