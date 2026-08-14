# Disaster Recovery v1

EdgeSentinel disaster recovery uses a local, bounded backup bundle under
`data/recovery/backups/dr_<id>/`. Each committed bundle contains:

- `manifest.json`, with relative paths, sizes, SHA-256 values, source roots,
  SQLite consistency metadata, and explicit credential exclusion;
- `manifest.sha256`, which detects accidental or partial manifest changes;
- `files/`, containing only allowlisted project data.

The protected sources are the active zone configuration and its local
backups, SQLite events, evidence, reports, runtime benchmarks, and confirmed
long-term memory. Volatile state, runtime logs, Agent traces/checkpoints, and
everything under `/etc/edgesentinel-visionops` are excluded. DeepSeek keys,
authentication hashes/signing keys, and TLS private keys must be recovered
from their separate root-owned operator process.

## Risk and authority boundary

- `recovery.get_status`: L0, read-only, MCP-visible.
- `recovery.preview_restore`: L0, read-only, MCP-visible.
- `recovery.create_backup`: L1, requires an Agent confirmation and is not
  exposed by the read-only MCP server.
- Applying a restore is not an online Agent tool. It requires an administrator
  on the Jetson host, a fresh preview plan, the exact
  `RESTORE_DISASTER_RECOVERY` phrase, systemd maintenance mode, and sudo.

This boundary prevents a prompt, compromised remote model, or ordinary MCP
client from overwriting the live database.

## Create and verify a backup

Run the acceptance test inside the managed container:

```bash
sudo docker exec edgesentinel-visionops bash -lc \
  'cd /workspace/edgesentinel && bash scripts/run_disaster_recovery_test.sh'
```

For an operator-created backup without the Dashboard:

```bash
sudo docker exec edgesentinel-visionops bash -lc \
  'cd /workspace/edgesentinel && python3 -m apps.disaster_recovery create'
```

Record the returned backup ID and manifest SHA-256 outside the Jetson. A
backup stored only on the same SD card is not disaster recovery; copy the
entire `dr_<id>` directory to a second trusted device using SSH/SCP after the
test passes.

The authenticated Dashboard path has a separate certificate-pinned Windows
acceptance. It verifies the L0 status query, L1 cancellation and confirmation,
invalid and duplicate confirmation rejection, public checkpoint redaction,
credential exclusion, and the MCP read-only boundary:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\check_disaster_recovery_dashboard.ps1 `
  -Username "zja"
```

## Preview a restore

Preview is safe while the service is running:

```bash
sudo docker exec edgesentinel-visionops bash -lc \
  'cd /workspace/edgesentinel && python3 -m apps.disaster_recovery preview \
    --backup-id dr_<32-hex-chars>'
```

The preview re-hashes the manifest and every payload file, rejects extra
payload files and symlinks, compares the backup with current targets, and
returns a `drp_<id>` plan. Any current-file change invalidates that plan.

## Apply a restore

Only use this during a real recovery drill or incident. Keep physical access
and a working SSH session. The script stops EdgeSentinel, starts the container
without the service manager, revalidates the plan, creates a rollback bundle,
atomically overwrites only manifest-listed files, restarts systemd, and runs
the runtime health check.

```bash
bash scripts/restore_disaster_recovery.sh dr_<32-hex-chars>
```

The first exact phrase authorizes entering maintenance mode. After systemd is
stopped, the script generates and displays a new stable `drp_<id>` plan, then
requires a second exact phrase before applying that plan. This avoids treating
a plan as stale merely because stopping SQLite checkpointed its WAL.

The restore is intentionally non-destructive to files that are absent from
the backup. Later evidence files may remain as orphans; they are never deleted
implicitly. A failed restore automatically restores pre-operation files from
`data/recovery/rollbacks/restore_<id>/` before returning an error.

## Production gaps intentionally left explicit

v1 is a local recovery foundation, not an off-device backup scheduler. Before
calling it production-grade, add encrypted off-device replication, retention
and capacity policy for backup bundles, periodic restore drills on a spare SD
card, signed manifests or an operator-controlled HMAC key, and alerting for
backup age or verification failure.

## Authenticated encrypted off-device export v1

The first off-device hardening step uses an operator passphrase stored only in
a root-owned `0600` Jetson credential and independently recorded in a password
manager. Exports use AES-256-CBC with PBKDF2-HMAC-SHA256 (200,000 iterations),
plus an independently derived HMAC-SHA256 over canonical metadata and the full
ciphertext. Verification checks the ciphertext hash and HMAC before decryption,
then validates the decrypted archive and every backup manifest entry in a
temporary directory. Plaintext is not retained by default.

Configure the Jetson credential and create an encrypted artifact:

```bash
bash scripts/configure_recovery_export_key.sh install
bash scripts/export_encrypted_recovery_backup.sh dr_<32-hex-chars>
```

Copy both `.esdr` and `.esdr.json` files to the off-device store. On Windows,
verify them interactively with the independently recorded passphrase:

```powershell
python -m apps.recovery_export verify `
  --artifact .\off-device\dr_<id>.esdr `
  --metadata .\off-device\dr_<id>.esdr.json
```

The passphrase is read without echo and sent to OpenSSL over stdin. It is never
placed in process arguments, JSON metadata, audit output, or the encrypted
artifact filename. Retention scheduling and capacity enforcement remain the
next step; v1 refuses to overwrite an existing encrypted export.

## Windows off-device synchronization and retention v1

`sync_encrypted_recovery_backups.ps1` discovers only strict encrypted metadata
filenames over SSH, downloads each metadata/artifact pair through a private
staging directory, validates its size and SHA-256, refuses conflicting or
incomplete pairs, and records a credential-free JSONL audit. SSH host-key
checking is mandatory. `-BatchMode` supports an independently configured
restricted SSH key without falling back to a password prompt.

The default retention policy keeps five artifacts and at most 2 GiB. It is
preview-only: no local backup is deleted unless both `-ApplyRetention` and the
exact `APPLY_OFF_DEVICE_RETENTION` phrase are supplied. The newest verified
artifact is retained even if it alone exceeds the capacity threshold.

Validate the existing local store without SSH or deletion:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\sync_encrypted_recovery_backups.ps1 `
  -LocalOnly
```

Pull all remote encrypted exports using the existing SSH authentication:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\sync_encrypted_recovery_backups.ps1
```

Add `-VerifyContent` for an interactive passphrase-backed HMAC, decryption,
manifest, SQLite, and per-file verification. For unattended use, configure a
dedicated restricted SSH key first and use `-IdentityFile ... -BatchMode`.

### Dedicated restricted synchronization identity

Generate a non-overwriting Windows Ed25519 machine identity under the current
user's protected LocalAppData directory:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\configure_offdevice_sync_key.ps1 `
  -Action install
```

Copy only the `.pub` file to the Jetson, then install it from the Jetson project
directory. The installer copies a small gate to `/usr/local/libexec` as
`root:root 0755` and adds an OpenSSH `restrict,command=...` entry. That identity
can run only `list` and `read dr_<id>.esdr[.json]`; shell access, writes, PTY,
agent forwarding and port forwarding are denied.

```bash
bash scripts/install_recovery_sync_access.sh install \
  /home/JETSON_USER/edgesentinel-recovery-sync.pub
bash scripts/install_recovery_sync_access.sh status
```

Test the restricted transport from Windows. It uses base64 only as the bounded
SSH transport encoding; confidentiality and integrity still come from the
`.esdr` encryption, HMAC and SHA-256 contract.

```powershell
$key = Join-Path $env:LOCALAPPDATA "EdgeSentinel\recovery-sync\id_ed25519"
powershell -ExecutionPolicy Bypass `
  -File .\scripts\sync_encrypted_recovery_backups.ps1 `
  -IdentityFile $key -BatchMode -RestrictedProtocol
```

### Passwordless scheduled synchronization

After the restricted transport passes interactively, install a per-user
Windows Scheduled Task. It runs daily and again at user logon so a missed
schedule is recovered. The task stores no Windows or SSH password, runs with
limited privileges, refuses overlapping instances, has a 30-minute execution
limit, and never enables retention deletion. Because it uses the protected
per-user identity, it intentionally does not run before that user logs on.

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\manage_offdevice_recovery_sync_task.ps1 `
  -Action install -DailyAt "03:00"

powershell -ExecutionPolicy Bypass `
  -File .\scripts\manage_offdevice_recovery_sync_task.ps1 `
  -Action run

powershell -ExecutionPolicy Bypass `
  -File .\scripts\manage_offdevice_recovery_sync_task.ps1 `
  -Action status
```

The last execution writes a bounded public status record to
`data/recovery/off-device/scheduled-sync-status.json`; successful detailed
syncs remain in `sync-audit.jsonl`. Removal requires the exact
`REMOVE_OFFDEVICE_RECOVERY_SYNC_TASK` confirmation and does not remove the
private key or any downloaded backup.

### Weekly Jetson recovery-point creation (demo profile)

Windows synchronization alone does not create a new recovery point. For this
space-constrained demo, install the Jetson timer so a consistent local backup
and authenticated encrypted export are created every Sunday at 02:00
Asia/Shanghai, with up to five minutes of random delay. The persistent timer
catches up after downtime. Its root-owned
runner validates the managed Docker label and project mount, uses a nonblocking
lock, self-verifies the encrypted artifact, and writes only a credential-free
public status record. Automatic deletion remains disabled.

```bash
bash scripts/install_scheduled_recovery_export.sh
bash scripts/check_scheduled_recovery_export.sh

