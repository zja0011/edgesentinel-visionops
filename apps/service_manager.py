"""Manage the live EdgeSentinel runtime inside the Jetson container."""

import argparse
from collections import deque
import datetime
import getpass
import json
import os
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from packages.harness.utf8 import print_json_utf8, write_json_atomic


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
DEFAULT_RUNTIME_DIR = os.path.join(PROJECT_DIR, "data", "runtime")
DEFAULT_STATE_PATH = os.path.join(
    DEFAULT_RUNTIME_DIR,
    "service.json",
)
TOKEN_ENV = "EDGESENTINEL_CONFIG_TOKEN"
READ_ONLY_ENV = "EDGESENTINEL_CONFIG_READ_ONLY"
MODEL_MODE_ENV = "EDGESENTINEL_MODEL_MODE"
MODEL_API_KEY_ENV = "EDGESENTINEL_MODEL_API_KEY"
MODEL_PROVIDER_ENV = "EDGESENTINEL_MODEL_PROVIDER"
MODEL_CREDENTIAL_PERSISTED_ENV = (
    "EDGESENTINEL_MODEL_CREDENTIAL_PERSISTED"
)
TLS_ENABLED_ENV = "EDGESENTINEL_TLS_ENABLED"
TLS_PUBLIC_ORIGIN_ENV = "EDGESENTINEL_TLS_PUBLIC_ORIGIN"


class ServiceManagerError(RuntimeError):
    """Raised when a requested service operation cannot be completed."""


def beijing_now():
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    )


def timestamp_text():
    return beijing_now().isoformat(timespec="milliseconds")


def run_id():
    return beijing_now().strftime("%Y%m%dT%H%M%S%f%z")


def read_state(path):
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as state_file:
            payload = json.load(state_file)
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def normalize_pid(pid):
    try:
        normalized = int(pid)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 1 else None


def process_exists(pid):
    normalized = normalize_pid(pid)
    if normalized is None:
        return False
    try:
        os.kill(normalized, 0)
        return True
    except OSError:
        return False


def process_matches(
    pid,
    proc_root="/proc",
    launcher_path=None,
):
    """Verify that a PID still belongs to our live launcher."""
    normalized = normalize_pid(pid)
    if normalized is None:
        return False
    try:
        with open(
            os.path.join(proc_root, str(normalized), "cmdline"),
            "rb",
        ) as command_file:
            arguments = [
                item
                for item in command_file.read().split(b"\x00")
                if item
            ]
    except OSError:
        return False
    expected = os.fsencode(
        os.path.abspath(
            launcher_path
            or os.path.join(
                PROJECT_DIR,
                "scripts",
                "run_dashboard_live.sh",
            )
        )
    )
    return expected in arguments


def process_identity(pid, launcher_path=None):
    normalized = normalize_pid(pid)
    alive = process_exists(normalized)
    return {
        "pid": normalized,
        "running": alive,
        "verified": alive and process_matches(
            normalized,
            launcher_path=launcher_path,
        ),
    }


def process_group_exists(process_group_id):
    normalized = normalize_pid(process_group_id)
    if normalized is None:
        return False
    try:
        os.killpg(normalized, 0)
        return True
    except OSError:
        return False


def build_running_state(
    pid,
    log_path,
    project_dir=PROJECT_DIR,
    config_save_enabled=True,
    model_mode="offline",
    model_credential_persisted=False,
    tls_enabled=False,
    tls_public_origin=None,
):
    return {
        "schema_version": "1.0",
        "service": "edgesentinel-visionops",
        "status": "running",
        "pid": int(pid),
        "process_group_id": int(pid),
        "started_at": timestamp_text(),
        "stopped_at": None,
        "log_path": os.path.relpath(log_path, project_dir),
        "launcher": "scripts/run_dashboard_live.sh",
        "config_save_enabled": bool(config_save_enabled),
        "model_mode": str(model_mode or "offline"),
        "model_credential_persisted": bool(
            model_credential_persisted
        ),
        "tls_enabled": bool(tls_enabled),
        "tls_public_origin": (
            str(tls_public_origin) if tls_enabled else None
        ),
    }


