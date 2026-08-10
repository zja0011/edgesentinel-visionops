import os
import tempfile
import unittest

from packages.monitoring.device import DeviceMonitor


class FakeStatvfs(object):
    f_frsize = 4096
    f_bsize = 4096
    f_blocks = 1000
    f_bfree = 250
    f_bavail = 200


class DeviceMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.proc_dir = os.path.join(self.temporary.name, "proc")
        self.thermal_dir = os.path.join(
            self.temporary.name,
            "thermal",
        )
        os.makedirs(self.proc_dir)
        os.makedirs(self.thermal_dir)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def write(path, content):
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, "w", encoding="utf-8") as output_file:
            output_file.write(content)

    def make_monitor(self):
        return DeviceMonitor(
            self.temporary.name,
            proc_dir=self.proc_dir,
            thermal_dir=self.thermal_dir,
            statvfs_func=lambda unused_path: FakeStatvfs(),
        )

    def test_reads_core_linux_metrics(self):
        self.write(
            os.path.join(self.proc_dir, "loadavg"),
            "1.00 0.50 0.25 1/100 42\n",
        )
        self.write(
            os.path.join(self.proc_dir, "meminfo"),
            "MemTotal: 4000 kB\nMemAvailable: 1500 kB\n",
        )
        self.write(
            os.path.join(self.proc_dir, "uptime"),
            "3601.5 1000.0\n",
        )

        payload = self.make_monitor().snapshot()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            payload["load_average"]["one_minute"],
            1.0,
        )
        self.assertEqual(
            payload["memory"]["used_percent"],
            62.5,
        )
        self.assertEqual(
            payload["disk"]["used_percent"],
            75.0,
        )
        self.assertEqual(payload["uptime_seconds"], 3601.5)
        self.assertTrue(payload["timestamp"].endswith("+08:00"))

    def test_reads_and_filters_thermal_sensors(self):
        self.write(
            os.path.join(
                self.thermal_dir,
                "thermal_zone0",
                "type",
            ),
            "CPU-therm\n",
        )
        self.write(
            os.path.join(
                self.thermal_dir,
                "thermal_zone0",
                "temp",
            ),
            "42500\n",
        )
        self.write(
            os.path.join(
                self.thermal_dir,
                "thermal_zone1",
                "temp",
            ),
            "999999\n",
        )

        temperature = self.make_monitor().snapshot()["temperature"]

        self.assertEqual(temperature["status"], "available")
        self.assertEqual(temperature["max_celsius"], 42.5)
        self.assertEqual(
            temperature["sensors"],
            [{"name": "CPU-therm", "celsius": 42.5}],
        )

    def test_missing_proc_metrics_are_degraded(self):
        payload = self.make_monitor().snapshot()

        self.assertEqual(payload["status"], "degraded")
        self.assertIsNone(payload["load_average"])
        self.assertIsNone(payload["memory"])
        self.assertIsNone(payload["uptime_seconds"])
        self.assertEqual(
            payload["temperature"]["status"],
            "unavailable",
        )


if __name__ == "__main__":
    unittest.main()
