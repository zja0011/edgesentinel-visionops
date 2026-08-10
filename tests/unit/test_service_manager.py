import json
import io
import os
import signal
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

from apps.service_manager import (
    MODEL_API_KEY_ENV,
    MODEL_CREDENTIAL_PERSISTED_ENV,
    MODEL_MODE_ENV,
    MODEL_PROVIDER_ENV,
    READ_ONLY_ENV,
    ServiceManager,
    ServiceManagerError,
    build_parser,
    build_running_state,
    normalize_pid,
    process_matches,
    read_state,
    tail_lines,
)
from packages.harness.utf8 import write_json_atomic


class ServiceManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project_dir = self.temporary.name
        self.runtime_dir = os.path.join(
            self.project_dir,
            "data",
            "runtime",
        )
        self.state_path = os.path.join(
            self.runtime_dir,
            "service.json",
        )
        self.manager = ServiceManager(
            project_dir=self.project_dir,
            state_path=self.state_path,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_running_state_never_contains_the_token(self):
        log_path = os.path.join(
            self.runtime_dir,
            "edgesentinel-test.log",
        )

        state = build_running_state(
            123,
            log_path,
            project_dir=self.project_dir,
        )
        rendered = json.dumps(state)

        self.assertNotIn("token", rendered.lower())
        self.assertNotIn("secret", rendered.lower())
        self.assertEqual(state["process_group_id"], 123)
        self.assertEqual(state["launcher"], "scripts/run_dashboard_live.sh")
        self.assertTrue(state["config_save_enabled"])
        self.assertEqual(state["model_mode"], "offline")
        self.assertFalse(state["model_credential_persisted"])
        self.assertFalse(state["tls_enabled"])
        self.assertIsNone(state["tls_public_origin"])

    def test_state_round_trip_is_atomic_and_utf8(self):
        payload = {
            "status": "running",
            "message": "北京时间",
        }

        write_json_atomic(self.state_path, payload)

        self.assertEqual(read_state(self.state_path), payload)

    @mock.patch("apps.service_manager.time.sleep")
    @mock.patch("apps.service_manager.process_identity")
    @mock.patch("apps.service_manager.subprocess.Popen")
    def test_start_passes_token_only_in_child_environment(
        self,
        popen,
        identity,
        unused_sleep,
    ):
        scripts_dir = os.path.join(self.project_dir, "scripts")
        os.makedirs(scripts_dir)
        with open(
            os.path.join(scripts_dir, "run_dashboard_live.sh"),
            "w",
            encoding="utf-8",
        ) as launcher:
            launcher.write("#!/usr/bin/env bash\n")
        identity.return_value = {
            "pid": None,
            "running": False,
            "verified": False,
        }
        process = popen.return_value
        process.pid = 2468
        process.poll.return_value = None
        secret = "not-written-to-state"
        expected = {"status": "starting_or_degraded"}

        with mock.patch.object(
            self.manager,
            "status",
            return_value=expected,
        ):
            result = self.manager.start(secret)

        self.assertEqual(result, expected)
        child_environment = popen.call_args[1]["env"]
        self.assertEqual(
            child_environment["EDGESENTINEL_CONFIG_TOKEN"],
            secret,
        )
        rendered_state = json.dumps(read_state(self.state_path))
        self.assertNotIn(secret, rendered_state)
        self.assertNotIn("token", rendered_state.lower())

    @mock.patch("apps.service_manager.time.sleep")
    @mock.patch("apps.service_manager.process_identity")
    @mock.patch("apps.service_manager.subprocess.Popen")
    def test_read_only_start_neither_requires_nor_passes_a_token(
        self,
        popen,
        identity,
        unused_sleep,
    ):
        scripts_dir = os.path.join(self.project_dir, "scripts")
        os.makedirs(scripts_dir)
        with open(
            os.path.join(scripts_dir, "run_dashboard_live.sh"),
            "w",
            encoding="utf-8",
        ) as launcher:
            launcher.write("#!/usr/bin/env bash\n")
        identity.return_value = {
            "pid": None,
            "running": False,
            "verified": False,
        }
        process = popen.return_value
        process.pid = 1357
        process.poll.return_value = None

        with mock.patch.object(
            self.manager,
            "status",
            return_value={"status": "starting_or_degraded"},
        ):
            self.manager.start("", read_only=True)

        child_environment = popen.call_args[1]["env"]
        self.assertNotIn(
            "EDGESENTINEL_CONFIG_TOKEN",
            child_environment,
        )
        self.assertEqual(child_environment[READ_ONLY_ENV], "1")
        state = read_state(self.state_path)
        self.assertFalse(state["config_save_enabled"])

    @mock.patch("apps.service_manager.time.sleep")
    @mock.patch("apps.service_manager.process_identity")
    @mock.patch("apps.service_manager.subprocess.Popen")
    def test_start_records_remote_mode_without_storing_model_key(
        self,
        popen,
        identity,
        unused_sleep,
    ):
        scripts_dir = os.path.join(self.project_dir, "scripts")
        os.makedirs(scripts_dir)
        with open(
            os.path.join(scripts_dir, "run_dashboard_live.sh"),
            "w",
            encoding="utf-8",
        ) as launcher:
            launcher.write("#!/usr/bin/env bash\n")
        identity.return_value = {
            "pid": None,
            "running": False,
            "verified": False,
        }
        process = popen.return_value
        process.pid = 9753
        process.poll.return_value = None
        secret = "sk-test-model-secret"
        model_environment = {
            MODEL_MODE_ENV: "remote",
            MODEL_PROVIDER_ENV: "deepseek",
            MODEL_API_KEY_ENV: secret,
            MODEL_CREDENTIAL_PERSISTED_ENV: "1",
        }

        with mock.patch.dict(
            os.environ,
            model_environment,
            clear=False,
        ):
            with mock.patch.object(
                self.manager,
                "status",
                return_value={"status": "starting_or_degraded"},
            ):
                self.manager.start("", read_only=True)

        child_environment = popen.call_args[1]["env"]
        self.assertEqual(child_environment[MODEL_API_KEY_ENV], secret)
        state = read_state(self.state_path)
        self.assertEqual(state["model_mode"], "remote")
        self.assertTrue(state["model_credential_persisted"])
        self.assertNotIn(secret, json.dumps(state))

    def test_process_match_requires_the_exact_launcher_path(self):
        proc_root = os.path.join(self.temporary.name, "proc")
        process_dir = os.path.join(proc_root, "321")
        launcher_path = os.path.join(
            self.project_dir,
            "scripts",
            "run_dashboard_live.sh",
        )
        os.makedirs(process_dir)
        with open(
            os.path.join(process_dir, "cmdline"),
            "wb",
        ) as command_file:
            command_file.write(
                b"bash\x00"
                + os.fsencode(os.path.abspath(launcher_path))
                + b"\x00"
            )

        self.assertTrue(
            process_matches(
                321,
                proc_root=proc_root,
                launcher_path=launcher_path,
            )
        )

    def test_process_match_rejects_an_unrelated_process(self):
        proc_root = os.path.join(self.temporary.name, "proc")
        process_dir = os.path.join(proc_root, "654")
        os.makedirs(process_dir)
        with open(
            os.path.join(process_dir, "cmdline"),
            "wb",
        ) as command_file:
            command_file.write(b"python3\x00unrelated.py\x00")

        self.assertFalse(process_matches(654, proc_root=proc_root))

    def test_invalid_and_process_group_pids_are_rejected(self):
        self.assertIsNone(normalize_pid(None))
        self.assertIsNone(normalize_pid("invalid"))
        self.assertIsNone(normalize_pid(0))
        self.assertIsNone(normalize_pid(1))
        self.assertEqual(normalize_pid("42"), 42)

    def test_token_stdin_is_explicit_and_never_accepts_a_value(self):
        args = build_parser().parse_args(
            ["start", "--token-stdin"]
        )

        self.assertTrue(args.token_stdin)
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(
                    ["start", "--token-stdin=visible-secret"]
                )
        read_only = build_parser().parse_args(
            ["start", "--read-only"]
        )
        self.assertTrue(read_only.read_only)
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(
                    ["start", "--read-only", "--token-stdin"]
                )

    def test_log_tail_is_bounded_to_requested_lines(self):
        log_path = os.path.join(self.temporary.name, "runtime.log")
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write("one\ntwo\nthree\nfour\n")

        self.assertEqual(tail_lines(log_path, 2), "three\nfour\n")

    def test_log_path_cannot_escape_the_runtime_directory(self):
        write_json_atomic(
            self.state_path,
            {"log_path": "../../outside.log"},
        )

        with self.assertRaises(ServiceManagerError):
            self.manager.logs(5)

    @mock.patch("apps.service_manager.os.killpg", create=True)
    @mock.patch("apps.service_manager.process_identity")
    def test_stop_refuses_to_signal_an_unverified_pid(
        self,
        identity,
        kill_group,
    ):
        write_json_atomic(
            self.state_path,
            {
                "pid": 777,
                "process_group_id": 777,
                "status": "running",
            },
        )
        identity.return_value = {
            "pid": 777,
            "running": True,
            "verified": False,
        }

        with self.assertRaises(ServiceManagerError):
            self.manager.stop()

        kill_group.assert_not_called()

    @mock.patch(
        "apps.service_manager.process_group_exists",
        return_value=False,
    )
    @mock.patch("apps.service_manager.os.killpg", create=True)
    @mock.patch("apps.service_manager.process_identity")
    def test_stop_signals_the_verified_pid_process_group(
        self,
        identity,
        kill_group,
        unused_group_exists,
    ):
        write_json_atomic(
            self.state_path,
            {
                "pid": 888,
                "process_group_id": 999,
                "status": "running",
            },
        )
        identity.return_value = {
            "pid": 888,
            "running": True,
            "verified": True,
        }

        payload = self.manager.stop()

        kill_group.assert_called_once_with(888, signal.SIGTERM)
        self.assertEqual(payload["status"], "stopped")
        saved_state = read_state(self.state_path)
        self.assertEqual(saved_state["status"], "stopped")
        self.assertEqual(saved_state["last_pid"], 888)
        self.assertIsNone(saved_state["pid"])
        self.assertIsNone(saved_state["process_group_id"])

    @mock.patch("apps.service_manager.process_identity")
    def test_status_does_not_query_api_for_a_stopped_process(
        self,
        identity,
    ):
        identity.return_value = {
            "pid": None,
            "running": False,
            "verified": False,
        }

        with mock.patch(
            "apps.service_manager.request_json"
        ) as request:
            payload = self.manager.status()

        self.assertEqual(payload["status"], "stopped")
        self.assertFalse(payload["secret_persisted"])
        self.assertFalse(payload["model_credential_persisted"])
        request.assert_not_called()

    @mock.patch("apps.service_manager.request_json")
    @mock.patch("apps.service_manager.process_identity")
    def test_status_requires_healthy_api_and_fresh_vision(
        self,
        identity,
        request,
    ):
        identity.return_value = {
            "pid": 987,
            "running": True,
            "verified": True,
        }
        request.side_effect = [
            {
                "status": "ok",
                "database": {"event_count": 12},
            },
            {
                "status": "available",
                "stale": False,
                "frame_id": 456,
                "age_seconds": 0.2,
                "scene_content_exposed": False,
            },
        ]

        payload = self.manager.status()

        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["api"]["event_count"], 12)
        self.assertEqual(payload["vision"]["frame_id"], 456)
        self.assertNotIn("current_people", payload["vision"])
        self.assertEqual(
            request.call_args_list[1][0][0],
            "http://127.0.0.1:8000/health/vision",
        )


if __name__ == "__main__":
    unittest.main()
