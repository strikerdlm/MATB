# FAC ISR SMS 0.2.0-rc.1 operator guide

## Release status and authority boundary

`fac-isr-sms@0.2.0-rc.1` is a technical release candidate. A valid signed release-evidence set may state `technicalReady=true`; this means the exact source commit and all three platform candidates passed the technical gates. This RC always remains `operationalReady=false` pending institutional cybersecurity, safety, operational, human-factors, deployment, and data acceptance. Technical readiness is never dispatch authority, aircraft approval, or institutional acceptance.

Before handling a candidate, verify it from `SMS/` with the externally supplied institutional public key and exact source commit:

```bash
npm run verify:technical-release -- \
  --candidate /controlled/incoming/fac-isr-sms-0.2.0-rc.1 \
  --source-commit 0123456789abcdef0123456789abcdef01234567 \
  --public-key /controlled/public/release-verification.pem
```

Do not install if the command fails. The verifier requires the exact Linux tarball, Windows ZIP, Linux/amd64 OCI archive, their platform inventories, current SBOM and scans, fresh clean native/OCI smoke evidence, and a detached signature. It never reads a private key. It reports technical and operational readiness separately.

## Custody and offline boundary

The runtime is offline and has no update downloader. Node 22.23.2 archives and OCI bases are CI build inputs only; CI verifies signed Node checksum metadata before packaging. Transfer candidate artifacts, approved packages, TLS material, export keys, and acceptance records through the institution's controlled removable-media process. Record hashes at dispatch and receipt. Never place private keys, credentials, operational databases, or generated production candidates in the repository.

Use a dedicated receiving node, encrypted storage, synchronized UTC, documented administrators, and a deny-by-default firewall. Keep operational data and research data on separate roots and access-control domains.

## Standalone mode

Standalone mode binds HTTPS only to `127.0.0.1`. It is suitable for one controlled workstation and does not accept tactical-LAN clients.

1. Verify the signed technical release and platform artifact.
2. Install with the native procedure below.
3. Place the server certificate, server private key, and Ed25519 export private key in the platform TLS directory. Set `SMS_DEPLOYMENT_MODE=standalone`, `SMS_BIND_ADDRESS=127.0.0.1`, and a controlled port (default 8443).
4. Bootstrap the first administrator while the service is stopped.
5. Add trust anchors and import/activate approved packages offline.
6. Start the service, then confirm `/healthz` and `/readyz`. A 200 `/readyz` requires `technicalReady=true`; the body still says `operationalReady=false`.

No browser bootstrap exists. Do not expose the standalone listener through port-forwarding or a reverse proxy.

## Tactical-LAN mode

Tactical mode requires mutual TLS. Use a dedicated isolated VLAN with no default route to the Internet, an allowlisted client-certificate issuance process, and receiving-site firewall rules limited to approved operator stations and adapter identities.

Set `SMS_DEPLOYMENT_MODE=tactical`, the approved bind address, `SMS_TLS_CERT_PATH`, `SMS_TLS_KEY_PATH`, and `SMS_TLS_CLIENT_CA_PATH`. The server certificate must cover the tactical DNS name/IP. The client CA is for inbound authentication; do not substitute the server-trust CA. Health clients need their own certificate/key pair and the server CA. Revoke lost clients at the CA/allowlist boundary and restart after controlled configuration changes.

Telemetry ingestion is read-only and certificate allowlisted. No adapter or UI route commands an aircraft. If mTLS, freshness, sequence, mission/aircraft binding, or schema validation fails, treat telemetry as unavailable/degraded and stop relying on it.

## Native Linux installation and lifecycle

Supported host: Ubuntu 24.04 x86-64. Extract the exact production tarball; never rename a TEST-ONLY fixture.

```bash
tar -xzf fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz
sudo ./fac-isr-sms/install/linux/smsctl install --bundle "$PWD/fac-isr-sms"
sudo /opt/fac-isr-sms/current/install/linux/smsctl status
```

Immutable releases are below `/opt/fac-isr-sms`; configuration is below `/etc/fac-isr-sms`; mutable data/packages/backups are below `/var/lib/fac-isr-sms`. The service uses UID/GID 10001 under a hardened systemd unit. Do not change ownership/modes to bypass a failure.

```bash
sudo /opt/fac-isr-sms/current/install/linux/smsctl start
sudo /opt/fac-isr-sms/current/install/linux/smsctl restart
sudo /opt/fac-isr-sms/current/install/linux/smsctl stop
sudo /opt/fac-isr-sms/current/install/linux/smsctl backup
sudo /opt/fac-isr-sms/current/install/linux/smsctl restore --backup /var/lib/fac-isr-sms/backups/<file>.tar
sudo /opt/fac-isr-sms/current/install/linux/smsctl upgrade --bundle "$PWD/fac-isr-sms"
sudo /opt/fac-isr-sms/current/install/linux/smsctl uninstall
```

Uninstall preserves operational data by default. Record and verify a backup before uninstalling immutable/configuration state.

## Native Windows installation and lifecycle

Supported host: Windows 11 or Windows Server 2022+ x86-64. Native Windows requires neither WSL nor Docker. Open Windows PowerShell as Administrator, expand the exact production ZIP, and run:

```powershell
Expand-Archive .\fac-isr-sms-0.2.0-rc.1-win32-x64.zip -DestinationPath .\candidate
$Ctl = ".\candidate\fac-isr-sms\install\windows\SmsCtl.ps1"
& $Ctl Install -BundleRoot ".\candidate\fac-isr-sms"
& $Ctl Status
```

