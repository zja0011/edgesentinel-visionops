import os
import unittest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


def read_script(name):
    with open(
        os.path.join(PROJECT_DIR, "scripts", name),
        "r",
        encoding="utf-8",
    ) as script_file:
        return script_file.read()


class TlsRotationScriptTests(unittest.TestCase):
    def test_rotation_is_confirmed_bounded_and_rolls_back(self):
        script = read_script("rotate_tls_boot.sh")

        self.assertIn("ROTATE_TLS_CERTIFICATE", script)
        self.assertIn('BACKUP_READY=0', script)
        self.assertIn('COMMITTED=0', script)
        self.assertIn("restoring the previous credential", script)
        self.assertIn('sudo rmdir -- "$BACKUP_DIRECTORY"', script)
        self.assertIn('sudo docker exec "$CONTAINER_NAME"', script)
        self.assertIn('"$backup_count" -ge 5', script)
        self.assertIn("contains_secret", script)
        self.assertNotIn("set -x", script)

    def test_rotation_check_proves_restart_and_all_public_copies(self):
        script = read_script("check_tls_rotation.sh")

        self.assertIn("check_tls_systemd_runtime.sh", script)
        self.assertIn("old_certificate_sha256", script)
        self.assertIn("new_certificate_sha256", script)
        self.assertIn("service_started_before", script)
        self.assertIn('sudo docker exec "$CONTAINER_NAME"', script)
        self.assertIn("Runtime certificate match: True", script)
        self.assertIn("Backup private key: root:root 600", script)
        self.assertIn("Private key exposed: False", script)


if __name__ == "__main__":
    unittest.main()
