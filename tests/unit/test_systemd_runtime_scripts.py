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


class SystemdRuntimeScriptTests(unittest.TestCase):
    def test_switch_stops_manual_runtime_before_systemd_start(self):
        script = read_script("switch_to_systemd_readonly.sh")

        stop_position = script.index(
            'host_edgesentinel.sh" stop'
        )
        start_position = script.index(
            'systemctl start "$UNIT_NAME"'
        )
        self.assertLess(stop_position, start_position)
        self.assertIn("check_systemd_runtime.sh", script)
        self.assertNotIn("reboot", script)

    def test_runtime_check_requires_authenticated_vision_health(self):
        script = read_script("check_systemd_runtime.sh")

        self.assertIn(
            "status['config_save_enabled'] is False",
            script,
        )
        self.assertIn("auth['enabled'] is True", script)
        self.assertIn("auth['ready'] is True", script)
        self.assertIn("auth['credentials_exposed'] is False", script)
        self.assertIn("status['vision']['stale'] is False", script)

    def test_runtime_check_proves_zone_write_requires_login(self):
        script = read_script("check_systemd_runtime.sh")

        self.assertIn('expected_write_status="401"', script)
        self.assertIn('expected_write_status="426"', script)
        self.assertIn(
            '[ "$write_status" = "$expected_write_status" ]', script
        )
        self.assertIn(
            "Zone administrator credential persisted:",
            script,
        )
        self.assertIn("Model credential persisted:", script)
        self.assertIn(
            "Systemd Runtime smoke test passed.",
            script,
        )


if __name__ == "__main__":
    unittest.main()
