import os
import tempfile
import unittest

from packages.events.sqlite_store import SqliteEventStore
from packages.harness.default_tools import build_default_registry
from packages.harness.registry import ToolInvocationError
from packages.harness.mock_model import OfflineMockModel
from packages.harness.tool_router import ToolSchemaRouter
from packages.mcp.server import EdgeSentinelMcpServer


class DisasterRecoveryToolTests(unittest.TestCase):
    def build_registry(self, directory):
        config_dir = os.path.join(directory, "configs")
        os.makedirs(config_dir)
        with open(
            os.path.join(config_dir, "zones.json"),
            "w",
            encoding="utf-8",
        ) as output_file:
            output_file.write('{"zones": []}\n')
        database = os.path.join(
            directory,
            "data",
            "events",
            "edgesentinel.db",
        )
        SqliteEventStore(database).close()
        return build_default_registry(
            directory,
            database,
            audit_path=os.path.join(directory, "audit.jsonl"),
        )

    def test_backup_is_l1_confirmed_and_preview_is_l0_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self.build_registry(directory)
            schemas = {item["name"]: item for item in registry.schemas()}
            create_annotations = schemas["recovery.create_backup"][
                "annotations"
            ]
            self.assertEqual(create_annotations["riskLevel"], "L1")
            self.assertTrue(create_annotations["requiresConfirmation"])
            self.assertFalse(create_annotations["readOnlyHint"])
            for name in (
                "recovery.get_status",
                "recovery.preview_restore",
            ):
                annotations = schemas[name]["annotations"]
                self.assertEqual(annotations["riskLevel"], "L0")
                self.assertTrue(annotations["readOnlyHint"])
                self.assertTrue(annotations["autoExecute"])

            with self.assertRaises(ToolInvocationError) as denied:
                registry.invoke("recovery.create_backup", {})
            self.assertEqual(denied.exception.code, "POLICY_DENIED")

            created = registry.invoke(
                "recovery.create_backup",
                {},
                confirmation_granted=True,
            )["result"]
            status = registry.invoke(
                "recovery.get_status",
                {"limit": 5},
            )["result"]
            preview = registry.invoke(
                "recovery.preview_restore",
                {"backup_id": created["backup_id"]},
            )["result"]
            self.assertEqual(status["backup_count"], 1)
            self.assertEqual(preview["backup_id"], created["backup_id"])
            self.assertFalse(preview["restore_performed"])

    def test_mcp_exposes_only_the_two_read_only_recovery_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self.build_registry(directory)
            server = EdgeSentinelMcpServer(registry)
            schemas = {item["name"] for item in registry.schemas()}
            read_only = set(server._read_only_schemas)
            self.assertEqual(len(schemas), 33)
            self.assertEqual(len(read_only), 25)
            self.assertIn("recovery.get_status", read_only)
            self.assertIn("recovery.preview_restore", read_only)
            self.assertNotIn("recovery.create_backup", read_only)

    def test_offline_model_and_schema_router_understand_recovery_intents(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self.build_registry(directory)
            schemas = registry.schemas()
            route = ToolSchemaRouter().route(
                "创建灾难恢复备份",
                schemas,
            )
            self.assertEqual(route["mode"], "DETERMINISTIC")
            self.assertIn(
                "recovery.create_backup",
                route["selected_tools"],
            )
            response = OfflineMockModel().generate(
                {
                    "user_message": "创建灾难恢复备份",
                    "recent_tool_results": [],
                },
                tool_schemas=schemas,
            )
            self.assertEqual(len(response.tool_calls), 1)
            self.assertEqual(
                response.tool_calls[0].name,
                "recovery.create_backup",
            )

    def test_host_restore_script_enforces_maintenance_sequence(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        script_path = os.path.join(
            root,
            "scripts",
            "restore_disaster_recovery.sh",
        )
        with open(script_path, "r", encoding="utf-8") as input_file:
            script = input_file.read()
        self.assertIn('sudo systemctl stop "$UNIT_NAME"', script)
        self.assertIn("EDGESENTINEL_RESTORE_MAINTENANCE=1", script)
        self.assertIn("ENTER_RECOVERY_MAINTENANCE", script)
        self.assertIn("RESTORE_DISASTER_RECOVERY", script)
        self.assertIn("python3 -m apps.disaster_recovery preview", script)
        self.assertIn('sudo systemctl start "$UNIT_NAME"', script)
        self.assertIn("check_systemd_runtime.sh", script)
        self.assertNotIn("/etc/edgesentinel-visionops/tls/server.key", script)

    def test_dashboard_acceptance_is_tls_pinned_and_confirmation_gated(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        script_path = os.path.join(
            root,
            "scripts",
            "check_disaster_recovery_dashboard.ps1",
        )
        with open(script_path, "r", encoding="utf-8") as input_file:
            script = input_file.read()
        self.assertIn("ExpectedTlsFingerprint", script)
        self.assertIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn("recovery.create_backup", script)
        self.assertIn("recovery.get_status", script)
        self.assertIn("list recovery backups", script)
        self.assertIn("create disaster recovery backup", script)
        self.assertIn("Invalid confirmation: HTTP", script)
        self.assertIn("Duplicate confirmation: HTTP", script)
        self.assertIn("credentials_included", script)
        self.assertIn("model_history", script)
        self.assertIn("pending\\.tool_name", script)
        self.assertIn("activeAgentToolName", script)
        self.assertIn("[switch]$AssetsOnly", script)
        self.assertIn("No backup created by this recheck: True", script)
        self.assertNotIn("确认创建本地恢复备份", script)
        self.assertNotIn("ServerCertificateValidationCallback = { $true }", script)


if __name__ == "__main__":
    unittest.main()
