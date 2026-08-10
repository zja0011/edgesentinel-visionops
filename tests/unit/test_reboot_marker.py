import json
import os
import tempfile
import unittest

from apps.reboot_marker import (
    RebootMarkerError,
    prepare_marker,
    verify_reboot,
)


class RebootMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project_dir = self.temporary.name
        self.runtime_dir = os.path.join(
            self.project_dir,
            "data",
            "runtime",
        )
        self.state_dir = os.path.join(
            self.project_dir,
            "data",
            "state",
        )
        os.makedirs(self.runtime_dir)
        os.makedirs(self.state_dir)
        self.marker_path = os.path.join(
            self.runtime_dir,
            "reboot-preflight.json",
        )
        self.boot_id_path = os.path.join(
            self.temporary.name,
            "boot_id",
        )
        self.uptime_path = os.path.join(
            self.temporary.name,
            "uptime",
        )
        self.tls_certificate_path = os.path.join(
            self.temporary.name,
            "server.crt",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_runtime(
        self,
        started_at,
        pid=12,
        frame_id=34,
        tls_enabled=False,
    ):
        with open(
            os.path.join(self.runtime_dir, "service.json"),
            "w",
            encoding="utf-8",
        ) as state_file:
            json.dump(
                {
                    "status": "running",
                    "started_at": started_at,
                    "pid": pid,
                    "config_save_enabled": False,
                    "model_mode": "remote",
                    "tls_enabled": tls_enabled,
                    "tls_public_origin": (
                        "https://192.168.1.101:8443"
                        if tls_enabled
                        else None
                    ),
                },
                state_file,
            )
        with open(
            os.path.join(
                self.state_dir,
                "current-vision.json",
            ),
            "w",
            encoding="utf-8",
        ) as vision_file:
            json.dump(
                {
                    "frame_id": frame_id,
                    "timestamp": started_at,
                },
                vision_file,
            )

    def write_system(self, boot_id, uptime):
        with open(
            self.boot_id_path,
            "w",
            encoding="utf-8",
        ) as boot_file:
            boot_file.write(boot_id)
        with open(
            self.uptime_path,
            "w",
            encoding="utf-8",
        ) as uptime_file:
            uptime_file.write("{} 0.0\n".format(uptime))

    def prepare(self):
        return prepare_marker(
            marker_path=self.marker_path,
            project_dir=self.project_dir,
            boot_id_path=self.boot_id_path,
            uptime_path=self.uptime_path,
            tls_certificate_path=self.tls_certificate_path,
        )

    def verify(self):
        return verify_reboot(
            marker_path=self.marker_path,
            project_dir=self.project_dir,
            boot_id_path=self.boot_id_path,
            uptime_path=self.uptime_path,
            tls_certificate_path=self.tls_certificate_path,
        )

    def test_prepare_records_safe_pre_reboot_identity(self):
        self.write_runtime("2026-07-26T18:00:00+08:00")
        self.write_system("boot-before", 5000)

        marker = self.prepare()
        rendered = json.dumps(marker).lower()

        self.assertEqual(marker["before"]["boot_id"], "boot-before")
        self.assertEqual(marker["before"]["vision_frame_id"], 34)
        self.assertFalse(marker["contains_secret"])
        self.assertNotIn("token", rendered)
        self.assertNotIn("password", rendered)

    def test_verify_requires_a_new_boot_and_service_start(self):
        self.write_runtime("2026-07-26T18:00:00+08:00")
        self.write_system("boot-before", 5000)
        self.prepare()
        self.write_runtime(
            "2026-07-26T18:10:00+08:00",
            pid=15,
            frame_id=20,
        )
        self.write_system("boot-after", 80)

        result = self.verify()

        self.assertTrue(result["boot_changed"])
        self.assertTrue(result["service_restarted"])
        self.assertTrue(result["uptime_reset"])
        self.assertEqual(result["after"]["boot_id"], "boot-after")

    def test_verify_rejects_same_host_boot(self):
        self.write_runtime("2026-07-26T18:00:00+08:00")
        self.write_system("same-boot", 5000)
        self.prepare()
        self.write_runtime("2026-07-26T18:10:00+08:00")
        self.write_system("same-boot", 5100)

        with self.assertRaises(RebootMarkerError):
            self.verify()

    def test_verify_proves_tls_identity_survived_reboot(self):
        with open(self.tls_certificate_path, "wb") as certificate:
            certificate.write(b"safe-public-certificate")
        self.write_runtime(
            "2026-07-26T18:00:00+08:00",
            tls_enabled=True,
        )
        self.write_system("boot-before", 5000)
        marker = self.prepare()
        self.write_runtime(
            "2026-07-26T18:10:00+08:00",
            pid=15,
            frame_id=20,
            tls_enabled=True,
        )
        self.write_system("boot-after", 80)

        result = self.verify()

        self.assertTrue(result["tls_recovered"])
        self.assertTrue(result["tls_certificate_unchanged"])
        self.assertEqual(
            marker["before"]["tls_certificate_sha256"],
            result["after"]["tls_certificate_sha256"],
        )
        self.assertNotIn("private", json.dumps(result).lower())

    def test_verify_rejects_changed_tls_certificate(self):
        with open(self.tls_certificate_path, "wb") as certificate:
            certificate.write(b"certificate-before")
        self.write_runtime(
            "2026-07-26T18:00:00+08:00",
            tls_enabled=True,
        )
        self.write_system("boot-before", 5000)
        self.prepare()
        with open(self.tls_certificate_path, "wb") as certificate:
            certificate.write(b"certificate-after")
        self.write_runtime(
            "2026-07-26T18:10:00+08:00",
            tls_enabled=True,
        )
        self.write_system("boot-after", 80)

        with self.assertRaises(RebootMarkerError):
            self.verify()

    def test_read_write_mode_cannot_create_a_reboot_marker(self):
        self.write_runtime("2026-07-26T18:00:00+08:00")
        self.write_system("boot-before", 5000)
        state_path = os.path.join(
            self.runtime_dir,
            "service.json",
        )
        with open(state_path, "r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        state["config_save_enabled"] = True
        with open(state_path, "w", encoding="utf-8") as state_file:
            json.dump(state, state_file)

        with self.assertRaises(RebootMarkerError):
            self.prepare()


if __name__ == "__main__":
    unittest.main()
