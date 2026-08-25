# State-aviation institutional acceptance checklist

## Document control

- Release candidate: `fac-isr-sms@0.2.0-rc.1`
- Technical readiness: independently established by `npm run verify:technical-release`; it is not acceptance.
- Operational readiness: `operationalReady=false` pending all institutional decisions and limitation closure.
- Profile: Colombian state-aviation unarmed ISR/support baseline
- Acceptance status: **NOT OPERATIONALLY APPROVED — institutional reviews pending**
- Machine-readable record: `operational-readiness-record.json`
- Human signature ledger: `verification-signatures.jsonl`
- Automated evidence matrix: `verification-matrix.md`
- Known limitations: `known-limitations.md`

Passing software tests is not institutional, legal, safety, cybersecurity, operational, or command approval. Only named, qualified human reviewers acting within documented authority may sign an acceptance scope. Automation identities are prohibited from the signature ledger. A pending or rejected review, an acceptance with open conditions, an expired review, or an open release-blocking limitation keeps `operationalReady` false.

## Evidence and decision rules

Before recording a decision, each reviewer must:

- [ ] Confirm their identity, organization or unit, role, delegated scope, and any conflict of interest.
- [ ] Review the exact release and immutable evidence hashes listed in their signature record.
- [ ] Record `accept`, `accept-with-conditions`, or `reject`, with an exact UTC signing time and future review or expiry time.
- [ ] State every condition explicitly. Conditional acceptance remains release-blocking until replaced by an unconditional, evidence-backed decision.
- [ ] Stop and record a rejection if the evidence falls outside their competence or delegated authority.

The release authority must confirm that all nine review scopes below are unconditionally accepted, every linked signature and evidence hash validates, every release-blocking limitation is closed, and the independent `--require-ready` verification succeeds before changing operational status.

## Coordinator decision intake procedure

The coordinator must replace the paths and exact UTC values below with controlled paths and coordinator-selected exact UTC times for the review being recorded. Every generation or regeneration must use a new empty output directory; the versioned directory below belongs only to the packet set generated at the example time. Keep reviewer decision input outside the release evidence tree; referenced institutional artifacts must be unclassified and placed below the controlled `docs/release/acceptance-artifacts/` directory.

```bash
npm run acceptance:packets -- --output dist/acceptance-reviewer-packets/2026-08-12T160000000Z --as-of 2026-08-12T16:00:00.000Z
npm run acceptance:record -- --packet dist/acceptance-reviewer-packets/2026-08-12T160000000Z/risk-authority/packet-manifest.json --decision /controlled/intake/risk-authority-decision.json --as-of 2026-08-12T18:00:00.000Z
npm run acceptance:record -- --packet dist/acceptance-reviewer-packets/2026-08-12T160000000Z/risk-authority/packet-manifest.json --decision /controlled/intake/risk-authority-decision.json --as-of 2026-08-12T18:00:00.000Z --apply
npm run acceptance:record -- --recover --as-of 2026-08-12T18:00:00.000Z
```

The first `acceptance:record` command is the mandatory dry run. Review its validation result before using `--apply`. Every required reviewer role records a separate decision, and the coordinator must regenerate the packets after every apply so that later decisions bind to the current acceptance-state fingerprint. Use `--recover` only to resolve an incomplete recorded transaction before any new apply attempt.

Recording a reviewer decision does not close a known limitation and does not set `operationalReady`. Qualification still requires every role-specific decision chain, limitation closure evidence, independent verification, and the competent institutional release authority's decision.

## 1. RACAE interpretation and controlled translation

Required reviewers: qualified FAC regulatory reviewer and designated bilingual legal reviewer.

- [ ] Identify the applicable official Spanish RACAE source, revision, effective date, and institutional authority for this state-aviation profile.
- [ ] Review every software interpretation against the official Spanish source; the Spanish source remains controlling.
- [ ] Validate the controlled terminology and English crosswalk, recording ambiguity, omitted applicability, and unresolved translation gaps.
- [ ] Confirm that software guidance is not presented as legal advice or as a substitute for the competent authority's determination.
- [ ] Hash the reviewed corpus, interpretation register, terminology file, and disposition of every ambiguity.

## 2. Representative operational checklist validation

Required reviewers: operator, remote pilot, maintainer, safety officer, and commander.

- [ ] Execute representative normal, degraded, contingency, and recovery workflows on receiving-site hardware.
- [ ] Validate role hand-offs, maintenance states, stale or malformed telemetry, offline operation, audit retrieval, and safe reversion.
- [ ] Confirm that the console cannot command an aircraft and that no display or alert is treated as a flight-control channel.
- [ ] Exercise day, night, tablet, keyboard, and accessibility workflows with representative users.
- [ ] Record discrepancies, required procedure changes, training impacts, and final participant decisions.

## 3. Active risk matrix and delegated authority