def tail_lines(path, count):
    count = max(1, min(int(count), 500))
    if not os.path.isfile(path):
        raise ServiceManagerError(
            "Runtime log does not exist: {}".format(path)
        )
    with open(
        path,
        "r",
        encoding="utf-8",
        errors="replace",
    ) as log_file:
        lines = deque(log_file, maxlen=count)
    return "".join(lines)


def request_json(url, timeout_seconds=2.0):
    try:
        with urlopen(url, timeout=float(timeout_seconds)) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError):
        return None


class ServiceManager(object):
    def __init__(
        self,
        project_dir=PROJECT_DIR,
        state_path=DEFAULT_STATE_PATH,
    ):
        self.project_dir = os.path.abspath(project_dir)
        self.runtime_dir = os.path.dirname(
            os.path.abspath(state_path)
        )
        self.state_path = os.path.abspath(state_path)
        self.launcher_path = os.path.join(
            self.project_dir,
            "scripts",
            "run_dashboard_live.sh",
        )

    def start(self, token, read_only=False):
        token = str(token or "")
        if not read_only and len(token) < 16:
            raise ServiceManagerError(
                "The zone administrator token must contain "
                "at least 16 characters."
            )
        state = read_state(self.state_path)
        identity = process_identity(
            state.get("pid"),
            launcher_path=self.launcher_path,
        )
        if identity["running"] and identity["verified"]:
            raise ServiceManagerError(
                "EdgeSentinel is already running with PID {}.".format(
                    identity["pid"]
                )
            )
        if identity["running"]:
            raise ServiceManagerError(
                "The saved PID belongs to another process; "
                "refusing to replace or stop it."
            )
        if not os.path.isfile(self.launcher_path):
            raise ServiceManagerError(
                "Live launcher does not exist: {}".format(
                    self.launcher_path
                )
            )
        if not os.path.isdir(self.runtime_dir):
            os.makedirs(self.runtime_dir)
        log_path = os.path.join(
            self.runtime_dir,
            "edgesentinel-{}.log".format(run_id()),
        )
        environment = os.environ.copy()
        if read_only:
            environment.pop(TOKEN_ENV, None)
            environment[READ_ONLY_ENV] = "1"
        else:
            environment[TOKEN_ENV] = token
            environment.pop(READ_ONLY_ENV, None)
        model_mode = str(
            environment.get(MODEL_MODE_ENV, "offline")
        ).strip().lower()
        model_credential_persisted = (
            environment.get(
                MODEL_CREDENTIAL_PERSISTED_ENV,
                "0",
            )
            == "1"
        )
        tls_enabled = environment.get(TLS_ENABLED_ENV, "0") == "1"
        tls_public_origin = environment.get(
            TLS_PUBLIC_ORIGIN_ENV
        )
        with open(
            log_path,
            "a",
            encoding="utf-8",
        ) as log_file:
            process = subprocess.Popen(
                ["bash", self.launcher_path],
                cwd=self.project_dir,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        running_state = build_running_state(
            process.pid,
            log_path,
            project_dir=self.project_dir,
            config_save_enabled=not read_only,
            model_mode=model_mode,
            model_credential_persisted=model_credential_persisted,
            tls_enabled=tls_enabled,
            tls_public_origin=tls_public_origin,
        )
        write_json_atomic(self.state_path, running_state)

        time.sleep(3.0)
        return_code = process.poll()
        if return_code is not None:
            running_state["status"] = "failed"
            running_state["stopped_at"] = timestamp_text()
            running_state["exit_code"] = int(return_code)
            write_json_atomic(self.state_path, running_state)
            raise ServiceManagerError(
                "EdgeSentinel stopped during startup (exit {}). "
                "Read the log with: bash scripts/"
                "edgesentinel_service.sh logs 80".format(return_code)
            )
        return self.status()

    def stop(self, timeout_seconds=15.0):
        state = read_state(self.state_path)
        pid = state.get("pid")
        if not pid:
            return self._stopped_payload(state)
        identity = process_identity(
            pid,
            launcher_path=self.launcher_path,
        )
        if identity["running"] and not identity["verified"]:
            raise ServiceManagerError(
                "PID {} is running but is not the EdgeSentinel "
                "launcher; refusing to signal it.".format(pid)
            )
        if identity["verified"]:
            process_group_id = identity["pid"]
            try:
                os.killpg(process_group_id, signal.SIGTERM)
            except OSError:
                if process_group_exists(process_group_id):
                    raise
            deadline = time.time() + float(timeout_seconds)
            while (
                process_group_exists(process_group_id)
                and time.time() < deadline
            ):
                time.sleep(0.2)
            if process_group_exists(process_group_id):
                raise ServiceManagerError(
                    "EdgeSentinel did not stop within {:.0f} seconds; "
                    "no forced kill was performed.".format(timeout_seconds)
                )
        state["status"] = "stopped"
        state["stopped_at"] = timestamp_text()
        state["last_pid"] = state.get("pid")
        state["pid"] = None
        state["process_group_id"] = None
        write_json_atomic(self.state_path, state)
        return self._stopped_payload(state)

    def status(self):
        state = read_state(self.state_path)
        identity = process_identity(
            state.get("pid"),
            launcher_path=self.launcher_path,
        )
        payload = {
            "schema_version": "1.0",
            "service": "edgesentinel-visionops",
            "status": "stopped",
            "process": identity,
            "api": {"status": "unavailable"},
            "vision": {"status": "unavailable"},
            "started_at": state.get("started_at"),
            "stopped_at": state.get("stopped_at"),
            "log_path": self._absolute_log_path(state),
            "state_path": self.state_path,
            "secret_persisted": False,
            "model_mode": state.get("model_mode", "offline"),
            "model_credential_persisted": bool(
                state.get("model_credential_persisted", False)
            ),
            "tls_enabled": bool(state.get("tls_enabled", False)),
            "tls_public_origin": state.get("tls_public_origin"),
            "config_save_enabled": state.get(
                "config_save_enabled"
            ),
        }
        if identity["verified"]:
            health = request_json("http://127.0.0.1:8000/health")
            people = request_json(
                "http://127.0.0.1:8000/health/vision"
            )
            payload["status"] = (
                "running"
                if (
                    health
                    and health.get("status") == "ok"
                    and people
                    and not people.get("stale", True)
                )
                else "starting_or_degraded"
            )
            if health:
                payload["api"] = {
                    "status": health.get("status", "unknown"),
                    "event_count": (
                        health.get("database") or {}
                    ).get("event_count"),
                }
                payload["model"] = health.get("agent_model")
            if people:
                payload["vision"] = {
                    "status": people.get("status", "available"),
                    "stale": bool(people.get("stale", True)),
                    "frame_id": people.get("frame_id"),
                    "age_seconds": people.get("age_seconds"),
                }
        elif identity["running"]:
            payload["status"] = "unverified_pid"
        return payload

    def logs(self, count=80):
        state = read_state(self.state_path)
        log_path = self._absolute_log_path(state)
        if not log_path:
            raise ServiceManagerError(
                "No managed runtime log has been recorded yet."
            )
        return tail_lines(log_path, count)

    def _absolute_log_path(self, state):
        value = state.get("log_path")
        if not value:
            return None
        candidate = (
            value
            if os.path.isabs(value)
            else os.path.join(self.project_dir, value)
        )
        candidate = os.path.abspath(candidate)
        try:
            inside_runtime = os.path.commonpath(
                [candidate, self.runtime_dir]
            ) == self.runtime_dir
        except ValueError:
            inside_runtime = False
        return candidate if inside_runtime else None

    def _stopped_payload(self, state):
        return {
            "schema_version": "1.0",
            "service": "edgesentinel-visionops",
            "status": "stopped",
            "process": {
                "pid": state.get("pid"),
                "running": False,
                "verified": False,
            },
            "log_path": self._absolute_log_path(state),
            "state_path": self.state_path,
            "secret_persisted": False,
            "model_mode": state.get("model_mode", "offline"),
            "model_credential_persisted": bool(
                state.get("model_credential_persisted", False)
            ),
            "tls_enabled": bool(state.get("tls_enabled", False)),
            "tls_public_origin": state.get("tls_public_origin"),
            "config_save_enabled": state.get(
                "config_save_enabled"
            ),
        }


def print_human_status(payload):
    process = payload["process"]
    print("Service status: {}".format(payload["status"].upper()))
    print("PID: {}".format(process.get("pid") or "-"))
    print(
        "Process: running={} verified={}".format(
            process.get("running"),
            process.get("verified"),
        )
    )
    print("API: {}".format(payload.get("api", {}).get("status", "-")))
    vision = payload.get("vision") or {}
    print(
        "Vision: {} stale={} frame={}".format(
            vision.get("status", "-"),
            vision.get("stale", "-"),
            vision.get("frame_id", "-"),
        )
    )
    print("Log: {}".format(payload.get("log_path") or "-"))
    print(
        "Zone configuration saving: {}".format(
            "enabled"
            if payload.get("config_save_enabled") is True
            else (
                "disabled"
                if payload.get("config_save_enabled") is False
                else "unknown"
            )
        )
    )
    print("Secret persisted: False")
    print(
        "Model mode: {}".format(
            payload.get("model_mode") or "offline"
        )
    )
    print(
        "Model credential persisted: {}".format(
            bool(payload.get("model_credential_persisted"))
        )
    )
    print("TLS enabled: {}".format(bool(payload.get("tls_enabled"))))
    if payload.get("tls_public_origin"):
        print("TLS public origin: {}".format(payload["tls_public_origin"]))


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Start, stop, inspect, and read logs for the live "
            "EdgeSentinel runtime inside the current container."
        )
    )
    commands = parser.add_subparsers(dest="command")
    commands.required = True

    start_parser = commands.add_parser("start")
    start_modes = start_parser.add_mutually_exclusive_group()
    start_modes.add_argument(
        "--token-stdin",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    start_modes.add_argument(
        "--read-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    start_parser.add_argument(
        "--deepseek-key-stdin",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    commands.add_parser("stop")

    status_parser = commands.add_parser("status")
    status_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
    )

    logs_parser = commands.add_parser("logs")
    logs_parser.add_argument(
        "lines",
        nargs="?",
        default=80,
        type=int,
    )
    return parser


def main():
    args = build_parser().parse_args()
    manager = ServiceManager()
    try:
        if args.command == "start":
            if args.deepseek_key_stdin:
                if not args.read_only:
                    raise ServiceManagerError(
                        "--deepseek-key-stdin requires --read-only"
                    )
                model_api_key = sys.stdin.readline().rstrip("\r\n")
                if len(model_api_key) < 16:
                    raise ServiceManagerError(
                        "The DeepSeek API key must contain at least "
                        "16 characters."
                    )
                os.environ[MODEL_MODE_ENV] = "remote"
                os.environ[MODEL_PROVIDER_ENV] = "deepseek"
                os.environ[MODEL_API_KEY_ENV] = model_api_key
                os.environ[MODEL_CREDENTIAL_PERSISTED_ENV] = "0"
            if args.read_only:
                token = ""
            else:
                token = (
                    sys.stdin.readline().rstrip("\r\n")
                    if args.token_stdin
                    else (
                        os.environ.get(TOKEN_ENV)
                        or getpass.getpass(
                            "Zone administrator token: "
                        )
                    )
                )
            try:
                payload = manager.start(
                    token,
                    read_only=args.read_only,
                )
            finally:
                if args.deepseek_key_stdin:
                    os.environ.pop(MODEL_API_KEY_ENV, None)
            print("EdgeSentinel started in the background.")
            print_human_status(payload)
        elif args.command == "stop":
            manager.stop()
            print("EdgeSentinel stopped.")
        elif args.command == "status":
            payload = manager.status()
            if args.as_json:
                print_json_utf8(payload)
            else:
                print_human_status(payload)
        elif args.command == "logs":
            sys.stdout.write(manager.logs(args.lines))
        return 0
    except ServiceManagerError as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
