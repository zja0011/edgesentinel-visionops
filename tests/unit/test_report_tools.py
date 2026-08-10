import hashlib
import json
import os
import tempfile
import unittest

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.harness.default_tools import build_default_registry
from packages.harness.registry import ToolInvocationError
from packages.harness.report_tools import (
    DailyEventReportTools,
    ReportGenerationUnavailable,
)


def append_event(
    store,
    event_id,
    timestamp,
    event_type,
    severity="INFO",
    object_class="person",
    camera_id="camera_01",
):
    store.append(
        Event(
            event_type=event_type,
            severity=severity,
            timestamp=timestamp,
            frame_id=10,
            camera_id=camera_id,
            zone_id="left_zone",
            zone_name="Left Zone",
            track_id=7,
            object_class=object_class,
            event_id=event_id,
            evidence_path="data/evidence/{0}.jpg".format(
                event_id
            ),
        )
    )


class DailyEventReportToolsTests(unittest.TestCase):
    def _database(self, directory):
        path = os.path.join(directory, "events.db")
        store = SqliteEventStore(path)
        append_event(
            store,
            "evt_enter",
            "2026-07-27T09:00:00.000+08:00",
            "ZONE_ENTER",
        )
        append_event(
            store,
            "evt_dwell",
            "2026-07-27T09:00:20.000+08:00",
            "ZONE_DWELL",
            severity="MEDIUM",
        )
        append_event(
            store,
            "evt_old",
            "2026-07-26T18:00:00.000+08:00",
            "ZONE_EXIT",
        )
        store.close()
        return path

    def test_generates_utf8_daily_markdown_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self._database(directory)
            tools = DailyEventReportTools(
                directory,
                database,
                clock=lambda: (
                    "2026-07-27T10:00:00.000+08:00"
                ),
            )

            result = tools.generate({})
            path = os.path.join(
                directory,
                *result["report_path"].split("/"),
            )
            with open(path, "rb") as report_file:
                content = report_file.read()
            text = content.decode("utf-8")

            self.assertEqual(result["date"], "2026-07-27")
            self.assertEqual(result["event_count"], 2)
            self.assertFalse(result["truncated"])
            self.assertTrue(
                result["report_path"].startswith(
                    "data/reports/2026-07-27/"
                )
            )
            self.assertEqual(result["bytes"], len(content))
            self.assertEqual(
                result["sha256"],
                hashlib.sha256(content).hexdigest(),
            )
            self.assertIn("每日事件报告", text)
            self.assertIn("长时间停留", text)
            self.assertIn("evt_dwell", text)
            self.assertNotIn("evt_old", text)

    def test_filters_report_by_camera_and_object_class(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self._database(directory)
            tools = DailyEventReportTools(directory, database)

            result = tools.generate(
                {
                    "date": "2026-07-27",
                    "camera_id": "camera_01",
                    "object_class": "person",
                }
            )

            self.assertEqual(result["event_count"], 2)
            self.assertEqual(
                result["filters"],
                {
                    "camera_id": "camera_01",
                    "object_class": "person",
                },
            )

    def test_generates_a_valid_report_when_the_day_has_no_events(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self._database(directory)
            tools = DailyEventReportTools(directory, database)

            result = tools.generate({"date": "2026-07-28"})
            path = os.path.join(
                directory,
                *result["report_path"].split("/"),
            )
            with open(
                path,
                "r",
                encoding="utf-8",
            ) as report_file:
                text = report_file.read()

            self.assertEqual(result["event_count"], 0)
            self.assertGreater(result["bytes"], 0)
            self.assertIn("报告事件数：0", text)
            self.assertIn("| 无事件 | 0 |", text)

    def test_rejects_an_invalid_calendar_date(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self._database(directory)
            tools = DailyEventReportTools(directory, database)

            with self.assertRaises(ReportGenerationUnavailable):
                tools.generate({"date": "2026-02-30"})

    def test_registry_requires_confirmation_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            database = self._database(directory)
            audit_path = os.path.join(directory, "audit.jsonl")
            registry = build_default_registry(
                directory,
                database,
                audit_path=audit_path,
            )

            with self.assertRaises(ToolInvocationError) as denied:
                registry.invoke(
                    "report.generate",
                    {"date": "2026-07-27"},
                )

            self.assertEqual(
                denied.exception.message,
                "CONFIRMATION_REQUIRED",
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(directory, "data", "reports")
                )
            )
            response = registry.invoke(
                "report.generate",
                {"date": "2026-07-27"},
                confirmation_granted=True,
            )

            self.assertEqual(response["status"], "SUCCEEDED")
            self.assertEqual(
                response["result"]["event_count"],
                2,
            )
            with open(
                audit_path,
                "r",
                encoding="utf-8",
            ) as audit_file:
                records = [
                    json.loads(line) for line in audit_file
                ]
            self.assertEqual(len(records), 2)
            self.assertEqual(
                records[1]["result_summary"]["report_id"],
                response["result"]["report_id"],
            )


if __name__ == "__main__":
    unittest.main()