Immutable releases are below `%ProgramFiles%\FAC ISR\SMS`; configuration, data, packages, logs, run state, and backups are below `%ProgramData%\FAC ISR\SMS`. A Scheduled Task runs as Local Service at startup with restart policy. Preserve the Administrators/SYSTEM/Local Service ACL model.

```powershell
& $Ctl Start
& $Ctl Restart
& $Ctl Backup
& $Ctl Restore -BackupPath "C:\ProgramData\FAC ISR\SMS\backups\<file>.zip"
& $Ctl Upgrade -BundleRoot ".\candidate\fac-isr-sms"
& $Ctl Stop
& $Ctl Uninstall
```

If `SmsCtl.ps1` rejects a reparse point, ACL, inventory, TLS key, task, readiness, migration, or rollback check, do not bypass it. Preserve the failure output and retained rollback material for diagnosis.

## OCI appliance

OCI is Linux/amd64 only. It is not the Windows deployment path. Import the verified archive into the approved Linux container engine, then use `docker/compose.edge.yml`. Set controlled absolute `SMS_DATA_DIR`, `SMS_PACKAGE_DIR`, `SMS_TLS_DIR`, `SMS_EXPORT_KEY_ID`, and `SMS_EDGE_PORT` values.

The one-time init/preflight runs with only the capabilities needed to establish UID/GID 10001 ownership and private modes. The permanent process must run as `10001:10001`, with a read-only root filesystem, dropped capabilities, `no-new-privileges`, an internal network, bounded PIDs/tmpfs, read-only package/TLS mounts, and graceful stop. Never run the permanent service as root.

```bash
docker image load --input fac-isr-sms-0.2.0-rc.1-linux-amd64.oci.tar
export SMS_EDGE_IMAGE=fac-isr-sms:0.2.0-rc.1
docker compose -f docker/compose.edge.yml config
docker compose -f docker/compose.edge.yml up init
docker compose -f docker/compose.edge.yml up -d edge
docker compose -f docker/compose.edge.yml ps
docker compose -f docker/compose.edge.yml down
```

Use the exact released image reference shown above, which the controlled archive import provides and Compose also uses by default. Do not permit registry pulls at runtime.

## TLS, release keys, export keys, and trust anchors

- Release signing private keys remain with the institutional release signer and never enter CI or the repository. Verification receives only a public key.
- Node release keyrings are build inputs used to verify official Node 22.23.2 checksum signatures; they are not application trust anchors.
- Server keys and export keys must be regular non-symlink files with service-only read access. Linux/OCI key mode is 0400; configuration is 0640 and private directories are 0700/0750 as installed. On Windows, only Administrators, SYSTEM, and the required Local Service identity may access keys.
- Use different material for server TLS, inbound client CA, outbound health-client identity, export signing, package trust, and release verification. Record key IDs, owners, validity, rotation, revocation, backup, and destruction.
- Never copy secrets through command-line arguments. Use protected files or masked interactive input.

## Offline bootstrap and package activation

Stop the service before administrative mutation. Invoke the bundled `sms-admin` from the current immutable release. The CLI supports `init`; `users create|disable|assign`; `trust add|list`; `packages import|activate|list`; `backup create|verify|restore`; and `diagnose`. It takes an exclusive maintenance lease and fails if the service owns the data.

Bootstrap passwords are read from protected files or explicit masked/piped input, never argv. Add only institutionally verified public trust anchors with the correct scope and algorithm. Import packages from controlled local paths, inspect quarantine/list output, and activate the exact policy/terminology/evidence roles. Activation invalidates stale evaluations and approvals by design.

## Backup, upgrade, and rollback

Before every change, record current release/inventory hashes, service state, `/readyz`, disk space, UTC, active package IDs, audit head, and a verified backup. Copy the backup to separate controlled encrypted media.

The native upgrade transaction stops the old service when it was running, backs up data/packages, stages and verifies immutable content, migrates, switches the pointer, starts, and checks readiness. Any migration/start/readiness failure restores data/packages and the old pointer/service. Do not delete retained rollback material until an accountable reviewer confirms recovery.

To perform an operator-requested rollback, stop the service and use the prior institutionally retained signed candidate plus the backup created immediately before the failed upgrade. Verify both, restore through `smsctl restore`/`SmsCtl.ps1 Restore`, install or upgrade to the prior immutable bundle, start, and verify audit/database/package/readiness state. Never copy SQLite files while writers are active.

## Diagnostics and escalation

Run status, `sms-admin diagnose`, and platform logs without exposing secrets. On Linux use `systemctl status fac-isr-sms` and `journalctl -u fac-isr-sms`; on Windows inspect the FAC ISR SMS Scheduled Task and `%ProgramData%\FAC ISR\SMS\logs`; on OCI use `docker compose ps` and bounded `docker logs` for the owned container.

Classify failures before action: signature/inventory; TLS/ACL/ownership; database integrity/migration/audit; lease/supervision; package trust/evaluation; readiness; resource capacity. Preserve exact timestamps, source commit, artifact hashes, request IDs, sanitized logs, diagnostic output, and rollback paths. Do not include passwords, cookies, CSRF tokens, private keys, personal data, or operational payloads in support bundles.

Stop and escalate when integrity fails, readiness becomes false, safe mode activates, audit verification fails, unexpected network activity appears, a key may be exposed, rollback is incomplete, or telemetry becomes untrusted. The safe response is read-only/non-operational evaluation—not bypassing a guard.

## Known limitations

The authoritative open limitations and closure rules are in [known-limitations.md](release/known-limitations.md) and [operational-readiness-record.json](release/operational-readiness-record.json). For this RC, `operationalReady=false` is mandatory even when a signed release evidence set establishes `technicalReady=true`. Only the existing controlled institutional workflow, qualified human reviewers, and competent release authority can change operational status.
