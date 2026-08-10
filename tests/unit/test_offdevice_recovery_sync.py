import os
import unittest


class OffDeviceRecoverySyncScriptTests(unittest.TestCase):
    def test_sync_is_strict_paired_bounded_and_confirmation_gated(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        path = os.path.join(
            root,
            "scripts",
            "sync_encrypted_recovery_backups.ps1",
        )
        with open(path, "r", encoding="utf-8") as input_file:
            script = input_file.read()

        self.assertIn("StrictHostKeyChecking=yes", script)
        self.assertIn("BatchMode=yes", script)
        self.assertIn("^dr_[0-9a-f]{32}", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn("SHA256", script)
        self.assertIn("Get-ArtifactRecord", script)
        self.assertIn("incomplete encrypted pair", script)
        self.assertIn("FileMode]::CreateNew", script)
        self.assertIn(".ToArray()", script)
        self.assertIn("$LockAcquired", script)
        self.assertIn("Open-SyncLock", script)
        self.assertIn("sync lock cannot be a reparse point", script)
        self.assertIn('"-n"', script)
        self.assertIn("Assert-TrustedStorePath", script)
        self.assertIn("cannot traverse a reparse point", script)
        self.assertIn("APPLY_OFF_DEVICE_RETENTION", script)
        self.assertIn("[switch]$LocalOnly", script)
        self.assertIn("[switch]$VerifyContent", script)
        self.assertIn("[switch]$RestrictedProtocol", script)
        self.assertIn("Invoke-RestrictedDownload", script)
        self.assertIn("Assert-RecoveryMetadataContract", script)
        self.assertIn("artifact_downloads", script)
        self.assertIn("StagedMetadataHash", script)
        self.assertIn('"RESTRICTED_SSH"', script)
        self.assertIn("apps.recovery_export verify", script)
        self.assertIn("sync-audit.jsonl", script)
        self.assertIn("credentials_included = $false", script)
        self.assertIn("plaintext_persisted = $false", script)
        self.assertNotIn("StrictHostKeyChecking=no", script)
        self.assertNotIn("UserKnownHostsFile=/dev/null", script)
        self.assertIn("ConnectTimeout=15", script)
        self.assertIn("ServerAliveCountMax=2", script)

    def test_restricted_ssh_access_is_forced_read_only_and_root_owned(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        gate_path = os.path.join(root, "scripts", "recovery_export_ssh_gate.sh")
        install_path = os.path.join(
            root, "scripts", "install_recovery_sync_access.sh"
        )
        key_path = os.path.join(
            root, "scripts", "configure_offdevice_sync_key.ps1"
        )
        with open(gate_path, "r", encoding="utf-8") as input_file:
            gate = input_file.read()
        with open(install_path, "r", encoding="utf-8") as input_file:
            installer = input_file.read()
        with open(key_path, "r", encoding="utf-8") as input_file:
            key_script = input_file.read()

        self.assertIn("SSH_ORIGINAL_COMMAND", gate)
        self.assertIn("^dr_[0-9a-f]{32}", gate)
        self.assertIn('exec base64 -w 0 -- "$path"', gate)
        self.assertNotIn("eval", gate)
        self.assertIn('restrict,command="%s"', installer)
        self.assertIn("sudo install -o root -g root -m 0755", installer)
        self.assertIn("REMOVE_RECOVERY_SYNC_ACCESS", installer)
        self.assertIn('ssh-ed25519\\ [A-Za-z0-9+/=]+', installer)
        self.assertIn("ssh-keygen -q -t ed25519 -N '\"\"'", key_script)
        self.assertIn("Windows PowerShell 5.1", key_script)
        self.assertIn('icacls $PrivateKey /inheritance:r /grant:r', key_script)
        self.assertIn("Remove-GeneratedIdentity", key_script)
        self.assertIn("S-1-5-32-544", key_script)
        self.assertIn("private key ACL is too broad", key_script)
        self.assertIn("refusing to overwrite", key_script)

    def test_scheduled_sync_is_non_destructive_bounded_and_passwordless(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        runner_path = os.path.join(
            root, "scripts", "run_offdevice_recovery_sync_task.ps1"
        )
        manager_path = os.path.join(
            root, "scripts", "manage_offdevice_recovery_sync_task.ps1"
        )
        with open(runner_path, "r", encoding="utf-8") as input_file:
            runner = input_file.read()
        with open(manager_path, "r", encoding="utf-8") as input_file:
            manager = input_file.read()

        self.assertIn("BatchMode = $true", runner)
        self.assertIn("RestrictedProtocol = $true", runner)
        self.assertIn('retention_applied = $false', runner)
        self.assertIn("MaximumBackupAgeHours", runner)
        self.assertIn("192.0", runner)
        self.assertIn("latest_backup_age_hours", runner)
        self.assertIn("MaximumDrillAgeDays", runner)
        self.assertIn("MaximumEncryptedBackups", runner)
        self.assertIn("MaximumEncryptedBytes", runner)
        self.assertIn("RECOVERY_CAPACITY_EXCEEDED", runner)
        self.assertIn("encrypted_backup_count", runner)
        self.assertIn("536870912", runner)
        self.assertIn("latest_drill_age_days", runner)
        self.assertIn("RESTORE_DRILL_INVALID", runner)
        self.assertIn("recovery-health-alert.json", runner)
        self.assertIn("Write-EventLog", runner)
        self.assertIn("4100", runner)
        self.assertIn("4101", runner)
        self.assertIn("EVENT_SOURCE_NOT_INSTALLED", runner)
        self.assertNotIn("-ApplyRetention", runner)
        self.assertIn("scheduled-sync-status.json", runner)
        self.assertIn("Assert-SafeStatusPath", runner)
        self.assertIn("ExecutionTimeLimit", manager)
        self.assertIn('MultipleInstances = "IgnoreNew"', manager)
        self.assertIn("StartWhenAvailable", manager)
        self.assertIn('LogonType = "Interactive"', manager)
        self.assertIn('RunLevel = "Limited"', manager)
        self.assertIn("TaskAccount.Translate", manager)
        self.assertIn("NOT_YET_RUN (267011)", manager)
        self.assertIn("STOPPED_OR_REQUEST_REFUSED", manager)
        self.assertIn("Windows password stored: False", manager)
        self.assertIn("Runs before user logon: False", manager)
        self.assertIn("Task registered: False", manager)
        self.assertIn("[switch]$Preview", manager)
        self.assertIn("REMOVE_OFFDEVICE_RECOVERY_SYNC_TASK", manager)
        self.assertIn("refusing to overwrite", manager)
        self.assertIn("Encrypted backup count:", manager)

    def test_recovery_health_check_distinguishes_sync_and_backup_age(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        path = os.path.join(
            root, "scripts", "check_offdevice_recovery_health.ps1"
        )
        with open(path, "r", encoding="utf-8") as input_file:
            script = input_file.read()
        self.assertIn("MaximumSyncAgeHours", script)
        self.assertIn("MaximumBackupAgeHours", script)
        self.assertIn("192.0", script)
        self.assertIn("MaximumDrillAgeDays", script)
        self.assertIn("MaximumEncryptedBackups", script)
        self.assertIn("MaximumEncryptedBytes", script)
        self.assertIn("RECOVERY_CAPACITY_COUNT_EXCEEDED", script)
        self.assertIn("RECOVERY_CAPACITY_BYTES_EXCEEDED", script)
        self.assertIn("536870912", script)
        self.assertIn("SYNC_STATUS_STALE", script)
        self.assertIn("RECOVERY_POINT_STALE", script)
        self.assertIn("RESTORE_DRILL_STALE", script)
        self.assertIn("RESTORE_DRILL_VERIFICATION_INVALID", script)
        self.assertIn("RECOVERY_ALERT_ACTIVE", script)
        self.assertIn("SCHEDULED_TASK_LAST_RUN_FAILED", script)
        self.assertIn("EVENT_LOG_SOURCE_UNAVAILABLE", script)
        self.assertIn("EVENT_LOG_DELIVERY_FAILED", script)
        self.assertIn("Credentials exposed: False", script)

    def test_event_source_management_requires_elevation_and_is_bounded(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        manager_path = os.path.join(
            root, "scripts", "manage_offdevice_recovery_event_source.ps1"
        )
        check_path = os.path.join(
            root, "scripts", "check_offdevice_recovery_event_log.ps1"
        )
        with open(manager_path, "r", encoding="utf-8") as input_file:
            manager = input_file.read()
        with open(check_path, "r", encoding="utf-8") as input_file:
            check = input_file.read()
        self.assertIn("New-EventLog", manager)
        self.assertIn("Write-EventLog", manager)
        self.assertIn("requires an elevated PowerShell", manager)
        self.assertIn("REMOVE_OFFDEVICE_RECOVERY_EVENT_SOURCE", manager)
        self.assertIn("refusing to overwrite", manager)
        self.assertIn("Event IDs: 4099 install, 4100 cleared, 4101 active", manager)
        self.assertIn("Get-WinEvent", check)
        self.assertIn("Limit must be between 1 and 100", check)

    def test_restore_drill_is_isolated_verified_and_freshness_checked(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        run_path = os.path.join(
            root, "scripts", "run_offdevice_recovery_drill.ps1"
        )
        check_path = os.path.join(
            root, "scripts", "check_offdevice_recovery_drill.ps1"
        )
        with open(run_path, "r", encoding="utf-8") as input_file:
            run = input_file.read()
        with open(check_path, "r", encoding="utf-8") as input_file:
            check = input_file.read()
        self.assertIn('"drill"', run)
        self.assertIn("ISOLATED_RESTORE_DRILL", run)
        self.assertIn("production_modified = $false", run)
        self.assertIn("plaintext_persisted = $false", run)
        self.assertIn("restore-drill-status.json", run)
        self.assertIn("MaximumDrillAgeDays", check)
        self.assertIn("RESTORE_DRILL_STALE", check)
        self.assertIn("LAST_RESTORE_DRILL_FAILED", check)
        self.assertIn("Credentials exposed: False", check)


if __name__ == "__main__":
    unittest.main()
