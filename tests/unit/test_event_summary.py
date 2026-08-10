import os
import tempfile
import unittest
from datetime import datetime

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.events.summary import EventSummaryService
from packages.vision.schemas import BEIJING_TIMEZONE


def make_event(
    event_id,
    event_type,
    timestamp,
    object_class,
    zone_id,
    severity="INFO",
):
    return Event(
        event_type=event_type,
        timestamp=timestamp,
        frame_id=1,
        camera_id="camera_01",
        zone_id=zone_id,
        zone_name=zone_id,
        track_id=None,
        object_class=object_class,
        severity=severity,
        details={"private": "must-not-be-summarized"},
        evidence_path="/private/evidence.jpg",
        event_id=event_id,
    )


class EventSummaryServiceTests(unittest.TestCase):
    def _service(self, directory):
        path = os.path.join(directory, "events.db")
        store = SqliteEventStore(path)
        store.append(
            make_event(
                "evt_old",
                "ZONE_ENTER",
                "2026-07-28T14:59:59.000+08:00",
                "person",
                "left_zone",
            )
        )
        store.append(
            make_event(
                "evt_one",
                "OBJECT_APPEARED",
                "2026-07-28T15:30:00.000+08:00",
                "bottle",
                "global",
            )
        )
        store.append(
            make_event(
                "evt_two",
                "OBJECT_REMOVED",
                "2026-07-28T15:40:00.000+08:00",
                "bottle",
                "global",
                severity="MEDIUM",
            )
        )
        store.acknowledge(
            "evt_two",
            "2026-07-28T15:45:00.000+08:00",
            acknowledged_by="tester",
        )
        store.append(
            make_event(
                "evt_three",
                "ZONE_EXIT",
                "2026-07-28T15:50:00.000+08:00",
                "person",
                "right_zone",
            )
        )
        store.append(
            make_event(
                "evt_yesterday",
                "ZONE_ENTER",
                "2026-07-27T15:30:00.000+08:00",
                "person",
                "left_zone",
            )
        )
        store.append(
            make_event(
                "evt_last_week_one",
                "OBJECT_APPEARED",
                "2026-07-21T15:30:00.000+08:00",
                "bottle",
                "global",
            )
        )
        store.append(
            make_event(
                "evt_last_week_two",
                "ZONE_EXIT",
                "2026-07-21T15:40:00.000+08:00",
                "person",
                "right_zone",
            )
        )
        store.close()
        return EventSummaryService(
            path,
            now_provider=lambda: datetime(
                2026,
                7,
                28,
                16,
                0,
                tzinfo=BEIJING_TIMEZONE,
            ),
        )

    def test_summarizes_complete_filtered_window(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._service(directory).summarize(
                minutes=60,
                recent_limit=2,
            )

            self.assertEqual(payload["total_events"], 3)
            self.assertEqual(payload["window"]["minutes"], 60)
            self.assertEqual(
                payload["counts"]["by_object_class"],
                [
                    {"name": "bottle", "count": 2},
                    {"name": "person", "count": 1},
                ],
            )
            self.assertEqual(
                payload["counts"]["by_severity"],
                [
                    {"name": "INFO", "count": 2},
                    {"name": "MEDIUM", "count": 1},
                ],
            )
            self.assertEqual(
                [
                    event["event_id"]
                    for event in payload["recent_events"]
                ],
                ["evt_three", "evt_two"],
            )
            self.assertTrue(payload["read_only"])
            serialized = str(payload)
            self.assertNotIn("private", serialized)
            self.assertNotIn("evidence", serialized)
            self.assertNotIn("details", serialized)

    def test_applies_exact_object_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._service(directory).summarize(
                minutes=60,
                object_class="bottle",
            )

            self.assertEqual(payload["total_events"], 2)
            self.assertEqual(
                payload["filters"]["object_class"],
                "bottle",
            )
            self.assertEqual(
                payload["counts"]["by_zone"],
                [{"name": "global", "count": 2}],
            )

    def test_applies_exact_disposition_filter_to_all_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._service(directory).summarize(
                minutes=60,
                status="OPEN",
            )

            self.assertEqual(payload["total_events"], 2)
            self.assertEqual(payload["filters"]["status"], "OPEN")
            self.assertEqual(
                {
                    event["status"]
                    for event in payload["recent_events"]
                },
                {"OPEN"},
            )
            self.assertEqual(
                payload["counts"]["by_object_class"],
                [
                    {"name": "bottle", "count": 1},
                    {"name": "person", "count": 1},
                ],
            )

    def test_applies_exact_severity_filter_to_all_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._service(directory).summarize(
                minutes=60,
                severity="INFO",
            )

            self.assertEqual(payload["total_events"], 2)
            self.assertEqual(
                payload["filters"]["severity"],
                "INFO",
            )
            self.assertEqual(
                {
                    event["severity"]
                    for event in payload["recent_events"]
                },
                {"INFO"},
            )
            self.assertEqual(
                payload["counts"]["by_severity"],
                [{"name": "INFO", "count": 2}],
            )

    def test_builds_complete_beijing_timeline_buckets(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._service(directory).summarize(
                minutes=60,
                bucket_minutes=15,
            )

            timeline = payload["timeline"]
            self.assertEqual(timeline["bucket_minutes"], 15)
            self.assertEqual(
                timeline["timezone"],
                "Asia/Shanghai",
            )
            self.assertEqual(len(timeline["buckets"]), 5)
            self.assertEqual(
                timeline["buckets"][0]["start"],
                "2026-07-28T15:00:00.000+08:00",
            )
            self.assertEqual(
                timeline["buckets"][-1]["start"],
                "2026-07-28T16:00:00.000+08:00",
            )
            self.assertEqual(
                sum(
                    bucket["count"]
                    for bucket in timeline["buckets"]
                ),
                payload["total_events"],
            )
            self.assertEqual(
                [
                    bucket["count"]
                    for bucket in timeline["buckets"]
                ],
                [0, 0, 2, 1, 0],
            )

    def test_rejects_unknown_timeline_bucket_size(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self._service(directory).summarize(
                    minutes=60,
                    bucket_minutes=20,
                )

    def test_compares_with_previous_equal_length_window(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            payload = service.summarize(
                minutes=60,
                compare_previous=True,
            )

            comparison = payload["comparison"]
            self.assertEqual(comparison["current_total"], 3)
            self.assertEqual(comparison["previous_total"], 1)
            self.assertEqual(comparison["absolute_change"], 2)
            self.assertEqual(comparison["percent_change"], 200.0)
            self.assertEqual(
                comparison["direction"],
                "INCREASE",
            )
            self.assertEqual(
                comparison["previous_window"],
                {
                    "minutes": 60,
                    "offset_minutes": 60,
                    "alignment": "ADJACENT",
                    "since_timestamp": (
                        "2026-07-28T14:00:00.000+08:00"
                    ),
                    "until_timestamp": (
                        "2026-07-28T15:00:00.000+08:00"
                    ),
                    "timezone": "Asia/Shanghai",
                },
            )
            aligned = service.summarize(
                minutes=60,
                compare_previous=True,
                comparison_offset_minutes=1440,
            )
            self.assertEqual(
                aligned["comparison"]["previous_window"],
                {
                    "minutes": 60,
                    "offset_minutes": 1440,
                    "alignment": "OFFSET",
                    "since_timestamp": (
                        "2026-07-27T15:00:00.000+08:00"
                    ),
                    "until_timestamp": (
                        "2026-07-27T16:00:00.000+08:00"
                    ),
                    "timezone": "Asia/Shanghai",
                },
            )
            self.assertEqual(
                aligned["comparison"]["previous_total"],
                1,
            )
            event_type_changes = comparison[
                "contributors"
            ]["by_event_type"]
            self.assertEqual(
                {
                    item["name"]: item["absolute_change"]
                    for item in event_type_changes
                },
                {
                    "OBJECT_APPEARED": 1,
                    "OBJECT_REMOVED": 1,
                    "ZONE_ENTER": -1,
                    "ZONE_EXIT": 1,
                },
            )
            self.assertEqual(
                comparison["largest_event_type_change"],
                event_type_changes[0],
            )
            self.assertEqual(
                comparison["contributors"]["by_object_class"][0],
                {
                    "name": "bottle",
                    "current_count": 2,
                    "previous_count": 0,
                    "absolute_change": 2,
                    "percent_change": None,
                    "direction": "INCREASE",
                    "status": "INSUFFICIENT_BASELINE",
                    "threshold_exceeded": False,
                    "reason": (
                        "BASELINE_ZERO_AND_ACTIVITY_BELOW_MINIMUM"
                    ),
                },
            )

            self.assertEqual(
                comparison["assessment"],
                {
                    "status": "WITHIN_THRESHOLD",
                    "threshold_exceeded": False,
                    "reason": "ABSOLUTE_CHANGE_BELOW_MINIMUM",
                    "minimum_absolute_change": 10,
                    "minimum_percent_change": 25.0,
                    "observed_absolute_change": 2,
                    "observed_percent_change": 200.0,
                },
            )
            self.assertEqual(
                comparison["structural_change"][
                    "by_event_type"
                ],
                {
                    "status": "OPPOSING_CHANGES",
                    "complete": True,
                    "gross_absolute_change": 4,
                    "net_change": 2,
                    "net_absolute_change": 2,
                    "net_matches_total": True,
                    "offsetting_events": 1,
                    "masked_share_percent": 50.0,
                    "increasing_groups": 3,
                    "decreasing_groups": 1,
                    "significant_groups": 0,
                    "masked_significant_change": False,
                },
            )
            sensitive = service.summarize(
                minutes=60,
                compare_previous=True,
                change_threshold_percent=100,
                change_threshold_events=2,
            )
            self.assertEqual(
                sensitive["comparison"]["assessment"]["status"],
                "SIGNIFICANT_CHANGE",
            )
            self.assertTrue(
                sensitive["comparison"]["assessment"][
                    "threshold_exceeded"
                ]
            )
            self.assertEqual(
                sensitive["comparison"][
                    "significant_contributors"
                ]["by_object_class"][0]["name"],
                "bottle",
            )
            cancelled = service._compare_groups(
                {
                    "event_type": [
                        {"name": "ZONE_ENTER", "count": 10},
                        {"name": "ZONE_EXIT", "count": 0},
                    ]
                },
                {
                    "event_type": [
                        {"name": "ZONE_ENTER", "count": 0},
                        {"name": "ZONE_EXIT", "count": 10},
                    ]
                },
                minimum_percent=25,
                minimum_events=5,
            )
            self.assertEqual(
                [
                    item["name"]
                    for item in cancelled["by_event_type"]
                    if item["threshold_exceeded"]
                ],
                ["ZONE_ENTER", "ZONE_EXIT"],
            )
            cancelled_structure = service._structural_changes(
                contributors=cancelled,
                current_truncated={
                    "event_type": False,
                    "severity": False,
                    "object_class": False,
                    "zone_id": False,
                },
                previous_truncated={
                    "event_type": False,
                    "severity": False,
                    "object_class": False,
                    "zone_id": False,
                },
                total_change=0,
                overall_threshold_exceeded=False,
            )
            self.assertEqual(
                cancelled_structure["by_event_type"],
                {
                    "status": "MASKED_SIGNIFICANT_CHANGE",
                    "complete": True,
                    "gross_absolute_change": 20,
                    "net_change": 0,
                    "net_absolute_change": 0,
                    "net_matches_total": True,
                    "offsetting_events": 10,
                    "masked_share_percent": 100.0,
                    "increasing_groups": 1,
                    "decreasing_groups": 1,
                    "significant_groups": 2,
                    "masked_significant_change": True,
                },
            )
            partial_structure = service._structural_changes(
                contributors=cancelled,
                current_truncated={
                    "event_type": True,
                },
                previous_truncated={
                    "event_type": False,
                },
                total_change=0,
                overall_threshold_exceeded=False,
            )
            self.assertEqual(
                partial_structure["by_event_type"]["status"],
                "PARTIAL",
            )
            self.assertFalse(
                partial_structure["by_event_type"]["complete"]
            )
            self.assertFalse(
                partial_structure["by_event_type"][
                    "net_matches_total"
                ]
            )

    def test_builds_fixed_yesterday_and_last_week_baselines(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            payload = service.summarize(
                minutes=60,
                include_reference_baselines=True,
            )

            profile = payload["reference_baselines"]
            self.assertEqual(profile["status"], "AVAILABLE")
            self.assertEqual(profile["window_minutes"], 60)
            self.assertEqual(profile["timezone"], "Asia/Shanghai")
            self.assertEqual(profile["current_total"], 3)
            self.assertEqual(profile["baseline_count"], 2)
            self.assertEqual(profile["baseline_average_total"], 1.5)
            self.assertEqual(profile["change_from_average"], 1.5)
            self.assertEqual(
                profile["percent_change_from_average"],
                100.0,
            )
            self.assertEqual(profile["direction"], "INCREASE")
            self.assertEqual(
                profile["assessment"],
                {
                    "status": "ABOVE_HISTORICAL_AVERAGE",
                    "reason": "CURRENT_TOTAL_ABOVE_HISTORY",
                    "historical_activity_available": True,
                    "current_activity": True,
                },
            )
            self.assertEqual(
                profile["consistency"],
                {
                    "status": "VARIABLE",
                    "reason": "SPREAD_EXCEEDS_THRESHOLD",
                    "minimum_total": 1,
                    "maximum_total": 2,
                    "spread": 1,
                    "spread_percent": 66.67,
                    "maximum_stable_spread_percent": 50,
                    "reliable_for_average": False,
                },
            )
            self.assertTrue(profile["complete"])
            self.assertEqual(
                profile["baselines"],
                [
                    {
                        "label": "SAME_TIME_YESTERDAY",
                        "minutes": 60,
                        "offset_minutes": 1440,
                        "since_timestamp": (
                            "2026-07-27T15:00:00.000+08:00"
                        ),
                        "until_timestamp": (
                            "2026-07-27T16:00:00.000+08:00"
                        ),
                        "timezone": "Asia/Shanghai",
                        "total_events": 1,
                    },
                    {
                        "label": "SAME_TIME_LAST_WEEK",
                        "minutes": 60,
                        "offset_minutes": 10080,
                        "since_timestamp": (
                            "2026-07-21T15:00:00.000+08:00"
                        ),
                        "until_timestamp": (
                            "2026-07-21T16:00:00.000+08:00"
                        ),
                        "timezone": "Asia/Shanghai",
                        "total_events": 2,
                    },
                ],
            )
            empty = service.summarize(
                minutes=60,
                object_class="camera",
                include_reference_baselines=True,
            )["reference_baselines"]
            self.assertEqual(empty["baseline_average_total"], 0.0)
            self.assertEqual(empty["change_from_average"], 0.0)
            self.assertIsNone(
                empty["percent_change_from_average"]
            )
            self.assertEqual(empty["direction"], "UNCHANGED")
            self.assertEqual(
                empty["assessment"]["status"],
                "NO_HISTORICAL_ACTIVITY",
            )
            self.assertFalse(
                empty["assessment"][
                    "historical_activity_available"
                ]
            )
            self.assertEqual(
                empty["consistency"]["status"],
                "NO_HISTORICAL_ACTIVITY",
            )
            self.assertIsNone(
                empty["consistency"]["spread_percent"]
            )
            self.assertFalse(
                empty["consistency"]["reliable_for_average"]
            )
            new_activity = service.summarize(
                minutes=60,
                severity="MEDIUM",
                include_reference_baselines=True,
            )["reference_baselines"]
            self.assertEqual(
                new_activity["assessment"]["status"],
                "NEW_ACTIVITY",
            )
            self.assertEqual(
                EventSummaryService._assess_reference_baselines(
                    current_total=1,
                    baseline_average=2.0,
                    change_from_average=-1.0,
                )["status"],
                "BELOW_HISTORICAL_AVERAGE",
            )
            self.assertEqual(
                EventSummaryService._assess_reference_baselines(
                    current_total=2,
                    baseline_average=2.0,
                    change_from_average=0.0,
                )["status"],
                "MATCHES_HISTORICAL_AVERAGE",
            )
            stable = (
                EventSummaryService._assess_reference_consistency(
                    baseline_totals=[10, 11],
                    baseline_average=10.5,
                )
            )
            self.assertEqual(stable["status"], "STABLE")
            self.assertEqual(
                stable["reason"],
                "SPREAD_WITHIN_THRESHOLD",
            )
            self.assertTrue(stable["reliable_for_average"])
            exact = (
                EventSummaryService._assess_reference_consistency(
                    baseline_totals=[2, 2],
                    baseline_average=2.0,
                )
            )
            self.assertEqual(exact["status"], "STABLE")
            self.assertEqual(
                exact["reason"],
                "REFERENCE_TOTALS_MATCH",
            )

    def test_comparison_inherits_exact_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            payload = service.summarize(
                minutes=60,
                object_class="bottle",
                severity="MEDIUM",
                compare_previous=True,
            )

            self.assertEqual(payload["total_events"], 1)
            self.assertEqual(
                payload["comparison"]["previous_total"],
                0,
            )
            self.assertEqual(
                payload["comparison"]["absolute_change"],
                1,
            )
            self.assertIsNone(
                payload["comparison"]["percent_change"]
            )
            self.assertEqual(
                payload["comparison"]["contributors"][
                    "by_event_type"
                ],
                [
                    {
                        "name": "OBJECT_REMOVED",
                        "current_count": 1,
                        "previous_count": 0,
                        "absolute_change": 1,
                        "percent_change": None,
                        "direction": "INCREASE",
                        "status": "INSUFFICIENT_BASELINE",
                        "threshold_exceeded": False,
                        "reason": (
                            "BASELINE_ZERO_AND_ACTIVITY_BELOW_MINIMUM"
                        ),
                    }
                ],
            )
            self.assertEqual(
                payload["comparison"]["assessment"]["status"],
                "INSUFFICIENT_BASELINE",
            )
            new_activity = service.summarize(
                minutes=60,
                object_class="bottle",
                severity="MEDIUM",
                compare_previous=True,
                change_threshold_events=1,
            )
            self.assertEqual(
                new_activity["comparison"]["assessment"]["status"],
                "NEW_ACTIVITY",
            )
            self.assertTrue(
                new_activity["comparison"]["assessment"][
                    "threshold_exceeded"
                ]
            )
            self.assertEqual(
                new_activity["comparison"][
                    "significant_event_type_count"
                ],
                1,
            )
            self.assertEqual(
                new_activity["comparison"][
                    "largest_significant_event_type_change"
                ]["name"],
                "OBJECT_REMOVED",
            )

    def test_validates_recent_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            for limit in (0, 11):
                with self.assertRaises(ValueError):
                    service.summarize(recent_limit=limit)
            for threshold in (0, 501):
                with self.assertRaises(ValueError):
                    service.summarize(
                        change_threshold_percent=threshold
                    )
            for threshold in (0, 1001):
                with self.assertRaises(ValueError):
                    service.summarize(
                        change_threshold_events=threshold
                    )
            with self.assertRaises(ValueError):
                service.summarize(
                    minutes=60,
                    comparison_offset_minutes=1440,
                )
            with self.assertRaises(ValueError):
                service.summarize(
                    minutes=60,
                    compare_previous=True,
                    comparison_offset_minutes=59,
                )
            with self.assertRaises(ValueError):
                service.summarize(
                    minutes=60,
                    compare_previous=True,
                    comparison_offset_minutes=10081,
                )


if __name__ == "__main__":
    unittest.main()
