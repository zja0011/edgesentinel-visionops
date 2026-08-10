"""Supervise the vision worker across camera disconnects."""

import argparse
import datetime
import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time

from packages.harness.utf8 import write_json_atomic
from packages.monitoring.camera_events import (
    CameraLifecycleEvents,
    CameraLifecycleEventWriter,
)


def beijing_timestamp():
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    ).isoformat(timespec="milliseconds")


def device_available(path):
    path = os.path.abspath(path)
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    if stat.S_ISDIR(mode):
        return False
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError:
        return False
    os.close(descriptor)
    return True


def read_vision_freshness(path, now=None):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return {
            "available": False,
            "age_seconds": None,
            "frame_id": None,
            "timestamp": None,
        }
    try:
        modified = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8") as state_file:
            payload = json.load(state_file)
    except (OSError, ValueError):
        return {
            "available": False,
            "age_seconds": None,
            "frame_id": None,
            "timestamp": None,
        }
    age_seconds = max(
        0.0,
        float(time.time() if now is None else now) - modified,
    )
    return {
        "available": True,
        "age_seconds": round(age_seconds, 3),
        "frame_id": payload.get("frame_id"),
        "timestamp": payload.get("timestamp"),
        "modified_at": modified,
    }


RESTART_REQUEST_PATTERN = re.compile(
    r"^restart_[0-9a-f]{32}$"
)


def read_restart_request(path, last_request_id=None, now=None):
    """Return one fresh, bounded supervisor restart request."""
    path = os.path.abspath(path)
    if not os.path.isfile(path) or os.path.islink(path):
        return None
    try:
        if os.path.getsize(path) > 4096:
            return None
        with open(path, "r", encoding="utf-8") as request_file:
            payload = json.load(request_file)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    request_id = str(payload.get("request_id") or "")
    if (
        not RESTART_REQUEST_PATTERN.match(request_id)
        or request_id == last_request_id
        or payload.get("schema_version") != "1.0"
        or payload.get("action") != "RESTART"
        or payload.get("status") != "REQUESTED"
    ):
        return None
    try:
        requested_at_epoch = float(
            payload["requested_at_epoch"]
        )
        expires_at_epoch = float(payload["expires_at_epoch"])
    except (KeyError, TypeError, ValueError):
        return None
    current_time = float(
        time.time() if now is None else now
    )
    if (
        requested_at_epoch > current_time + 5.0
        or expires_at_epoch <= current_time
        or expires_at_epoch - requested_at_epoch > 60.0
    ):
        return None
    return {
        "request_id": request_id,
        "requested_at": payload.get("requested_at"),
    }


