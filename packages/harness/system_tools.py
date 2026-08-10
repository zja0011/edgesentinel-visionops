"""Read-only deterministic Jetson health tool."""

from packages.monitoring.device import DeviceMonitor


class SystemHealthTools(object):
    LOAD_WARNING = 100.0
    LOAD_CRITICAL = 150.0
    MEMORY_WARNING = 85.0
    MEMORY_CRITICAL = 95.0
    DISK_WARNING = 85.0
    DISK_CRITICAL = 95.0
    TEMPERATURE_WARNING = 75.0
    TEMPERATURE_CRITICAL = 85.0

    def __init__(self, project_dir, monitor=None):
        self.monitor = monitor or DeviceMonitor(project_dir)

    def get_health(self, unused_arguments):
        snapshot = self.monitor.snapshot()
        load = snapshot.get("load_average")
        memory = snapshot.get("memory")
        disk = snapshot.get("disk")
        temperature = snapshot.get("temperature") or {}

        checks = {
            "load": self._percent_check(
                None if load is None else load.get(
                    "normalized_percent"
                ),
                self.LOAD_WARNING,
                self.LOAD_CRITICAL,
                extra={
                    "cpu_count": (
                        None if load is None else load.get("cpu_count")
                    ),
                    "one_minute": (
                        None
                        if load is None
                        else load.get("one_minute")
                    ),
                },
            ),
            "memory": self._percent_check(
                None if memory is None else memory.get(
                    "used_percent"
                ),
                self.MEMORY_WARNING,
                self.MEMORY_CRITICAL,
                extra={
                    "available_bytes": (
                        None
                        if memory is None
                        else memory.get("available_bytes")
                    ),
                },
            ),
            "disk": self._percent_check(
                None if disk is None else disk.get("used_percent"),
                self.DISK_WARNING,
                self.DISK_CRITICAL,
                extra={
                    "available_bytes": (
                        None
                        if disk is None
                        else disk.get("available_bytes")
                    ),
                },
            ),
            "temperature": self._temperature_check(temperature),
        }
        status = self._overall_status(checks)
        issues = [
            "{0}:{1}".format(name, check["status"])
            for name, check in sorted(checks.items())
            if check["status"] != "OK"
        ]
        return {
            "schema_version": "1.0",
            "status": status,
            "timestamp": snapshot.get("timestamp"),
            "checks": checks,
            "issues": issues,
            "uptime_seconds": snapshot.get("uptime_seconds"),
            "source_status": snapshot.get("status"),
            "read_only": True,
        }

    @staticmethod
    def _percent_check(
        value,
        warning,
        critical,
        extra=None,
    ):
        status = SystemHealthTools._threshold_status(
            value,
            warning,
            critical,
        )
        payload = {
            "status": status,
            "used_percent": value,
            "warning_at": warning,
            "critical_at": critical,
        }
        payload.update(extra or {})
        return payload

    @classmethod
    def _temperature_check(cls, temperature):
        value = temperature.get("max_celsius")
        return {
            "status": cls._threshold_status(
                value,
                cls.TEMPERATURE_WARNING,
                cls.TEMPERATURE_CRITICAL,
            ),
            "max_celsius": value,
            "warning_at": cls.TEMPERATURE_WARNING,
            "critical_at": cls.TEMPERATURE_CRITICAL,
            "sensor_status": temperature.get(
                "status",
                "unavailable",
            ),
        }

    @staticmethod
    def _threshold_status(value, warning, critical):
        if value is None:
            return "UNKNOWN"
        if float(value) >= float(critical):
            return "CRITICAL"
        if float(value) >= float(warning):
            return "WARNING"
        return "OK"

    @staticmethod
    def _overall_status(checks):
        statuses = {
            check.get("status")
            for check in checks.values()
        }
        if "CRITICAL" in statuses:
            return "CRITICAL"
        if "WARNING" in statuses:
            return "WARNING"
        if "UNKNOWN" in statuses:
            return "DEGRADED"
        return "OK"