Required reviewers: designated risk authority and commander.

- [ ] Confirm the active institutional risk matrix, acceptance thresholds, delegation instrument, limits of authority, and review dates.
- [ ] Trace each identified hazard and open limitation to controls, verification evidence, residual risk, owner, and decision authority.
- [ ] Verify that the software does not infer risk acceptance from a test pass, a role name, or an expired delegation.
- [ ] Record the exact release scope, operating constraints, conditions, and expiry of any risk decision.

## 4. Emergency-response exercises

Required reviewers: ERP exercise director, safety officer, and commander.

- [ ] Complete a documented tabletop exercise for telemetry loss, incorrect or stale data, database corruption, cybersecurity incident, loss of electrical or network services, fire, injury, and evacuation.
- [ ] Complete functional exercises for notification, escalation, evidence preservation, manual reversion, recovery, and post-event review.
- [ ] Verify contact lists, decision rights, time objectives, log custody, and after-action corrective actions.
- [ ] Close or formally reject every exercise discrepancy before unconditional acceptance.

## 5. Cybersecurity and receiving-node deployment

Required reviewers: institutional cybersecurity reviewer and deployment authority.

- [ ] Verify the transferred bundle and OCI image hashes before loading them on the disconnected receiving node.
- [ ] Review approved vulnerability and malware scans, hardening, least privilege, network isolation, TLS, encrypted storage, backup encryption, restore, logging, and time synchronization.
- [ ] Validate institutional key custody, certificate issuance, removable-media controls, account lifecycle, incident response, and rollback/downgrade prevention.
- [ ] Complete receiving-site security testing, including any required penetration test, and disposition every finding.

## 6. Official map, terrain, obstacle, AIP, and NOTAM data

Required reviewers: qualified geospatial reviewer and operational data authority.

- [ ] Accept separately signed map, terrain, and obstacle packages with source, license, coverage, resolution, datum, effective window, and content hashes.
- [ ] Validate the official AIP and NOTAM acquisition, update, reconciliation, expiry, and audit process.
- [ ] Prove that missing, stale, expired, out-of-coverage, or unverifiable critical data is conspicuous and blocks the affected dispatch or decision.
- [ ] Validate the controlled-exception procedure: only delegated authority may approve a time-bounded exception after documenting alternate official evidence, affected scope, residual risk, conditions, and signatures.
- [ ] Confirm that an exception never fabricates data, suppresses uncertainty, or converts planning context into an official source.

## 7. Human-factors and usability protocol

Required reviewers: human-factors authority and ethics or protocol authority.

- [ ] Approve the protocol, representative users, task set, receiving hardware, environmental conditions, measures, stopping rules, consent, privacy, and adverse-event process.
- [ ] Assess legibility, color and non-color cues, touch targets, keyboard access, screen-reader semantics, workload, alert comprehension, error recovery, and hand-offs.
- [ ] Separate software accessibility conformance evidence from operational usability acceptance.
- [ ] Record protocol deviations and approve the final analysis and corrective-action disposition.

## 8. Research and operational data separation

Required reviewers: research governance reviewer and data-protection reviewer.

- [ ] Confirm that research exports are synthetic or properly deidentified, authorized, auditable, and segregated from operational records.
- [ ] Verify that research outputs, MATB/HRV measures, and exploratory models cannot make dispatch, command, maintenance-release, or risk-acceptance decisions.
- [ ] Approve the protocol or ethics basis, retention, access, withdrawal, export, destruction, and breach procedures before human-subject use.
- [ ] Exercise denial paths for cross-profile access and unauthorized research export.

## 9. Training and safety promotion

Required reviewers: training authority and safety-promotion owner.

- [ ] Approve role-based initial and recurrent training, competency standards, practical evaluation, remediation, and training records.
- [ ] Cover system boundaries, no-C2 constraints, degraded-data behavior, known limitations, emergency response, cybersecurity, privacy, and reporting culture.
- [ ] Validate safety-promotion material, acknowledgement, update ownership, and communication of release changes.
- [ ] Confirm that training completion does not replace role authorization or operational acceptance.

## Final release decision

- [ ] All nine review scopes are unconditionally accepted by qualified, authorized human reviewers.
- [ ] Signature identities, roles, organizations/units, scopes, decisions, UTC times, evidence hashes, conflicts, conditions, and review dates validate.
- [ ] The signature ledger contains no automation identity and no duplicate or unlinked signature.
- [ ] Every release-blocking known limitation is closed with traceable evidence.
- [ ] Automated verification and the disconnected bundle verifier pass for the exact release.
- [ ] `node scripts/verify-operational-readiness.mjs --require-ready` exits successfully.
- [ ] The competent institutional release authority records the final readiness decision outside automation.

Until every final item is complete, this checklist remains pending and the software is limited to controlled development, demonstration, and evaluation use.
