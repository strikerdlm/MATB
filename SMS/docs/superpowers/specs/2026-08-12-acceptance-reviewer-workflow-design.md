# Acceptance Reviewer Packet and Decision Intake Design

**Status:** Approved design

**Date:** 2026-08-12

**Scope:** Colombian State Aviation / FAC ISR acceptance evidence for `fac-isr-sms@0.1.0`

## Context

The release already records nine required institutional review scopes, ten open release-blocking limitations, an empty human signature ledger, and an operational-readiness verifier. It correctly reports `operationalReady=false`. Qualified FAC and competent-authority reviewers—not software or automation—must make the institutional decisions.

The current repository does not prepare scope-specific, hash-locked review packets or safely record reviewer-supplied decisions. Manual edits to both `operational-readiness-record.json` and `verification-signatures.jsonl` would be error-prone and could create contradictory evidence. This feature adds a controlled workflow without manufacturing approval or weakening the existing release gate.

## Goals

1. Generate a deterministic review packet for each required institutional scope.
2. Bind each packet to the exact release, current acceptance state, reviewer roles, checklist section, blockers, and evidence hashes.
3. Validate a completed human decision and its institutional source artifact before any authoritative file changes.
4. Record a valid decision in the append-only signature ledger and link it to the corresponding review scope.
5. Remain fail-closed on malformed, stale, mismatched, duplicated, or partially written evidence.
6. Include the generated reviewer packets and institutional decision artifacts in the disconnected bundle and verify them independently.

## Non-goals

- The software will not sign, approve, reject, or conditionally accept on a reviewer's behalf.
- The software will not verify institutional authority beyond recording the asserted human identity, unit, role, system-of-record reference, and supplied artifact. Institutional identity and delegated authority remain human and receiving-site controls.
- Reviewer public-key infrastructure and cryptographic reviewer signatures are deferred.
- Recording a decision will not close a known limitation, set `operationalReady`, change final qualification, or issue the institutional release decision.
- This work will not begin P7 future operator profiles. P7 remains blocked until the State Aviation baseline is accepted and its change-impact review is documented.

## Architecture

The workflow has three isolated units sharing canonical validation helpers:

1. **Packet generator:** a read-only command that creates review materials under a requested output directory.
2. **Decision validator and recorder:** a dry-run-by-default command that validates reviewer-supplied evidence and, only with `--apply`, records it.
3. **Bundle integration:** the existing offline builder generates packets, copies referenced institutional artifacts, and records their hashes; the standalone verifier validates them without network access.

Generation and mutation remain separate commands. A generated template is structurally distinguishable from a recordable decision and is always rejected by the recorder until a human supplies all required fields and the institutional artifact.

## Components

### Canonical acceptance contracts

A focused module will own:

- the nine allowed review scopes;
- review-status and decision mappings;
- exact UTC, non-empty string, identifier, SHA-256, and contained POSIX path validation;
- canonical JSON serialization and hashing;
- signature-ledger parsing;
- packet and decision schema validation;
- evidence hash verification.

The existing operational-readiness verifier and the new commands will consume these helpers so their rules cannot silently diverge. The refactor must preserve current behavior before new behavior is added.

### Review packet generator

The generator accepts the repository root, an output directory, and a required exact UTC `--as-of` time. By default it creates all nine packets; an optional scope selects one. It never writes under `docs/release` and never edits either authoritative acceptance file.

Each scope directory contains:

- `packet-manifest.json`: canonical machine-readable packet metadata;
- `review-instructions.md`: release, scope, required roles, checklist excerpt, current blockers, evidence inventory, and recording instructions;
- `decision-template.json`: an explicitly unsigned and non-recordable template.

The manifest contains:

- schema version and `recordType: "review-packet"`;
- packet ID equal to the SHA-256 of the canonical manifest payload with the `packetId` field omitted;
- exact release ID and readiness-record ID;
- the exact UTC `asOfUtc` used to evaluate time-dependent blockers;
- review scope, title, required reviewer roles, and current status;
- applicable checklist section;
- the target review's current role coverage and every current release blocker;
- the acceptance-state fingerprint;
- a sorted evidence inventory of repository-relative paths and SHA-256 hashes.

The evidence inventory contains the signed release manifest, detached signature, public key, SBOM, test report, security scan, verification matrix, acceptance checklist, and known-limitations register. The mutable readiness record and signature ledger are excluded from decision evidence because recording the decision necessarily changes them.