class VisionSupervisor(object):
    def __init__(
        self,
        command,
        device_path,
        state_path,
        vision_state_path,
        retry_seconds=3.0,
        poll_seconds=1.0,
        fresh_seconds=5.0,
        startup_timeout_seconds=120.0,
        lifecycle_events=None,
        control_path=None,
    ):
        if not command:
            raise ValueError("vision worker command is required")
        self.command = list(command)
        self.device_path = os.path.abspath(device_path)
        self.state_path = os.path.abspath(state_path)
        self.vision_state_path = os.path.abspath(
            vision_state_path
        )
        self.retry_seconds = float(retry_seconds)
        self.poll_seconds = float(poll_seconds)
        self.fresh_seconds = float(fresh_seconds)
        self.startup_timeout_seconds = float(
            startup_timeout_seconds
        )
        if (
            self.retry_seconds <= 0
            or self.poll_seconds <= 0
            or self.fresh_seconds <= 0
            or self.startup_timeout_seconds <= 0
        ):
            raise ValueError("supervisor intervals must be positive")
        self.stop_event = threading.Event()
        self.child = None
        self.generation = 0
        self.restart_count = 0
        self.last_exit_code = None
        self.started_at = beijing_timestamp()
        self._last_reported_status = None
        self.lifecycle_events = lifecycle_events
        self.control_path = os.path.abspath(
            control_path
            or os.path.join(
                os.path.dirname(self.state_path),
                "vision-control.json",
            )
        )
        self.last_control_request_id = None
        self.last_control_status = None
        self.last_control_requested_at = None
        self.last_control_completed_at = None
        self._pending_restart_request_id = None
        startup_request = read_restart_request(
            self.control_path
        )
        if startup_request is not None:
            # Never replay a request that predates this supervisor
            # instance, even when it has not expired yet.
            self.last_control_request_id = startup_request[
                "request_id"
            ]

    def request_stop(self, unused_signum=None, unused_frame=None):
        self.stop_event.set()
        self._terminate_child()

    def run(self):
        self._publish("STARTING")
        try:
            while not self.stop_event.is_set():
                if not device_available(self.device_path):
                    self._publish("WAITING_FOR_CAMERA")
                    self.stop_event.wait(self.retry_seconds)
                    continue
                self.generation += 1
                worker_started_at = time.time()
                self._publish(
                    "STARTING",
                    device_is_available=True,
                )
                try:
                    self.child = subprocess.Popen(self.command)
                except OSError:
                    self.child = None
                    self.last_exit_code = 127
                    self.restart_count += 1
                    self._publish(
                        "RESTARTING",
                        device_is_available=True,
                    )
                    self.stop_event.wait(self.retry_seconds)
                    continue
                self._publish(
                    "STARTING",
                    device_is_available=True,
                )
                generation_was_running = False
                while not self.stop_event.is_set():
                    return_code = self.child.poll()
                    if return_code is not None:
                        self.last_exit_code = int(return_code)
                        break
                    restart_request = read_restart_request(
                        self.control_path,
                        last_request_id=(
                            self.last_control_request_id
                        ),
                    )
                    if restart_request is not None:
                        self.last_control_request_id = (
                            restart_request["request_id"]
                        )
                        self.last_control_status = "ACCEPTED"
                        self.last_control_requested_at = (
                            restart_request.get("requested_at")
                        )
                        self.last_control_completed_at = None
                        self._pending_restart_request_id = (
                            restart_request["request_id"]
                        )
                        self._publish(
                            "RESTARTING",
                            device_is_available=True,
                        )
                        self._terminate_child()
                        self.last_exit_code = (
                            self.child.returncode
                            if self.child is not None
                            else None
                        )
                        break
                    if not os.path.exists(self.device_path):
                        self._publish(
                            "CAMERA_OFFLINE",
                            device_is_available=False,
                        )
                        self._terminate_child()
                        self.last_exit_code = (
                            self.child.returncode
                            if self.child is not None
                            else None
                        )
                        break
                    vision = read_vision_freshness(
                        self.vision_state_path
                    )
                    new_generation_frame = (
                        vision.get("available")
                        and vision.get("modified_at", 0)
                        >= worker_started_at
                    )
                    fresh_frame = (
                        new_generation_frame
                        and vision.get("age_seconds", 999999)
                        <= self.fresh_seconds
                    )
                    if fresh_frame:
                        generation_was_running = True
                        if (
                            self._pending_restart_request_id
                            == self.last_control_request_id
                        ):
                            self.last_control_status = "COMPLETED"
                            self.last_control_completed_at = (
                                beijing_timestamp()
                            )
                            self._pending_restart_request_id = None
                    if (
                        generation_was_running
                        and not fresh_frame
                    ):
                        self._publish(
                            "VISION_STALLED",
                            device_is_available=True,
                            vision=vision,
                        )
                        self._terminate_child()
                        self.last_exit_code = (
                            self.child.returncode
                            if self.child is not None
                            else None
                        )
                        break
                    if (
                        not generation_was_running
                        and time.time() - worker_started_at
                        > self.startup_timeout_seconds
                    ):
                        self._publish(
                            "VISION_STALLED",
                            device_is_available=True,
                            vision=vision,
                        )
                        self._terminate_child()
                        self.last_exit_code = (
                            self.child.returncode
                            if self.child is not None
                            else None
                        )
                        break
                    status = (
                        "RUNNING"
                        if fresh_frame
                        else "STARTING"
                    )
                    self._publish(
                        status,
                        device_is_available=True,
                        vision=vision,
                    )
                    self.stop_event.wait(self.poll_seconds)
                if self.stop_event.is_set():
                    break
                self.child = None
                self.restart_count += 1
                self._publish("RESTARTING")
                self.stop_event.wait(self.retry_seconds)
        finally:
            self._terminate_child()
            self.child = None
            self._publish("STOPPED")
        return 0

    def _terminate_child(self):
        child = self.child
        if child is None or child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()

    def _publish(
        self,
        status,
        device_is_available=None,
        vision=None,
    ):
        if device_is_available is None:
            device_is_available = device_available(
                self.device_path
            )
        vision = vision or read_vision_freshness(
            self.vision_state_path
        )
        child_running = (
            self.child is not None
            and self.child.poll() is None
        )
        payload = {
            "schema_version": "1.0",
            "status": str(status),
            "device": self.device_path,
            "device_available": bool(device_is_available),
            "worker_running": child_running,
            "worker_pid": (
                int(self.child.pid) if child_running else None
            ),
            "generation": int(self.generation),
            "restart_count": int(self.restart_count),
            "last_exit_code": self.last_exit_code,
            "started_at": self.started_at,
            "updated_at": beijing_timestamp(),
            "vision": {
                "available": bool(vision.get("available")),
                "age_seconds": vision.get("age_seconds"),
                "frame_id": vision.get("frame_id"),
                "timestamp": vision.get("timestamp"),
            },
            "control": {
                "last_request_id": (
                    self.last_control_request_id
                ),
                "status": self.last_control_status,
                "requested_at": self.last_control_requested_at,
                "completed_at": self.last_control_completed_at,
            },
        }
        write_json_atomic(self.state_path, payload)
        if self.lifecycle_events is not None:
            event = self.lifecycle_events.on_status(
                status,
                payload,
            )
            if event is not None:
                print(
                    "Camera lifecycle event: {0} {1}".format(
                        event.get("event_type"),
                        event.get("event_id"),
                    ),
                    flush=True,
                )
        if status != self._last_reported_status:
            print(
                "Vision supervisor: {0} "
                "generation={1} restarts={2}".format(
                    status,
                    self.generation,
                    self.restart_count,
                ),
                flush=True,
            )
            self._last_reported_status = status
        return payload


