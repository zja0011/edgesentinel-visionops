import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from packages.api.zone_service import (
    ZoneAuthenticationFailed,
    ZoneConfigUnavailable,
    ZoneQueryService,
    ZoneSaveDisabled,
    ZoneValidationFailed,
    ZoneVersionConflict,
)


class ZoneQueryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = os.path.join(
            self.temporary.name,
            "zones.json",
        )
        self.default_path = os.path.join(
            self.temporary.name,
            "zones.default.json",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, payload):
        with open(self.path, "w", encoding="utf-8") as output:
            json.dump(payload, output)

    def write_default(self, payload):
        with open(
            self.default_path,
            "w",
            encoding="utf-8",
        ) as output:
            json.dump(payload, output)

    @staticmethod
    def zone(
        zone_id="desk",
        polygon=None,
    ):
        return {
            "id": zone_id,
            "name": "Desk",
            "polygon": polygon or [
                [0.1, 0.2],
                [0.9, 0.2],
                [0.9, 0.8],
            ],
            "target_classes": ["person"],
            "anchor": "bottom_center",
            "minimum_hits": 3,
            "max_missed_frames": 2,
        }

    def save_payload(self, service, zones=None):
        return {
            "expected_version": (
                service.get_zones()["config_version"]
            ),
            "confirmation": "SAVE_ZONE_CONFIG",
            "coordinate_space": "normalized",
            "zones": zones or [self.zone()],
        }

    def test_returns_validated_normalized_zones(self):
        self.write(
            {
                "coordinate_space": "normalized",
                "zones": [
                    {
                        "id": "desk",
                        "name": "Desk",
                        "polygon": [
                            [0.1, 0.2],
                            [0.9, 0.2],
                            [0.9, 0.8],
                        ],
                        "target_classes": ["person"],
                        "anchor": "bottom_center",
                        "minimum_hits": 3,
                        "max_missed_frames": 2,
                    }
                ],
            }
        )

        payload = ZoneQueryService(self.path).get_zones()

        self.assertEqual(payload["coordinate_space"], "normalized")
        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["zones"][0]["id"], "desk")
        self.assertEqual(
            payload["zones"][0]["polygon"][0],
            [0.1, 0.2],
        )
        self.assertEqual(len(payload["config_version"]), 64)
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["save_enabled"])
        self.assertNotIn("admin_token", payload)

    def test_rejects_missing_and_invalid_configuration(self):
        service = ZoneQueryService(self.path)
        with self.assertRaises(ZoneConfigUnavailable):
            service.get_zones()

        self.write(
            {
                "coordinate_space": "pixels",
                "zones": [],
            }
        )
        with self.assertRaises(ZoneConfigUnavailable):
            service.get_zones()

    def test_rejects_out_of_range_polygon(self):
        self.write(
            {
                "coordinate_space": "normalized",
                "zones": [
                    {
                        "id": "invalid",
                        "polygon": [
                            [0, 0],
                            [1.1, 0],
                            [0, 1],
                        ],
                    }
                ],
            }
        )

        with self.assertRaises(ZoneConfigUnavailable):
            ZoneQueryService(self.path).get_zones()

    def test_save_is_disabled_without_a_strong_admin_token(self):
        self.write(
            {
                "coordinate_space": "normalized",
                "zones": [self.zone()],
            }
        )
        service = ZoneQueryService(
            self.path,
            admin_token="too-short",
        )

        with self.assertRaises(ZoneSaveDisabled):
            service.save_zones({}, "too-short")

    def test_returns_separate_validated_factory_defaults(self):
        current = {
            "coordinate_space": "normalized",
            "zones": [self.zone(polygon=[
                [0.2, 0.2],
                [0.8, 0.2],
                [0.8, 0.8],
            ])],
        }
        defaults = {
            "coordinate_space": "normalized",
            "zones": [self.zone(polygon=[
                [0.0, 0.0],
                [0.49, 0.0],
                [0.49, 1.0],
                [0.0, 1.0],
            ])],
        }
        self.write(current)
        self.write_default(defaults)
        service = ZoneQueryService(
            self.path,
            default_config_path=self.default_path,
        )

        payload = service.get_default_zones()

        self.assertEqual(payload["source"], "factory_default")
        self.assertTrue(payload["read_only"])
        self.assertEqual(len(payload["default_version"]), 64)
        self.assertEqual(
            payload["zones"][0]["polygon"],
            defaults["zones"][0]["polygon"],
        )
        self.assertNotEqual(
            payload["zones"][0]["polygon"],
            service.get_zones()["zones"][0]["polygon"],
        )

    def test_rejects_missing_factory_defaults(self):
        self.write(
            {
                "coordinate_space": "normalized",
                "zones": [self.zone()],
            }
        )
        service = ZoneQueryService(
            self.path,
            default_config_path=self.default_path,
        )

        with self.assertRaises(ZoneConfigUnavailable):
            service.get_default_zones()

    def test_save_rejects_wrong_token_and_confirmation(self):
        self.write(
            {
                "coordinate_space": "normalized",
                "zones": [self.zone()],
            }
        )
        service = ZoneQueryService(
            self.path,
            admin_token="correct-token-123",
        )
        payload = self.save_payload(service)

        with self.assertRaises(ZoneAuthenticationFailed):
            service.save_zones(payload, "incorrect-token")

        payload["confirmation"] = "yes"
        with self.assertRaises(ZoneValidationFailed):
            service.save_zones(payload, "correct-token-123")

    def test_save_backs_up_and_atomically_replaces_configuration(self):
        original = {
            "coordinate_space": "normalized",
            "zones": [self.zone()],
        }
        self.write(original)
        fixed_time = datetime(
            2026,
            7,
            26,
            10,
            11,
            12,
            123000,
            tzinfo=timezone(timedelta(hours=8)),
        )
        service = ZoneQueryService(
            self.path,
            admin_token="correct-token-123",
            clock=lambda: fixed_time,
        )
        replacement = self.zone(
            polygon=[
                [0.2, 0.2],
                [0.8, 0.2],
                [0.8, 0.7],
                [0.2, 0.7],
            ]
        )
        old_version = service.get_zones()["config_version"]

        response = service.save_zones(
            self.save_payload(service, [replacement]),
            "correct-token-123",
        )

        self.assertTrue(response["saved"])
        self.assertFalse(response["restart_required"])
        self.assertTrue(response["hot_reload_expected"])
        self.assertTrue(response["save_enabled"])
        self.assertFalse(response["read_only"])
        self.assertNotEqual(
            response["config_version"],
            old_version,
        )
        self.assertIn("+08:00", response["saved_at"])
        self.assertTrue(
            response["backup_path"].endswith(
                "zones-20260726T101112123000+0800.json"
            )
        )
        with open(self.path, "r", encoding="utf-8") as config:
            saved = json.load(config)
        self.assertEqual(
            saved["zones"][0]["polygon"],
            replacement["polygon"],
        )
        backup_path = os.path.join(
            self.temporary.name,
            "backups",
            os.path.basename(response["backup_path"]),
        )
        with open(backup_path, "r", encoding="utf-8") as backup:
            self.assertEqual(json.load(backup), original)

    def test_save_rejects_stale_version_without_changing_file(self):
        original = {
            "coordinate_space": "normalized",
            "zones": [self.zone()],
        }
        self.write(original)
        service = ZoneQueryService(
            self.path,
            admin_token="correct-token-123",
        )
        payload = self.save_payload(service)
        payload["expected_version"] = "0" * 64

        with self.assertRaises(ZoneVersionConflict):
            service.save_zones(payload, "correct-token-123")

        with open(self.path, "r", encoding="utf-8") as config:
            self.assertEqual(json.load(config), original)
        self.assertFalse(
            os.path.exists(
                os.path.join(self.temporary.name, "backups")
            )
        )

    def test_save_rejects_degenerate_and_self_intersecting_polygons(self):
        self.write(
            {
                "coordinate_space": "normalized",
                "zones": [self.zone()],
            }
        )
        service = ZoneQueryService(
            self.path,
            admin_token="correct-token-123",
        )

        for polygon in (
            [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]],
            [
                [0.1, 0.1],
                [0.9, 0.9],
                [0.9, 0.1],
                [0.1, 0.9],
            ],
        ):
            with self.assertRaises(ZoneValidationFailed):
                service.save_zones(
                    self.save_payload(
                        service,
                        [self.zone(polygon=polygon)],
                    ),
                    "correct-token-123",
                )


if __name__ == "__main__":
    unittest.main()