# First controlled execution
sudo systemctl start edgesentinel-recovery-export.service
bash scripts/check_scheduled_recovery_export.sh
```

The Windows pull remains daily at 03:00. With no new recovery point it compares
metadata and transfers no large artifact. The recovery-point freshness target
is 192 hours (eight days), allowing one day of grace beyond the weekly schedule;
the Windows synchronization status itself remains subject to the 30-hour target.

### Recovery freshness and local alert signal

The scheduled Windows runner now enforces a 192-hour maximum recovery-point age
after each successful pull. Transport success with an old artifact fails the
task. It atomically writes `scheduled-sync-status.json` plus
`recovery-health-alert.json`; the latter is `ACTIVE` on transport, validation,
or freshness failure and `CLEARED` only after a healthy run. No external alert
destination is fabricated: Task Scheduler's nonzero result and the bounded JSON
signal are the supported local integration points.

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\check_offdevice_recovery_health.ps1
```

The health check independently evaluates Windows synchronization age and the
latest Jetson recovery-point age. Existing remote backups are now skipped after
exact validated metadata comparison, so their large encrypted artifacts are
not downloaded again on every daily run.

Preview Jetson capacity and the bounded demo retention policy without deleting
anything. The preview keeps four newest exports within 512 MiB and reports
matching local backup candidates; it never applies deletion:

```bash
bash scripts/preview_recovery_capacity.sh
```

At roughly 20 MiB per weekly export, gross annual growth is about 1 GiB before
retention. Automatic deletion remains disabled until an operator explicitly
authorizes a separately confirmation-gated cleanup workflow.

The cleanup workflow is deliberately manual. Re-run the preview and record its
`rcp_<id>` plan. Applying the plan takes the same exclusive lock as scheduled
export, rejects any inventory change, requires the exact
`DELETE_PREVIEWED_LOCAL_RECOVERY_BACKUPS` phrase, and deletes only Jetson-local
backup directories that are not represented by the retained encrypted export
set. Encrypted Jetson exports and Windows copies are never deleted by it.

```bash
bash scripts/preview_recovery_capacity.sh
bash scripts/cleanup_recovery_capacity.sh rcp_<32-hex-chars>
```

PREPARED and COMPLETED records are appended to the root-owned capacity audit.
No recurring job invokes cleanup.

### Windows Application Event Log integration

An administrator registers the bounded `EdgeSentinel Recovery` Application log
source once. Normal synchronization remains a limited-user task. Event 4101 is
written for each active synchronization or freshness failure; event 4100 is
written only when a prior ACTIVE alert clears, avoiding daily healthy-event
noise. Event 4099 records source installation. Messages contain no credential,
filesystem path, raw tool result, or model content.

```powershell
# Run once from an elevated Windows PowerShell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\manage_offdevice_recovery_event_source.ps1 `
  -Action install

# Normal non-elevated verification
powershell -ExecutionPolicy Bypass `
  -File .\scripts\check_offdevice_recovery_event_log.ps1

powershell -ExecutionPolicy Bypass `
  -File .\scripts\check_offdevice_recovery_health.ps1 `
  -RequireEventLog
```

If no external SIEM or webhook is configured, the Task Scheduler result,
bounded JSON signal, and Windows Application log are the complete local alert
surfaces. External delivery is not claimed or fabricated.

### Isolated off-device restore drill

Cryptographic verification alone does not prove that an operator can restore
the protected files. Run a manual drill from the Windows off-device store at
least every 45 days. The drill reads the passphrase without echo, authenticates
and decrypts the latest `.esdr` into an operating-system temporary directory,
applies the restore to a disposable project, verifies every restored file and
SQLite integrity, and removes all plaintext in a `finally` cleanup. It never
writes the live Windows project or Jetson runtime. Only a bounded, credential-
free status record is retained.

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\run_offdevice_recovery_drill.ps1

powershell -ExecutionPolicy Bypass `
  -File .\scripts\check_offdevice_recovery_drill.ps1
```

`-BackupId dr_<id>` can pin a specific recovery point. `-KeyFile` exists for
controlled test environments; production operators should keep the independent
passphrase in a password manager and use the interactive prompt. A failed or
older-than-45-day status fails the health check. The drill does not authorize
or exercise a production restore.

The daily Windows synchronization task consumes this bounded drill status as
part of the unified recovery health contract. Missing, failed, structurally
invalid, or older-than-45-day drills fail the scheduled task and write Event
Log error 4101 through the installed source. A later healthy synchronization
after a successful drill writes the single recovery event 4100. Healthy daily
runs remain quiet. `check_offdevice_recovery_health.ps1` independently checks
the same drill result rather than trusting only the scheduled-task snapshot.

The same daily task also enforces the demo capacity envelope independently on
the Windows off-device store: at most four verified encrypted backups and 512
MiB. Exceeding either threshold sets `RECOVERY_CAPACITY_EXCEEDED`, returns a
nonzero Scheduled Task result, and writes Event Log 4101. Returning below both
thresholds writes the normal one-time 4100 recovery event. This monitor never
enables or invokes retention deletion.
