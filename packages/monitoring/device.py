"""Dependency-free Linux and Jetson device metrics."""

import glob
import os
import shutil

from packages.vision.schemas import beijing_timestamp


class DeviceMonitor(object):
    API_SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        project_path,
        proc_dir="/proc",
        thermal_dir="/sys/class/thermal",
        statvfs_func=None,
    ):
        self.project_path = os.path.abspath(project_path)
        self.proc_dir = os.path.abspath(proc_dir)
        self.thermal_dir = os.path.abspath(thermal_dir)
        self.statvfs_func = statvfs_func or getattr(
            os,
            "statvfs",
            None,
        )

    def snapshot(self):
        load = self._load_average()
        memory = self._memory()
        disk = self._disk()
        uptime_seconds = self._uptime()
        temperature = self._temperature()
        core_values = (load, memory, disk, uptime_seconds)
        return {
            "schema_version": self.API_SCHEMA_VERSION,
            "status": (
                "ok"
                if all(value is not None for value in core_values)
                else "degraded"
            ),
            "timestamp": beijing_timestamp(),
            "load_average": load,
            "memory": memory,
            "disk": disk,
            "uptime_seconds": uptime_seconds,
            "temperature": temperature,
        }

    def _load_average(self):
        text = self._read_text(
            os.path.join(self.proc_dir, "loadavg")
        )
        if text is None:
            return None
        fields = text.split()
        if len(fields) < 3:
            return None
        try:
            values = [float(value) for value in fields[:3]]
        except ValueError:
            return None
        cpu_count = os.cpu_count() or 1
        return {
            "one_minute": round(values[0], 3),
            "five_minutes": round(values[1], 3),
            "fifteen_minutes": round(values[2], 3),
            "cpu_count": int(cpu_count),
            "normalized_percent": round(
                values[0] / float(cpu_count) * 100.0,
                1,
            ),
        }

    def _memory(self):
        text = self._read_text(
            os.path.join(self.proc_dir, "meminfo")
        )
        if text is None:
            return None
        values = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            name, raw_value = line.split(":", 1)
            fields = raw_value.strip().split()
            if not fields:
                continue
            try:
                values[name] = int(fields[0]) * 1024
            except ValueError:
                continue
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        if not total or available is None:
            return None
        used = max(0, total - available)
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "used_percent": round(
                used / float(total) * 100.0,
                1,
            ),
        }

    def _disk(self):
        try:
            if self.statvfs_func is not None:
                stat = self.statvfs_func(self.project_path)
                block_size = int(stat.f_frsize or stat.f_bsize)
                total = int(stat.f_blocks) * block_size
                free = int(stat.f_bfree) * block_size
                available = int(stat.f_bavail) * block_size
            else:
                usage = shutil.disk_usage(self.project_path)
                total = int(usage.total)
                free = int(usage.free)
                available = free
        except (AttributeError, OSError, TypeError, ValueError):
            return None
        if total <= 0:
            return None
        used = max(0, total - free)
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "used_percent": round(
                used / float(total) * 100.0,
                1,
            ),
        }

    def _uptime(self):
        text = self._read_text(
            os.path.join(self.proc_dir, "uptime")
        )
        if text is None:
            return None
        try:
            return round(float(text.split()[0]), 1)
        except (IndexError, ValueError):
            return None

    def _temperature(self):
        sensors = []
        pattern = os.path.join(
            self.thermal_dir,
            "thermal_zone*",
            "temp",
        )
        for temperature_path in sorted(glob.glob(pattern)):
            raw_value = self._read_text(temperature_path)
            if raw_value is None:
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue
            celsius = value / 1000.0 if abs(value) > 200 else value
            if celsius < -40.0 or celsius > 150.0:
                continue
            sensor_dir = os.path.dirname(temperature_path)
            sensor_type = self._read_text(
                os.path.join(sensor_dir, "type")
            )
            name = (
                sensor_type.strip()[:64]
                if sensor_type
                else os.path.basename(sensor_dir)
            )
            sensors.append(
                {
                    "name": name,
                    "celsius": round(celsius, 1),
                }
            )
        if not sensors:
            return {
                "status": "unavailable",
                "max_celsius": None,
                "sensors": [],
            }
        return {
            "status": "available",
            "max_celsius": max(
                sensor["celsius"] for sensor in sensors
            ),
            "sensors": sensors,
        }

    @staticmethod
    def _read_text(path):
        try:
            with open(path, "r", encoding="utf-8") as input_file:
                return input_file.read().strip()
        except (OSError, UnicodeError):
            return None