The separate acceptance-state fingerprint covers the operational-readiness record, signature ledger, checklist, known-limitations register, verification matrix, and signed release manifest. Identical repository inputs and an identical `asOfUtc` produce byte-identical packets. A decision prepared from an older state is stale after any covered input changes and must be regenerated.

The template contains `recordType: "unsigned-decision-template"`, the packet ID, release ID, and scope. Human decision fields are null or documented placeholders. The recorder categorically rejects this record type.

### Decision validator and recorder

The recorder accepts one completed JSON decision. It validates without writing unless `--apply` is present.

A recordable decision contains:

- `schemaVersion: "1.0"` and `recordType: "institutional-decision"`;
- a unique signature ID, the source packet ID, and either `supersedesSignatureId: null` or the current decision ID for the same scope and required role;
- release ID, scope, and decision (`accept`, `accept-with-conditions`, or `reject`);
- human reviewer identity, organization or unit, and role;
- exact UTC signing and future review/expiry times;
- evidence paths and SHA-256 hashes copied from the packet;
- conflict and condition arrays;
- a nonempty institutional system-of-record identifier;
- a repository-relative institutional artifact path and SHA-256 hash.

The supplied artifact is an exported or scanned institutional decision record, not a software-generated signature. It must already be stored beneath `docs/release/acceptance-artifacts/`, must hash correctly, and must not be the decision JSON or an unsigned template. Only unclassified controlled safety metadata belongs in this repository and bundle.

Validation requires exact agreement between the decision, source packet, release, scope, current acceptance-state fingerprint, and packet evidence inventory. The reviewer's role must exactly match one of the scope's required roles. The packet manifest is archived on apply at `docs/release/acceptance-packets/<packetId>.json`, and the decision links its path and hash so the reviewed state remains auditable after later packets become stale. This is a syntactic consistency check; a competent human release authority remains responsible for confirming identity, authority, competence, and conflicts.

### Required-role coverage and decision history

Each decision attests exactly one required reviewer role. The first decision for a scope and role has `supersedesSignatureId: null`. A later decision for that role must supersede its current decision head; it cannot rewrite or skip history. Every decision remains in the append-only ledger and in the review's `signatureIds` array.

The recorder computes the scope status from the current decision head for every required role:

- `rejected` when any current required-role decision is `reject`, even if other roles remain pending;
- `accepted-with-conditions` when every role is covered, none rejects, and at least one current decision is `accept-with-conditions`;
- `accepted` only when every required role's current decision is an unconditional `accept`.
- `pending` otherwise, including when any required role has no current decision.

The operational-readiness verifier independently rebuilds these decision chains, rejects forks, cycles, cross-scope or cross-role supersession, unlinked decisions, and status mismatches, and checks full required-role coverage. One reviewer decision can never accept a multi-role scope.

### Authoritative updates

On `--apply`, the recorder:

1. obtains an exclusive acceptance-update lock;
2. rereads and revalidates all inputs to prevent a time-of-check/time-of-use mismatch;
3. rejects duplicate signature IDs and any packet that has become stale;
4. creates candidate packet archive, ledger, and readiness-record files in a transaction directory beneath `docs/release`;
5. validates the complete candidate state with the operational-readiness verifier;
6. writes a recovery journal containing the transaction ID and original and candidate hashes;
7. installs the additive packet archive, replaces the ledger and readiness record, then reruns verification;
8. removes the recovery journal only after the committed state validates.

Every error before the journaled commit leaves both authoritative files unchanged. A commit error attempts immediate rollback from the journaled originals. Because a filesystem cannot atomically replace two independent files across a process or power failure, any interrupted or incomplete transaction leaves the journal in place and causes all acceptance verification and subsequent intake to fail closed.

Recovery is an explicit `--recover` operation. If both authoritative files match the candidate hashes, it validates and finalizes the commit. If both match the original hashes, it removes the unused transaction. If they are mixed, it restores and verifies both journaled originals. Any unrecognized hash stops for manual evidence-preserving investigation. A partial transaction can never produce an operational-ready result.

The signature ledger remains append-only. The matching review appends the new signature ID, preserves prior linkage as history, and receives the status derived from all current required-role decision heads.

Neither the recorder nor recovery logic changes known-limitation status, readiness, qualification, record status, or the final readiness decision.

## Data Flow

