import os
import unittest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


def read_project(relative_path):
    with open(
        os.path.join(PROJECT_DIR, relative_path),
        "r",
        encoding="utf-8",
    ) as input_file:
        return input_file.read()


class TlsBootScriptTests(unittest.TestCase):
    def test_configurator_keeps_private_key_root_only(self):
        script = read_project("scripts/configure_tls_boot.sh")

        self.assertIn('PRIVATE_KEY="$TLS_DIR/server.key"', script)
        self.assertIn("--mode 0600", script)
        self.assertIn("openssl req -x509", script)
        self.assertIn("subjectAltName", script)
        self.assertIn("EDGESENTINEL_AUTH_COOKIE_SECURE=1", script)
        self.assertIn("Private key persisted in Docker: False", script)
        self.assertNotIn("set -x", script)

    def test_unit_copies_key_to_memory_and_passes_only_paths(self):
        unit = read_project(
            "deploy/edgesentinel-visionops.service.template"
        )

        self.assertIn(
            "EnvironmentFile=-/etc/edgesentinel-visionops/tls-runtime.env",
            unit,
        )
        self.assertIn("docker exec -i edgesentinel-visionops", unit)
        self.assertIn(
            "< /etc/edgesentinel-visionops/tls/server.key", unit
        )
        self.assertIn("/dev/shm/edgesentinel-tls/server.key", unit)
        self.assertNotIn("docker cp", unit)
        self.assertIn("-e EDGESENTINEL_TLS_PRIVATE_KEY", unit)
        self.assertNotIn("BEGIN PRIVATE KEY", unit)

    def test_runtime_check_verifies_https_and_secure_cookie(self):
        script = read_project("scripts/check_tls_systemd_runtime.sh")
        windows_check = read_project("scripts/check_tls_dashboard.ps1")

        self.assertIn("TLS certificate pin mismatch", script)
        self.assertIn("getpeercert(binary_form=True)", script)
        self.assertIn("external_https_required", script)
        self.assertIn("cookie_secure", script)
        self.assertIn("Strict-Transport-Security", windows_check)
        self.assertIn("Content-Security-Policy", windows_check)
        self.assertIn("SecurityProtocolType]::Tls12", windows_check)
        self.assertIn("EdgeSentinelCertificatePinning", windows_check)
        self.assertIn("RemoteCertificateValidationCallback", windows_check)
        self.assertNotIn("return $true", windows_check)
        self.assertIn("Private key persisted in Docker: False", script)

    def test_live_launcher_supervises_tls_proxy(self):
        script = read_project("scripts/run_dashboard_live.sh")

        self.assertIn("python3 -m apps.tls_proxy", script)
        self.assertIn('TLS_PID=""', script)
        self.assertIn('kill "$TLS_PID"', script)


if __name__ == "__main__":
    unittest.main()
