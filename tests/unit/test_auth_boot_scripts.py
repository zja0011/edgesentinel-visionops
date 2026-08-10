import os
import subprocess
import sys
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


class AuthBootScriptTests(unittest.TestCase):
    def test_credential_generator_emits_hash_and_not_password(self):
        password = "enterprise-test-password"
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.auth_credential",
                "--username",
                "admin",
            ],
            cwd=PROJECT_DIR,
            env=environment,
            input=password,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )

        self.assertIn("EDGESENTINEL_AUTH_ENABLED=1", process.stdout)
        self.assertIn("pbkdf2_sha256$", process.stdout)
        self.assertIn("EDGESENTINEL_AUTH_CREDENTIAL_PERSISTED=1", process.stdout)
        self.assertNotIn(password, process.stdout)
        self.assertNotIn(password, process.stderr)

    def test_systemd_passes_root_owned_auth_environment(self):
        unit = read_project(
            "deploy/edgesentinel-visionops.service.template"
        )
        installer = read_project("scripts/install_host_service.sh")
        configurator = read_project("scripts/configure_auth_boot.sh")

        self.assertIn(
            "EnvironmentFile=-/etc/edgesentinel-visionops/auth-runtime.env",
            unit,
        )
        self.assertIn("-e EDGESENTINEL_AUTH_SESSION_SECRET", unit)
        self.assertIn("EDGESENTINEL_AUTH_ENABLED=1", unit)
        self.assertIn("auth-runtime.env", installer)
        self.assertIn("--mode 0600", configurator)
        self.assertIn("Password stored in plaintext: False", configurator)
        self.assertNotIn("AUTH_PASSWORD=admin", configurator)


if __name__ == "__main__":
    unittest.main()
