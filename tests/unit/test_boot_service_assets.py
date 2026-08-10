import os
import unittest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


def read_text(*parts):
    with open(
        os.path.join(PROJECT_DIR, *parts),
        "r",
        encoding="utf-8",
    ) as input_file:
        return input_file.read()


class BootServiceAssetTests(unittest.TestCase):
    def test_unit_orders_boot_after_docker_and_stops_cleanly(self):
        unit = read_text(
            "deploy",
            "edgesentinel-visionops.service.template",
        )

        self.assertIn("Requires=docker.service", unit)
        self.assertIn("After=docker.service network-online.target", unit)
        self.assertIn("dev-video0.device", unit)
        self.assertIn(
            "ExecStartPre=/bin/sh -c "
            "'until [ -c /dev/video0 ]; do sleep 2; done'",
            unit,
        )
        self.assertIn(
            "if [ -L /tmp/edgesentinel_nv_jetson_model ]; "
            "then exit 1; fi",
            unit,
        )
        self.assertIn(
            "rm -f -- /tmp/edgesentinel_nv_jetson_model/model",
            unit,
        )
        self.assertIn(
            "rmdir -- /tmp/edgesentinel_nv_jetson_model",
            unit,
        )
        self.assertIn("TimeoutStartSec=180", unit)
        self.assertNotIn("Restart=", unit)
        self.assertNotIn("RestartSec=", unit)
        self.assertIn(
            "ExecStart=/usr/bin/docker start edgesentinel-visionops",
            unit,
        )
        self.assertIn(
            "apps.service_manager start --read-only",
            unit,
        )
        self.assertIn(
            "scripts/edgesentinel_service.sh stop",
            unit,
        )
        self.assertIn("WantedBy=multi-user.target", unit)

    def test_unit_never_executes_the_user_writable_host_script(self):
        unit = read_text(
            "deploy",
            "edgesentinel-visionops.service.template",
        )

        self.assertNotIn("host_edgesentinel.sh", unit)
        self.assertNotIn("@PROJECT_DIR@", unit)
        self.assertNotIn("WorkingDirectory=", unit)

    def test_unit_uses_only_the_fixed_root_model_credential_source(self):
        unit = read_text(
            "deploy",
            "edgesentinel-visionops.service.template",
        )

        self.assertNotIn("EDGESENTINEL_CONFIG_TOKEN", unit)
        self.assertIn(
            "EnvironmentFile=-/etc/edgesentinel-visionops/"
            "model-runtime.env",
            unit,
        )
        self.assertIn(
            "EnvironmentFile=-/etc/edgesentinel-visionops/"
            "model-cost-runtime.env",
            unit,
        )
        self.assertIn(
            "Environment=EDGESENTINEL_AGENT_MAX_TOTAL_TOKENS=16384",
            unit,
        )
        self.assertIn(
            "-e EDGESENTINEL_MODEL_MAX_ESTIMATED_COST_USD",
            unit,
        )
        self.assertIn(
            "EnvironmentFile=-/etc/edgesentinel-visionops/"
            "weather-runtime.env",
            unit,
        )
        self.assertIn(
            "-e EDGESENTINEL_WEATHER_DEFAULT_LOCATION",
            unit,
        )
        self.assertIn(
            "Environment=EDGESENTINEL_MODEL_MODE=offline",
            unit,
        )
        self.assertNotIn("sk-", unit)
        self.assertIn(
            "docker exec -e EDGESENTINEL_MODEL_MODE",
            unit,
        )

    def test_installer_enables_but_does_not_start_the_unit(self):
        installer = read_text(
            "scripts",
            "install_host_service.sh",
        )

        self.assertIn("systemctl enable", installer)
        self.assertIn("systemd-analyze verify", installer)
        self.assertIn("Current runtime was not restarted.", installer)
        self.assertNotIn("systemctl start", installer)
        self.assertNotIn("systemctl restart", installer)
        verify_position = installer.index(
            'systemd-analyze verify "$TEMPORARY_UNIT"'
        )
        install_position = installer.index("sudo install")
        self.assertLess(verify_position, install_position)
        self.assertIn(
            'TEMPORARY_UNIT="$TEMPORARY_DIR/$UNIT_NAME"',
            installer,
        )

    def test_boot_check_requires_root_owned_non_literal_secret_unit(self):
        check = read_text("scripts", "check_boot_service.sh")

        self.assertIn('owner" = "root:root', check)
        self.assertIn('mode" = "644', check)
        self.assertIn(
            "Zone administrator credential persisted: False",
            check,
        )
        self.assertIn(
            "Model fallback without credential: offline-rule-mock",
            check,
        )
        self.assertIn(
            "configure_deepseek_boot.sh",
            check,
        )
        self.assertIn(
            "Camera boot dependency: configured",
            check,
        )
        self.assertIn("NeedDaemonReload", check)
        self.assertIn('need_daemon_reload" != "no', check)
        self.assertIn('load_state" != "loaded', check)
        self.assertIn(
            "Camera wait: every 2 seconds, bounded by "
            "180-second timeout",
            check,
        )
        self.assertIn(
            "NVIDIA model mount bootstrap: configured",
            check,
        )
        self.assertIn(
            "Root executes project code on host: False",
            check,
        )
        self.assertIn(
            "Boot Service installation test passed.",
            check,
        )

    def test_deepseek_configurator_uses_root_only_atomic_file(self):
        configurator = read_text(
            "scripts",
            "configure_deepseek_boot.sh",
        )

        self.assertIn(
            'CREDENTIAL_FILE="$CREDENTIAL_DIR/model-runtime.env"',
            configurator,
        )
        self.assertIn("--mode 0700", configurator)
        self.assertIn("umask 077", configurator)
        self.assertIn("chown root:root", configurator)
        self.assertIn("chmod 0600", configurator)
        self.assertIn("mv -f --", configurator)
        self.assertIn("model-runtime.env.disabled", configurator)
        self.assertIn("select_offline", configurator)
        self.assertIn("select_online", configurator)
        self.assertIn(
            "EDGESENTINEL_MODEL_CREDENTIAL_PERSISTED=1",
            configurator,
        )
        self.assertNotIn("set -x", configurator)

    def test_weather_configurator_uses_root_only_atomic_file(self):
        configurator = read_text(
            "scripts",
            "configure_weather_boot.sh",
        )

        self.assertIn(
            'CONFIG_FILE="$CONFIG_DIR/weather-runtime.env"',
            configurator,
        )
        self.assertIn("EDGESENTINEL_WEATHER_DEFAULT_LOCATION", configurator)
        self.assertIn("--mode 0700", configurator)
        self.assertIn("umask 077", configurator)
        self.assertIn("chown root:root", configurator)
        self.assertIn("chmod 0600", configurator)
        self.assertIn("mv -f --", configurator)
        self.assertNotIn("set -x", configurator)

    def test_model_cost_configurator_uses_root_only_atomic_file(self):
        configurator = read_text(
            "scripts",
            "configure_model_cost_boot.sh",
        )

        self.assertIn(
            'CONFIG_FILE="$CONFIG_DIR/model-cost-runtime.env"',
            configurator,
        )
        self.assertIn("EDGESENTINEL_MODEL_RATE_CARD_ID", configurator)
        self.assertIn(
            "EDGESENTINEL_MODEL_INPUT_USD_PER_MILLION",
            configurator,
        )
        self.assertIn(
            "EDGESENTINEL_MODEL_MAX_ESTIMATED_COST_USD",
            configurator,
        )
        self.assertIn("--mode 0700", configurator)
        self.assertIn("umask 077", configurator)
        self.assertIn("chown root:root", configurator)
        self.assertIn("chmod 0600", configurator)
        self.assertIn("mv -f --", configurator)
        self.assertIn("not a provider invoice", configurator)
        self.assertNotIn("set -x", configurator)

    def test_persistent_runtime_check_never_reads_key_into_output(self):
        check = read_text(
            "scripts",
            "check_deepseek_systemd_runtime.sh",
        )

        self.assertIn(
            "configure_deepseek_boot.sh\" status",
            check,
        )
        self.assertIn("API key exposed:", check)
        self.assertIn('"api_key" not in raw', check)
        self.assertNotIn("sk-test", check)
        self.assertNotIn("curl ", check)
        self.assertIn("from urllib.request import urlopen", check)


if __name__ == "__main__":
    unittest.main()