1. A release coordinator runs packet generation for the current repository state.
2. The coordinator supplies the relevant packet to qualified institutional reviewers.
3. Each required role completes human review in the institution's authorized process and produces a system-of-record entry plus an exported decision artifact.
4. The artifact is placed in the controlled acceptance-artifact directory, and the completed decision JSON references its immutable hash and system-of-record identifier.
5. The coordinator runs the recorder without `--apply` and resolves every validation failure.
6. The coordinator reruns with `--apply`; the command records and links the decision under the crash-consistent transaction protocol.
7. The operational-readiness verifier reconstructs role coverage and reports the updated review state. Conditional acceptance, rejection, missing role decisions, and open limitations remain blockers.
8. Packets for subsequent decisions are regenerated because the acceptance-state fingerprint changed.
9. The offline builder includes current packets and every artifact referenced by the ledger. The standalone verifier validates their paths, hashes, state binding, and decision linkage.

## Failure Behavior

The workflow rejects, without authoritative changes:

- automated or incomplete identities;
- unsigned templates or unknown record types;
- unknown scopes, roles, decisions, or statuses;
- duplicate signature IDs;
- decision-history forks, cycles, skipped heads, or cross-scope/cross-role supersession;
- release, record, scope, packet, or evidence mismatches;
- stale acceptance-state fingerprints;
- malformed, future signing, expired review, or non-increasing UTC times;
- missing conflicts or conditions arrays;
- conditional acceptance without conditions or unconditional acceptance with conditions;
- empty or malformed system-of-record references;
- missing artifacts, hash mismatches, disallowed locations, absolute paths, traversal, backslashes, or symlink escapes;
- a changed input after initial validation;
- an active or inconsistent recovery journal.

Valid `accept-with-conditions` and `reject` decisions may be recorded because they are truthful institutional outcomes, but both remain release-blocking. An unconditional acceptance also remains insufficient while any other review or release-blocking limitation is unresolved.

## Offline Bundle Behavior

The bundle builder generates current reviewer packets with its fixed `builtAtUtc` into `reports/acceptance/reviewer-packets/`, copies ledger-referenced historical packet manifests and institutional artifacts into `reports/acceptance/recorded-decisions/`, and adds a sorted acceptance-workflow inventory to the bundle manifest. The inventory binds packet IDs, scope, acceptance-state fingerprint, decision-chain heads, role coverage, artifact destination, and SHA-256 hashes.

The standalone verifier checks packet structure and determinism, evidence hashes, artifact hashes, ledger linkage, manifest agreement, and absence of an incomplete transaction. It warns rather than overclaims when reviews or limitations remain blocking. It requires no network access and no reviewer PKI.

## Testing Strategy

Tests are added before implementation and use temporary repositories and fixture artifacts. They prove:

1. Packet output is deterministic, complete for all nine scopes, scope-selectable, and read-only with respect to authoritative files.
2. Packets bind the exact release, roles, checklist section, blockers, state fingerprint, and sorted evidence inventory.
3. Unsigned templates cannot be recorded.
4. Dry-run validation never writes.
5. Valid fixture decisions record append-only history, and a scope becomes accepted only after every required role has a current unconditional acceptance.
6. Automation identities, duplicates, decision-chain faults, hash mismatches, path and symlink escapes, stale packets, invalid dates, roles, releases, scopes, conditions, and record types fail without partial writes.
7. Injected failures before and during commit either preserve the original state or leave a journal that blocks verification and can be recovered deterministically.
8. Missing-role, conditional, and rejected decisions remain blockers.
9. Accepted decisions cannot close limitations, set `operationalReady`, or issue a readiness decision.
10. The offline bundle contains and independently validates packets and referenced artifacts.
11. Existing operational-readiness, offline, no-C2, data-separation, security, typecheck, lint, and full release gates remain green.

The real repository remains at zero signatures and `operationalReady=false`; only temporary fixtures exercise successful decision recording.

## Completion Criteria

- All nine deterministic packets can be generated from the real blocked release.
- A fixture human decision passes dry-run and apply tests through the complete transaction path.
- Invalid or interrupted updates cannot yield a false acceptance state.
- The disconnected bundle independently verifies current packets and decision artifacts.
- No test or command fabricates a real reviewer identity, institutional artifact, limitation closure, or operational approval.
- The existing release gates pass for the exact committed source.

## Deferred Work

- Institution-managed reviewer keys, trust anchors, revocation, and cryptographic signature verification.
- Integration with a specific institutional records-management API.
- Final limitation closure and `operationalReady=true`, which require the nine qualified reviews, closure evidence for all ten release-blocking limitations, and the competent institutional release authority's decision.
