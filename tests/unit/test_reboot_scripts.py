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


class RebootScriptTests(unittest.TestCase):
    def test_preflight_checks_health_before_writing_marker(self):
        script = read_script("prepare_reboot_test.sh")

        health = script.index("check_tls_systemd_runtime.sh")
        marker = script.index("apps.reboot_marker prepare")
        self.assertLess(health, marker)
        self.assertEqual(
            script.count("check_systemd_runtime.sh"),
            1,
        )
        self.assertIn("tls-runtime.env", script)
        before_final_instructions = "\n".join(
            script.splitlines()[:-4]
        )
        self.assertNotIn(
            "sudo reboot",
            before_final_instructions,
        )

    def test_recovery_waits_and_compares_boot_identity(self):
        script = read_script("check_reboot_recovery.sh")

        self.assertIn('while [ "$attempt" -lt 60 ]', script)
        self.assertIn("journalctl", script)
        self.assertIn("apps.reboot_marker verify", script)
        self.assertIn("check_tls_systemd_runtime.sh", script)
        self.assertIn("TLS certificate unchanged:", script)
        self.assertIn("Boot ID changed:", script)
        self.assertIn("Reboot Recovery smoke test passed.", script)


if __name__ == "__main__":
    unittest.main()
