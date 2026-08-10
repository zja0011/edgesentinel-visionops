import os
import unittest


class ScheduledRecoveryExportScriptTests(unittest.TestCase):
    def setUp(self):
        self.root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

    def read(self, *parts):
        with open(os.path.join(self.root, *parts), "r", encoding="utf-8") as source:
            return source.read()

    def test_runner_is_locked_verified_and_secret_safe(self):
        script = self.read("scripts", "run_scheduled_recovery_export.sh")
        self.assertIn("flock -n", script)
        self.assertIn("com.edgesentinel.managed", script)
        self.assertIn("apps.disaster_recovery create", script)
        self.assertIn("apps.recovery_export create", script)
        self.assertIn("apps.recovery_export verify", script)
        self.assertIn('cd "$project_dir"', script)
        self.assertIn('pipeline_stage="BACKUP_CREATED"', script)
        self.assertIn('pipeline_stage="VERIFIED"', script)
        self.assertIn('sqlite_consistent="true"', script)
        self.assertIn("bash -c", script)
        self.assertNotIn("bash -lc", script)
        self.assertIn("root:root 600", script)
        self.assertIn('credentials_included": False', script)
        self.assertIn('plaintext_persisted": False', script)
        self.assertNotIn("print(secret", script)
        self.assertNotIn("rm -rf", script)

    def test_systemd_timer_is_persistent_and_hardened(self):
        service = self.read("deploy", "edgesentinel-recovery-export.service")
        timer = self.read("deploy", "edgesentinel-recovery-export.timer")
        installer = self.read("scripts", "install_scheduled_recovery_export.sh")
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("WorkingDirectory=/home/nvidia/projects/edgesentinel-visionops", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ProtectHome=read-only", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", service)
        self.assertIn("TimeoutStartSec=1800", service)
        self.assertIn("Sun *-*-* 02:00:00 Asia/Shanghai", timer)
        self.assertIn("RandomizedDelaySec=300", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("systemd-analyze verify", installer)
        self.assertIn("edgesentinel-scheduled-recovery-export", installer)
        self.assertIn("sed", installer)
        self.assertIn("scheduled-recovery-export\\$#ExecStart=", installer)
        self.assertIn('chmod 0755 "$temporary/edgesentinel-scheduled-recovery-export"', installer)
        self.assertIn("enable --now", installer)
        self.assertIn("Automatic deletion: disabled", installer)
        self.assertIn('sudo test -f "$credential_path"', installer)
        self.assertIn('sudo test -L "$credential_path"', installer)
        self.assertIn("Profile: DEMO_WEEKLY", installer)
        self.assertIn("edgesentinel-recovery-capacity-manager", installer)
        self.assertIn('capacity_source="$project_dir/scripts/recovery_capacity_manager.py"', installer)

    def test_status_check_handles_not_installed_without_raw_systemd_failure(self):
        script = self.read("scripts", "check_scheduled_recovery_export.sh")
        self.assertIn("Scheduled recovery export: not installed", script)
        self.assertIn('sudo test -f "$timer_path"', script)
        self.assertIn("Profile: DEMO_WEEKLY", script)

    def test_capacity_preview_is_read_only_and_bounded(self):
        script = self.read("scripts", "preview_recovery_capacity.sh")
        manager = self.read("scripts", "recovery_capacity_manager.py")
        cleanup = self.read("scripts", "cleanup_recovery_capacity.sh")
        self.assertIn("536870912", script)
        self.assertIn("root:root 755", script)
        self.assertIn('exec sudo "$manager" preview', script)
        self.assertIn("DEMO_WEEKLY", manager)
        self.assertIn("Estimated annual growth bytes", manager)
        self.assertIn("Retention keep count", manager)
        self.assertIn("onerror=fail_walk", manager)
        self.assertIn("Delete performed: False", manager)
        self.assertIn("DELETE_PREVIEWED_LOCAL_RECOVERY_BACKUPS", manager)
        self.assertIn("recovery capacity plan is stale", manager)
        self.assertIn("fcntl.LOCK_EX | fcntl.LOCK_NB", manager)
        self.assertIn("encrypted_exports_deleted", manager)
        self.assertIn("shutil.rmtree(candidate)", manager)
        self.assertIn("^rcp_[0-9a-f]{32}$", cleanup)
        self.assertIn('exec sudo "$manager" apply --plan-id "$1"', cleanup)
        self.assertNotIn("rm -rf", manager)

    def test_status_check_fails_cleanly_when_capacity_runner_is_missing(self):
        script = self.read("scripts", "check_scheduled_recovery_export.sh")
        self.assertIn("installed assets are incomplete", script)
        self.assertIn('sudo test -f "$capacity_runner"', script)
        self.assertIn('sudo test -L "$capacity_runner"', script)
        self.assertIn("edgesentinel-recovery-capacity-manager", script)


if __name__ == "__main__":
    unittest.main()
