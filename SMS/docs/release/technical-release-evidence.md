# 0.2.0-rc.1 technical release evidence procedure

Technical release evidence is generated for one exact source commit by the Ubuntu 24.04 and Windows Server 2022 jobs in `sms-ci.yml`. Those jobs build the production artifacts only after verifying official Node 22.23.2 signed checksum metadata with an immutable official Node release-keyring file and pinned official signer fingerprints. A dependent Ubuntu job downloads both gated candidate sets before creating the SBOM and dependency-scan record, so those records bind all three artifacts rather than whichever artifact happened to exist on one runner.

The candidate contains exactly:

- `fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz` and `inventories/linux-x64.json`;
- `fac-isr-sms-0.2.0-rc.1-win32-x64.zip` and `inventories/win32-x64.json`;
- `fac-isr-sms-0.2.0-rc.1-linux-amd64.oci.tar` and `inventories/linux-amd64-oci.json`;
- a current CycloneDX SBOM; dependency, OCI, and malware scan attestations; clean Linux native, Windows native, and OCI smoke attestations; and clean Ubuntu/Windows CI attestations.

Every inventory/evidence record carries the same exact source commit, a current UTC timestamp, and exact relevant artifact hashes. Every scan record also names a candidate-contained raw scanner-output path, its SHA-256, its enforced threshold, and zero findings at or above that threshold. The signed manifest repeats the evidence and raw-output paths and hashes. Dependency scanning uses native npm-audit JSON, OCI scanning uses native Grype JSON with no High/Critical match, and approved malware evidence uses normalized JSON with `malwareFound: 0`, `errors: 0`, and the exact three-artifact hash map. The manifest states `technicalReady=true` and `operationalReady=false`.

## External signing handoff

1. Download the Ubuntu candidate, Windows candidate, and cross-platform scan-evidence artifacts from the same successful `sms-ci.yml` run. The run must be a trusted `push` on `main`, originate in this repository, have the exact release source SHA, and be completed successfully. A pull-request, fork, alternate workflow, branch, SHA, incomplete run, or failed run is rejected.
2. Add the approved malware-scan evidence and raw normalized scanner output for all three candidate artifacts. Both files must carry the exact artifact hash map; the evidence must hash-lock the raw output and declare `threshold: "zero-malware"` and zero findings.
3. Assemble the unsigned manifest:

   ```bash
   npm run release:evidence -- assemble \
     --candidate /controlled/candidate \
     --source-commit <40-hex-commit> \
     --output /controlled/candidate/release-evidence.json
   ```

4. Transfer the exact manifest bytes to the authorized institutional Ed25519 signing service. The private key must never enter the repository, CI variables, or a runner.
5. Return only the detached base64 signature and approved public verification material. Verify them on an independent receiving host.
6. Populate the protected `sms-release` environment with base64-encoded `SMS_RELEASE_MANIFEST_B64`, `SMS_RELEASE_SIGNATURE_B64`, `SMS_RELEASE_PUBLIC_KEY_B64`, `SMS_MALWARE_SCAN_EVIDENCE_B64`, and `SMS_MALWARE_SCAN_OUTPUT_B64`. Supply an optional workflow run ID only as decimal digits; the workflow still verifies the run identity and provenance.
7. Run the tag/manual `sms-release.yml` workflow for the same exact commit/CI run. It verifies before creating `release-output`; failure produces no published candidate.

TEST-ONLY fixtures use the explicit `--test-only-fixture` boundary, TEST-ONLY artifact/release names, `production:false`, and `controlled-test-fixture` provenance. They test cryptographic/error behavior only and can never satisfy the production verifier.

`npm run verify:operational -- --require-ready` is separate and intentionally exits nonzero for this RC while institutional reviews and limitations remain open.