def build_parser():
    parser = argparse.ArgumentParser(
        description="Restart the vision worker after camera outages."
    )
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument(
        "--state-output",
        default="data/runtime/vision-supervisor.json",
    )
    parser.add_argument(
        "--vision-state",
        default="data/state/current-vision.json",
    )
    parser.add_argument(
        "--control-input",
        default="data/runtime/vision-control.json",
    )
    parser.add_argument("--retry-seconds", type=float, default=3.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--fresh-seconds", type=float, default=5.0)
    parser.add_argument(
        "--startup-timeout-seconds",
        type=float,
        default=120.0,
    )
    parser.add_argument("--event-output")
    parser.add_argument("--event-db")
    parser.add_argument("--camera-id", default="camera_01")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main():
    args = build_parser().parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit(
            "vision worker command is required after --"
        )
    lifecycle_events = None
    if bool(args.event_output) != bool(args.event_db):
        raise SystemExit(
            "--event-output and --event-db must be used together"
        )
    if args.event_output and args.event_db:
        lifecycle_events = CameraLifecycleEvents(
            CameraLifecycleEventWriter(
                args.event_output,
                args.event_db,
            ),
            camera_id=args.camera_id,
        )
    supervisor = VisionSupervisor(
        command=command,
        device_path=args.device,
        state_path=args.state_output,
        vision_state_path=args.vision_state,
        retry_seconds=args.retry_seconds,
        poll_seconds=args.poll_seconds,
        fresh_seconds=args.fresh_seconds,
        startup_timeout_seconds=args.startup_timeout_seconds,
        lifecycle_events=lifecycle_events,
        control_path=args.control_input,
    )
    signal.signal(signal.SIGTERM, supervisor.request_stop)
    signal.signal(signal.SIGINT, supervisor.request_stop)
    return supervisor.run()


if __name__ == "__main__":
    sys.exit(main())
