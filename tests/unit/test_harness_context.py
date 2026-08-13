import json
import os
import tempfile
import unittest

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.harness.context import ContextEngine
from packages.harness.utf8 import normalize_cli_text
from packages.vision.state_store import CurrentVisionStateStore


TOOLS = [
    {
        "name": "event.query",
        "description": "query events",
        "annotations": {
            "riskLevel": "L0",
            "autoExecute": True,
            "requiresConfirmation": False,
        },
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
    }
]


def make_state():
    return {
        "frame_id": 20,
        "timestamp": "2026-07-25T16:30:00.000+08:00",
        "camera_id": "camera_01",
        "detections": [{"bbox": [1, 2, 3, 4]}],
        "analytics": {
            "people": {
                "current_people": 1,
                "visible_people": 1,
            },
            "inventory": {
                "current_counts": {
                    "bottle": 1,
                    "cup": 0,
                }
            },
        },
    }


def make_event(event_id):
    return Event(
        event_type="OBJECT_REMOVED",
        timestamp="2026-07-25T16:20:00.000+08:00",
        frame_id=10,
        camera_id="camera_01",
        zone_id="global",
        zone_name="Global Scene",
        track_id=None,
        object_class="bottle",
        evidence_path="data/evidence/private.jpg",
        details={"previous_count": 1, "current_count": 0},
        event_id=event_id,
    )


class ContextEngineTests(unittest.TestCase):
    def test_includes_selected_skill_and_bounded_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            active_skill = {
                "name": "vision.investigate_removed_item",
                "version": "1.0.0",
                "instructions": "Use bounded read-only tools.",
            }

            context = engine.build(
                "Who took the bottle?",
                TOOLS,
                active_skill=active_skill,
                available_skills=[
                    {"name": "vision.skill_{0}".format(index)}
                    for index in range(25)
                ],
            )

            self.assertEqual(
                context["active_skill"],
                active_skill,
            )
            self.assertEqual(
                len(context["available_skills"]),
                20,
            )

    def test_recovers_utf8_cli_text_from_surrogateescape(self):
        original = "最近是否有人拿走瓶子？"
        decoded_with_ascii = original.encode("utf-8").decode(
            "ascii",
            "surrogateescape",
        )

        normalized = normalize_cli_text(decoded_with_ascii)

        self.assertEqual(normalized, original)

    def test_builds_compact_vision_and_event_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            state = os.path.join(directory, "state.json")
            store = SqliteEventStore(database)
            store.append(make_event("evt_one"))
            store.close()
            CurrentVisionStateStore(state).write(make_state())
            engine = ContextEngine(database, state)

            context = engine.build("最近的瓶子事件", TOOLS)

            self.assertEqual(
                context["vision"]["people"]["current"],
                1,
            )
            self.assertEqual(
                context["vision"]["objects"],
                [{"class_name": "bottle", "count": 1}],
            )
            event = context["recent_events"]["events"][0]
            self.assertNotIn("details", event)
            self.assertNotIn("evidence_path", event)
            self.assertNotIn("detections", context["vision"])

    def test_marks_missing_sources_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )

            context = engine.build("当前状态", TOOLS)

            self.assertEqual(
                context["vision"]["status"],
                "unavailable",
            )
            self.assertEqual(
                context["recent_events"]["status"],
                "unavailable",
            )

    def test_summarizes_tools_without_copying_input_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )

            context = engine.build("查询事件", TOOLS)
            tool = context["available_tools"][0]

            self.assertEqual(tool["name"], "event.query")
            self.assertEqual(tool["risk"], "L0")
            self.assertNotIn("inputSchema", tool)
            self.assertFalse(
                context["permissions"]["arbitrary_shell"]
            )

    def test_can_omit_duplicate_tool_descriptions(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
                include_tool_descriptions=False,
            )

            context = engine.build("query events", TOOLS)
            tool = context["available_tools"][0]

            self.assertEqual(tool["name"], "event.query")
            self.assertNotIn("description", tool)
            self.assertEqual(
                context["permissions"]["allowed_tools"],
                ["event.query"],
            )

    def test_limits_recent_tool_result_history(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
                max_tool_results=2,
            )
            results = [
                {
                    "tool_name": "tool.{0}".format(index),
                    "status": "SUCCEEDED",
                    "result": {"large": "not copied"},
                }
                for index in range(4)
            ]

            context = engine.build(
                "查询",
                TOOLS,
                recent_tool_results=results,
            )

            self.assertEqual(
                [
                    item["tool_name"]
                    for item in context["recent_tool_results"]
                ],
                ["tool.2", "tool.3"],
            )
            self.assertEqual(
                context["recent_tool_results"][0]["result"],
                {"returned": True},
            )

    def test_can_exclude_all_tool_result_history(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
                max_tool_results=0,
            )

            context = engine.build(
                "查询",
                TOOLS,
                recent_tool_results=[
                    {
                        "tool_name": "event.query",
                        "status": "SUCCEEDED",
                    }
                ],
            )

            self.assertEqual(context["recent_tool_results"], [])

    def test_preserves_bounded_event_query_window_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "event.query",
                    "status": "SUCCEEDED",
                    "result": {
                        "count": 1,
                        "events": [
                            {
                                "event_type": "ZONE_DWELL",
                                "severity": "MEDIUM",
                                "timestamp": "2026-07-28T15:30:00+08:00",
                                "zone_id": "left_zone",
                                "object_class": "person",
                                "event_id": "evt_track",
                                "track_id": 7,
                                "status": "OPEN",
                                "private": "/secret",
                            }
                        ],
                        "window": {
                            "minutes": 60,
                            "since_timestamp": (
                                "2026-07-28T15:00:00.000+08:00"
                            ),
                            "queried_at": (
                                "2026-07-28T16:00:00.000+08:00"
                            ),
                            "timezone": "Asia/Shanghai",
                        },
                        "filters": {
                            "event_type": None,
                            "object_class": None,
                            "camera_id": None,
                            "status": "OPEN",
                            "severity": "INFO",
                            "private": "/secret",
                        },
                        "pagination": {
                            "order": (
                                "timestamp_desc,frame_id_desc,"
                                "event_id_desc"
                            ),
                            "has_more": True,
                            "next_cursor": "signed.cursor",
                            "private": "/secret",
                        },
                        "read_only": True,
                        "database_path": "/private/events.db",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["events"][0]["track_id"], 7)
            self.assertNotIn("private", bounded["events"][0])
            self.assertEqual(bounded["window"]["minutes"], 60)
            self.assertEqual(
                bounded["filters"]["status"],
                "OPEN",
            )
            self.assertEqual(
                bounded["filters"]["severity"],
                "INFO",
            )
            self.assertNotIn("private", bounded["filters"])
            self.assertTrue(bounded["read_only"])
            self.assertNotIn("database_path", bounded)
            self.assertTrue(
                bounded["pagination"]["has_more"]
            )
            self.assertEqual(
                bounded["pagination"]["next_cursor"],
                "signed.cursor",
            )
            self.assertNotIn(
                "private",
                bounded["pagination"],
            )

    def test_bounds_event_summary_for_model_context(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "event.summarize",
                    "status": "SUCCEEDED",
                    "result": {
                        "window": {"minutes": 5},
                        "filters": {
                            "object_class": None,
                            "severity": "MEDIUM",
                            "private": "/secret",
                        },
                        "total_events": 2,
                        "counts": {
                            "by_event_type": [
                                {"name": "ZONE_ENTER", "count": 2}
                            ],
                            "by_severity": [],
                            "by_object_class": [],
                            "by_zone": [],
                        },
                        "timeline": {
                            "bucket_minutes": 15,
                            "timezone": "Asia/Shanghai",
                            "buckets": [
                                {
                                    "start": "time",
                                    "count": 2,
                                    "private": "/secret",
                                }
                            ],
                            "private": "/secret",
                        },
                        "comparison": {
                            "current_total": 2,
                            "previous_total": 1,
                            "absolute_change": 1,
                            "percent_change": 100.0,
                            "direction": "INCREASE",
                            "previous_window": {
                                "minutes": 5,
                                "offset_minutes": 1440,
                                "alignment": "OFFSET",
                                "since_timestamp": "start",
                                "until_timestamp": "end",
                                "timezone": "Asia/Shanghai",
                                "private": "/secret",
                            },
                            "contributors": {
                                "by_event_type": [
                                    {
                                        "name": "ZONE_ENTER",
                                        "current_count": 2,
                                        "previous_count": 1,
                                        "absolute_change": 1,
                                        "direction": "INCREASE",
                                        "private": "/secret",
                                    }
                                ],
                                "by_severity": [],
                                "by_object_class": [],
                                "by_zone": [],
                                "private": "/secret",
                            },
                            "significant_contributors": {
                                "by_event_type": [
                                    {
                                        "name": "ZONE_ENTER",
                                        "current_count": 20,
                                        "previous_count": 0,
                                        "absolute_change": 20,
                                        "percent_change": None,
                                        "direction": "INCREASE",
                                        "status": "NEW_ACTIVITY",
                                        "threshold_exceeded": True,
                                        "reason": (
                                            "NEW_ACTIVITY_ABOVE_MINIMUM"
                                        ),
                                        "private": "/secret",
                                    }
                                ],
                                "by_severity": [],
                                "by_object_class": [],
                                "by_zone": [],
                                "private": "/secret",
                            },
                            "significant_event_type_count": 1,
                            "largest_event_type_change": {
                                "name": "ZONE_ENTER",
                                "current_count": 2,
                                "previous_count": 1,
                                "absolute_change": 1,
                                "direction": "INCREASE",
                                "private": "/secret",
                            },
                            "largest_significant_event_type_change": {
                                "name": "ZONE_ENTER",
                                "current_count": 20,
                                "previous_count": 0,
                                "absolute_change": 20,
                                "percent_change": None,
                                "direction": "INCREASE",
                                "status": "NEW_ACTIVITY",
                                "threshold_exceeded": True,
                                "reason": (
                                    "NEW_ACTIVITY_ABOVE_MINIMUM"
                                ),
                                "private": "/secret",
                            },
                            "assessment": {
                                "status": "SIGNIFICANT_CHANGE",
                                "threshold_exceeded": True,
                                "reason": (
                                    "ABSOLUTE_AND_PERCENT_"
                                    "THRESHOLDS_EXCEEDED"
                                ),
                                "minimum_absolute_change": 10,
                                "minimum_percent_change": 25.0,
                                "observed_absolute_change": 20,
                                "observed_percent_change": 50.0,
                                "private": "/secret",
                            },
                            "structural_change": {
                                "by_event_type": {
                                    "status": (
                                        "MASKED_SIGNIFICANT_CHANGE"
                                    ),
                                    "complete": True,
                                    "gross_absolute_change": 40,
                                    "net_change": 0,
                                    "net_absolute_change": 0,
                                    "net_matches_total": True,
                                    "offsetting_events": 20,
                                    "masked_share_percent": 100.0,
                                    "increasing_groups": 1,
                                    "decreasing_groups": 1,
                                    "significant_groups": 2,
                                    "masked_significant_change": True,
                                    "private": "/secret",
                                },
                                "private": "/secret",
                            },
                            "private": "/secret",
                        },
                        "reference_baselines": {
                            "status": "AVAILABLE",
                            "window_minutes": 60,
                            "timezone": "Asia/Shanghai",
                            "current_total": 2,
                            "baseline_count": 2,
                            "baseline_average_total": 1.5,
                            "change_from_average": 0.5,
                            "percent_change_from_average": 33.33,
                            "direction": "INCREASE",
                            "assessment": {
                                "status": (
                                    "ABOVE_HISTORICAL_AVERAGE"
                                ),
                                "reason": (
                                    "CURRENT_TOTAL_ABOVE_HISTORY"
                                ),
                                "historical_activity_available": True,
                                "current_activity": True,
                                "private": "/secret",
                            },
                            "consistency": {
                                "status": "VARIABLE",
                                "reason": (
                                    "SPREAD_EXCEEDS_THRESHOLD"
                                ),
                                "minimum_total": 1,
                                "maximum_total": 2,
                                "spread": 1,
                                "spread_percent": 66.67,
                                "maximum_stable_spread_percent": 50,
                                "reliable_for_average": False,
                                "private": "/secret",
                            },
                            "complete": True,
                            "baselines": [
                                {
                                    "label": (
                                        "SAME_TIME_YESTERDAY"
                                    ),
                                    "minutes": 60,
                                    "offset_minutes": 1440,
                                    "since_timestamp": "yesterday-start",
                                    "until_timestamp": "yesterday-end",
                                    "timezone": "Asia/Shanghai",
                                    "total_events": 1,
                                    "private": "/secret",
                                },
                                {
                                    "label": (
                                        "SAME_TIME_LAST_WEEK"
                                    ),
                                    "minutes": 60,
                                    "offset_minutes": 10080,
                                    "since_timestamp": "week-start",
                                    "until_timestamp": "week-end",
                                    "timezone": "Asia/Shanghai",
                                    "total_events": 2,
                                    "private": "/secret",
                                },
                                {
                                    "label": "UNBOUNDED",
                                    "private": "/secret",
                                },
                            ],
                            "private": "/secret",
                        },
                        "recent_events": [
                            {
                                "event_id": "evt_one",
                                "event_type": "ZONE_ENTER",
                                "severity": "INFO",
                                "timestamp": "time",
                                "camera_id": "camera_01",
                                "zone_id": "left_zone",
                                "object_class": "person",
                                "evidence_path": "/private.jpg",
                                "details": {"private": True},
                            }
                        ],
                        "read_only": True,
                        "database_path": "/private/events.db",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["total_events"], 2)
            self.assertEqual(
                bounded["recent_events"][0]["event_id"],
                "evt_one",
            )
            serialized = json.dumps(bounded)
            self.assertNotIn("evidence_path", serialized)
            self.assertNotIn("details", serialized)
            self.assertNotIn("database_path", serialized)
            self.assertEqual(
                bounded["filters"]["severity"],
                "MEDIUM",
            )
            self.assertNotIn("private", bounded["filters"])
            self.assertEqual(
                bounded["timeline"]["bucket_minutes"],
                15,
            )
            self.assertEqual(
                bounded["timeline"]["buckets"],
                [{"start": "time", "count": 2}],
            )
            self.assertEqual(
                bounded["comparison"]["direction"],
                "INCREASE",
            )
            self.assertEqual(
                bounded["comparison"]["previous_window"][
                    "offset_minutes"
                ],
                1440,
            )
            self.assertEqual(
                bounded["comparison"]["previous_window"][
                    "alignment"
                ],
                "OFFSET",
            )
            self.assertNotIn(
                "private",
                bounded["comparison"],
            )
            self.assertEqual(
                bounded["comparison"]["contributors"][
                    "by_event_type"
                ][0]["absolute_change"],
                1,
            )
            self.assertEqual(
                bounded["comparison"][
                    "largest_event_type_change"
                ]["name"],
                "ZONE_ENTER",
            )
            self.assertEqual(
                bounded["comparison"]["structural_change"][
                    "by_event_type"
                ]["status"],
                "MASKED_SIGNIFICANT_CHANGE",
            )
            self.assertEqual(
                bounded["comparison"]["structural_change"][
                    "by_event_type"
                ]["offsetting_events"],
                20,
            )
            self.assertEqual(
                bounded["comparison"]["assessment"]["status"],
                "SIGNIFICANT_CHANGE",
            )
            self.assertTrue(
                bounded["comparison"]["assessment"][
                    "threshold_exceeded"
                ]
            )
            self.assertEqual(
                bounded["comparison"][
                    "significant_event_type_count"
                ],
                1,
            )
            self.assertEqual(
                bounded["comparison"][
                    "significant_contributors"
                ]["by_event_type"][0]["status"],
                "NEW_ACTIVITY",
            )
            self.assertEqual(
                bounded["comparison"][
                    "largest_significant_event_type_change"
                ]["name"],
                "ZONE_ENTER",
            )
            self.assertNotIn(
                "private",
                json.dumps(bounded["comparison"]),
            )
            self.assertEqual(
                bounded["reference_baselines"][
                    "baseline_average_total"
                ],
                1.5,
            )
            self.assertEqual(
                len(
                    bounded["reference_baselines"][
                        "baselines"
                    ]
                ),
                2,
            )
            self.assertEqual(
                bounded["reference_baselines"]["baselines"][1][
                    "offset_minutes"
                ],
                10080,
            )
            self.assertEqual(
                bounded["reference_baselines"]["assessment"][
                    "status"
                ],
                "ABOVE_HISTORICAL_AVERAGE",
            )
            self.assertEqual(
                bounded["reference_baselines"]["consistency"][
                    "status"
                ],
                "VARIABLE",
            )
            self.assertEqual(
                bounded["reference_baselines"]["consistency"][
                    "spread_percent"
                ],
                66.67,
            )
            self.assertNotIn(
                "private",
                json.dumps(bounded["reference_baselines"]),
            )
            self.assertNotIn(
                "UNBOUNDED",
                json.dumps(bounded["reference_baselines"]),
            )

    def test_bounds_zone_tool_result(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "vision.get_zone_status",
                    "status": "SUCCEEDED",
                    "result": {
                        "timestamp": (
                            "2026-07-27T14:00:00.000+08:00"
                        ),
                        "stale": False,
                        "selected_zone_id": "left_zone",
                        "occupied_zone_count": 1,
                        "unique_current_count": 1,
                        "zones": [
                            {
                                "zone_id": "left_zone",
                                "name": "Left Zone",
                                "current_count": 1,
                                "track_ids": [7],
                                "polygon": [[0, 0], [1, 1]],
                            }
                        ],
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["zone_count"], 1)
            self.assertEqual(
                bounded["zones"][0]["track_ids"],
                [7],
            )
            self.assertNotIn("polygon", bounded["zones"][0])

    def test_bounds_inventory_state_tool_result(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "inventory.get_current_state",
                    "status": "SUCCEEDED",
                    "result": {
                        "timestamp": "time",
                        "stale": False,
                        "selected_object_class": "bottle",
                        "target_class_count": 1,
                        "total_current": 1,
                        "total_visible": 1,
                        "nonzero_current_class_count": 1,
                        "items": [
                            {
                                "class_name": "bottle",
                                "current_count": 1,
                                "visible_count": 1,
                                "active_track_ids": list(range(30)),
                                "detections": ["forbidden"],
                            }
                        ],
                        "read_only": True,
                        "source": "/dev/video0",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(
                bounded["selected_object_class"],
                "bottle",
            )
            self.assertEqual(
                len(bounded["items"][0]["active_track_ids"]),
                20,
            )
            self.assertNotIn("detections", bounded["items"][0])
            self.assertNotIn("source", bounded)

    def test_bounds_removed_inventory_history(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "inventory.get_removed_items",
                    "status": "SUCCEEDED",
                    "result": {
                        "queried_at": "now",
                        "since_timestamp": "before",
                        "window_minutes": 10,
                        "selected_object_class": "bottle",
                        "count": 1,
                        "total_removed_units": 1,
                        "removals": [
                            {
                                "event_id": "evt_one",
                                "timestamp": "time",
                                "camera_id": "camera_01",
                                "zone_id": "global",
                                "object_class": "bottle",
                                "previous_count": 1,
                                "current_count": 0,
                                "removed_units": 1,
                                "previous_track_ids": list(range(30)),
                                "current_track_ids": [],
                                "disposition_status": "OPEN",
                                "evidence_path": "/private/path",
                                "evidence_urls": {
                                    "primary": "/api/evidence/one",
                                },
                                "details": {"private": True},
                            }
                        ],
                        "read_only": True,
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["count"], 1)
            self.assertEqual(bounded["total_removed_units"], 1)
            self.assertEqual(
                bounded["removals"][0]["evidence_urls"],
                {"primary": "/api/evidence/one"},
            )
            self.assertNotIn(
                "evidence_path",
                bounded["removals"][0],
            )
            self.assertNotIn("details", bounded["removals"][0])
            self.assertEqual(
                len(
                    bounded["removals"][0][
                        "previous_track_ids"
                    ]
                ),
                20,
            )

    def test_bounds_inventory_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "inventory.compare_state",
                    "status": "SUCCEEDED",
                    "result": {
                        "timestamp": "time",
                        "stale": False,
                        "compared_class_count": 1,
                        "total_expected": 2,
                        "total_current": 1,
                        "total_missing": 1,
                        "total_extra": 0,
                        "matches": False,
                        "comparisons": [
                            {
                                "class_name": "bottle",
                                "expected_count": 2,
                                "current_count": 1,
                                "visible_count": 1,
                                "delta": -1,
                                "missing_count": 1,
                                "extra_count": 0,
                                "matches": False,
                                "active_track_ids": list(range(30)),
                                "detections": ["forbidden"],
                            }
                        ],
                        "read_only": True,
                        "source": "/dev/video0",
                    },
                }
            )

            bounded = result["result"]
            self.assertFalse(bounded["matches"])
            self.assertEqual(bounded["total_missing"], 1)
            self.assertEqual(
                len(
                    bounded["comparisons"][0][
                        "active_track_ids"
                    ]
                ),
                20,
            )
            self.assertNotIn(
                "detections",
                bounded["comparisons"][0],
            )
            self.assertNotIn("source", bounded)

    def test_bounds_latest_frame_object_count(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "vision.count_objects",
                    "status": "SUCCEEDED",
                    "result": {
                        "timestamp": "time",
                        "stale": False,
                        "requested_classes": [
                            "class_{0}".format(index)
                            for index in range(30)
                        ],
                        "selected_zone_id": "left_zone",
                        "minimum_confidence": 0.5,
                        "detected_class_count": 1,
                        "total_count": 1,
                        "counts": [
                            {
                                "class_name": "bottle",
                                "count": 1,
                                "bbox": [1, 2, 3, 4],
                            }
                        ],
                        "detections": ["forbidden"],
                        "read_only": True,
                        "source": "/dev/video0",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(len(bounded["requested_classes"]), 20)
            self.assertEqual(bounded["total_count"], 1)
            self.assertEqual(
                bounded["counts"],
                [{"class_name": "bottle", "count": 1}],
            )
            self.assertNotIn("detections", bounded)
            self.assertNotIn("bbox", bounded["counts"][0])
            self.assertNotIn("source", bounded)

    def test_bounds_track_history_points_and_excludes_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "vision.get_track_history",
                    "status": "SUCCEEDED",
                    "result": {
                        "timestamp": "time",
                        "stale": False,
                        "selected_track_id": 7,
                        "selected_object_class": None,
                        "track_count": 1,
                        "tracks": [
                            {
                                "track_id": 7,
                                "class_name": "person",
                                "visible": True,
                                "hits": 40,
                                "first_seen_frame": 1,
                                "last_seen_frame": 40,
                                "observation_count": 40,
                                "movement": "right",
                                "displacement": 0.5,
                                "current_zone_ids": [
                                    "right_zone"
                                ],
                                "bbox": [1, 2, 3, 4],
                                "points": [
                                    {
                                        "frame_id": index,
                                        "x": index / 100.0,
                                        "y": 0.8,
                                        "private": True,
                                    }
                                    for index in range(30)
                                ],
                            }
                        ],
                        "detections": ["forbidden"],
                        "read_only": True,
                    },
                }
            )

            bounded = result["result"]
            track = bounded["tracks"][0]
            self.assertEqual(bounded["track_count"], 1)
            self.assertEqual(len(track["points"]), 20)
            self.assertEqual(track["movement"], "right")
            self.assertNotIn("bbox", track)
            self.assertNotIn("private", track["points"][0])
            self.assertNotIn("detections", bounded)

    def test_bounds_camera_status_tool_result(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "camera.get_status",
                    "status": "SUCCEEDED",
                    "result": {
                        "status": "RUNNING",
                        "healthy": True,
                        "device_available": True,
                        "worker_running": True,
                        "generation": 2,
                        "restart_count": 1,
                        "last_exit_code": 0,
                        "updated_at": "time",
                        "state_age_seconds": 0.1,
                        "state_stale": False,
                        "read_only": True,
                        "worker_pid": 999,
                        "command": ["private"],
                        "vision": {
                            "available": True,
                            "age_seconds": 0.2,
                            "frame_id": 80,
                            "timestamp": "frame",
                        },
                    },
                }
            )

            bounded = result["result"]
            self.assertTrue(bounded["healthy"])
            self.assertEqual(bounded["vision"]["frame_id"], 80)
            self.assertNotIn("worker_pid", bounded)
            self.assertNotIn("command", bounded)

    def test_bounds_model_info_for_agent_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "vision.get_model_info",
                    "status": "SUCCEEDED",
                    "result": {
                        "manifest_id": "mdl_abc",
                        "generated_at": "time",
                        "network": "ssd-mobilenet-v2",
                        "backend": "TensorRT",
                        "runtime": "jetson-inference",
                        "threshold": 0.5,
                        "artifact": {
                            "name": "model.GPU.FP16.engine",
                            "relative_path": (
                                "SSD-Mobilenet-v2/"
                                "model.GPU.FP16.engine"
                            ),
                            "size_bytes": 123,
                            "sha256": "a" * 64,
                            "precision": "FP16",
                            "absolute_path": "/private/model.engine",
                        },
                        "platform": {
                            "architecture": "aarch64",
                            "l4t_release": "R32.7.1",
                        },
                        "verification": {
                            "status": "MATCH",
                            "checked_at": "now",
                            "expected_sha256": "a" * 64,
                            "current_sha256": "a" * 64,
                            "size_bytes": 123,
                        },
                        "absolute_paths_included": False,
                        "read_only": True,
                        "model_root": "/private/networks",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(
                bounded["network"],
                "ssd-mobilenet-v2",
            )
            self.assertEqual(
                bounded["artifact"]["precision"],
                "FP16",
            )
            self.assertEqual(
                bounded["verification"]["status"],
                "MATCH",
            )
            self.assertNotIn(
                "absolute_path",
                bounded["artifact"],
            )
            self.assertNotIn("model_root", bounded)
            self.assertNotIn(directory, str(bounded))

    def test_bounds_vision_performance_for_agent_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "vision.get_performance",
                    "status": "SUCCEEDED",
                    "result": {
                        "timestamp": "time",
                        "stale": False,
                        "status": "MEETS_TARGET",
                        "total_frames": 500,
                        "sample_count": 120,
                        "window_size_frames": 120,
                        "processing_fps": 11.5,
                        "pipeline_latency_ms": {
                            "latest": 42.0,
                            "average": 44.0,
                            "p50": 43.0,
                            "p95": 52.0,
                            "maximum": 60.0,
                            "samples": ["forbidden"],
                        },
                        "targets": {
                            "minimum_fps": 5.0,
                            "maximum_p95_ms": 200.0,
                            "fps_met": True,
                            "p95_met": True,
                            "all_met": True,
                        },
                        "read_only": True,
                        "detections": ["forbidden"],
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["processing_fps"], 11.5)
            self.assertEqual(
                bounded["pipeline_latency_ms"]["p95"],
                52.0,
            )
            self.assertTrue(bounded["targets"]["all_met"])
            self.assertNotIn(
                "samples",
                bounded["pipeline_latency_ms"],
            )
            self.assertNotIn("detections", bounded)

    def test_bounds_runtime_benchmark_for_agent_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "system.get_runtime_benchmark",
                    "status": "SUCCEEDED",
                    "result": {
                        "status": "PASS",
                        "started_at": "start",
                        "completed_at": "end",
                        "actual_duration_seconds": 60.043,
                        "sample_count": 13,
                        "expected_sample_count": 13,
                        "api_success_percent": 100.0,
                        "vision_fresh_percent": 100.0,
                        "frame_progress": {
                            "advanced_frames": 870,
                            "private": "forbidden",
                        },
                        "performance": {
                            "minimum_fps": 14.607,
                            "average_fps": 14.738,
                            "maximum_observed_p95_ms": 40.317,
                        },
                        "resources": {
                            "peak_memory_used_gib": 2.652,
                            "maximum_temperature_celsius": 50.0,
                        },
                        "camera": {
                            "restart_count_delta": 0,
                        },
                        "report_sha256": "a" * 64,
                        "report_path": "/private/report.json",
                        "samples": ["forbidden"],
                        "contains_secret": False,
                        "read_only": True,
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["status"], "PASS")
            self.assertEqual(
                bounded["performance"]["minimum_fps"],
                14.607,
            )
            self.assertEqual(
                bounded["camera"]["restart_count_delta"],
                0,
            )
            self.assertNotIn("samples", bounded)
            self.assertNotIn("report_path", bounded)
            self.assertNotIn(
                "private",
                bounded["frame_progress"],
            )

    def test_bounds_storage_usage_for_agent_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "system.get_storage_usage",
                    "status": "SUCCEEDED",
                    "result": {
                        "status": "COMPLETE",
                        "timestamp": "now",
                        "root": "data",
                        "totals": {
                            "file_count": 2,
                            "directory_count": 1,
                            "bytes": 20,
                        },
                        "categories": [
                            {
                                "name": "evidence",
                                "file_count": 2,
                                "directory_count": 1,
                                "bytes": 20,
                                "path": "/private/evidence",
                            }
                        ],
                        "skipped_symlinks": 0,
                        "scan_errors": 0,
                        "truncated": False,
                        "max_files": 100000,
                        "absolute_paths_included": False,
                        "read_only": True,
                        "private_path": "/workspace/private",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["root"], "data")
            self.assertEqual(bounded["totals"]["bytes"], 20)
            self.assertEqual(len(bounded["categories"]), 1)
            self.assertFalse(bounded["absolute_paths_included"])
            self.assertNotIn(
                "path",
                bounded["categories"][0],
            )
            self.assertNotIn("private_path", bounded)

    def test_bounds_retention_preview_for_agent_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": (
                        "system.preview_data_retention"
                    ),
                    "status": "SUCCEEDED",
                    "result": {
                        "status": "COMPLETE",
                        "generated_at": "now",
                        "mode": "PREVIEW_ONLY",
                        "root": "data",
                        "policy": [
                            {
                                "category": "logs",
                                "relative_root": "data/logs",
                                "retention_days": 3,
                                "min_keep_files": 5,
                                "filename_rule": (
                                    "all_regular_files"
                                ),
                                "private": "forbidden",
                            }
                        ],
                        "protected_scopes": ["data/evidence"],
                        "scanned": {"file_count": 9},
                        "candidates": {
                            "file_count": 2,
                            "bytes": 12,
                            "returned_count": 1,
                        },
                        "by_category": [
                            {
                                "category": "logs",
                                "retention_days": 3,
                                "min_keep_files": 5,
                                "matched_file_count": 9,
                                "candidate_file_count": 2,
                                "candidate_bytes": 12,
                                "private": "forbidden",
                            }
                        ],
                        "candidate_files": [
                            {
                                "category": "logs",
                                "path": "data/logs/old.jsonl",
                                "bytes": 6,
                                "age_days": 9.0,
                                "modified_at": "old",
                                "absolute_path": "/private/old",
                            }
                        ],
                        "candidate_files_truncated": True,
                        "skipped_symlinks": 0,
                        "scan_errors": 0,
                        "truncated": False,
                        "max_files": 100000,
                        "candidate_limit": 100,
                        "delete_performed": False,
                        "absolute_paths_included": False,
                        "read_only": True,
                        "private_path": "/workspace/private",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["mode"], "PREVIEW_ONLY")
            self.assertEqual(
                bounded["candidates"]["file_count"],
                2,
            )
            self.assertFalse(bounded["delete_performed"])
            self.assertEqual(
                bounded["candidate_files"][0]["path"],
                "data/logs/old.jsonl",
            )
            self.assertNotIn(
                "absolute_path",
                bounded["candidate_files"][0],
            )
            self.assertNotIn("private_path", bounded)

    def test_bounds_retention_cleanup_result(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": (
                        "system.cleanup_retained_data"
                    ),
                    "status": "SUCCEEDED",
                    "result": {
                        "status": "COMPLETED",
                        "cleanup_id": "clean_abc",
                        "plan_id": "ret_abc",
                        "deleted_file_count": 2,
                        "deleted_bytes": 10,
                        "deleted_paths": [
                            "data/logs/old.jsonl"
                        ],
                        "failed_file_count": 0,
                        "failed_paths": [],
                        "audit_path": (
                            "data/runtime/"
                            "retention-cleanup-audit.jsonl"
                        ),
                        "delete_performed": True,
                        "confirmation_required": True,
                        "absolute_paths_included": False,
                        "read_only": False,
                        "private": "/workspace/private",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(
                bounded["deleted_file_count"],
                2,
            )
            self.assertTrue(bounded["delete_performed"])
            self.assertTrue(
                bounded["confirmation_required"]
            )
            self.assertFalse(bounded["read_only"])
            self.assertNotIn("deleted_paths", bounded)
            self.assertNotIn("failed_paths", bounded)
            self.assertNotIn("private", bounded)

    def test_bounds_retention_cleanup_history_without_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": (
                        "system.get_retention_cleanup_history"
                    ),
                    "status": "SUCCEEDED",
                    "result": {
                        "status": "COMPLETE",
                        "generated_at": "now",
                        "audit_exists": True,
                        "record_count": 1,
                        "returned_count": 1,
                        "records": [
                            {
                                "cleanup_id": (
                                    "clean_" + "a" * 32
                                ),
                                "timestamp": "now",
                                "status": "COMPLETED",
                                "plan_id": "ret_" + "b" * 32,
                                "candidate_file_count": 2,
                                "candidate_bytes": 20,
                                "deleted_file_count": 2,
                                "deleted_bytes": 20,
                                "failed_file_count": 0,
                                "deleted_paths": [
                                    "data/logs/private.jsonl"
                                ],
                            }
                        ],
                        "totals": {
                            "deleted_file_count": 2,
                            "deleted_bytes": 20,
                            "failed_file_count": 0,
                        },
                        "invalid_records": 0,
                        "truncated": False,
                        "read_only": True,
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["record_count"], 1)
            self.assertEqual(bounded["returned_count"], 1)
            self.assertFalse(bounded["paths_included"])
            self.assertFalse(
                bounded["absolute_paths_included"]
            )
            self.assertNotIn(
                "deleted_paths",
                bounded["records"][0],
            )
            self.assertNotIn("audit_path", bounded)

    def test_bounds_evidence_integrity_without_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "evidence.verify_recent",
                    "status": "SUCCEEDED",
                    "result": {
                        "status": "WARN",
                        "generated_at": "now",
                        "requested_event_limit": 50,
                        "checked_event_count": 2,
                        "events_with_evidence": 1,
                        "events_without_evidence": 1,
                        "referenced_evidence_count": 1,
                        "valid_evidence_count": 0,
                        "unique_valid_file_count": 0,
                        "issue_count": 1,
                        "issues": [
                            {
                                "event_id": "evt_" + "a" * 32,
                                "evidence_kind": "primary",
                                "code": "MISSING_FILE",
                                "path": "/private/evidence.jpg",
                            }
                        ],
                        "issues_truncated": False,
                        "paths_included": False,
                        "absolute_paths_included": False,
                        "read_only": True,
                        "private_path": "/workspace/private",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["status"], "WARN")
            self.assertEqual(bounded["issue_count"], 1)
            self.assertEqual(
                bounded["issues"][0]["code"],
                "MISSING_FILE",
            )
            self.assertNotIn("path", bounded["issues"][0])
            self.assertNotIn("private_path", bounded)
            self.assertFalse(bounded["paths_included"])
            self.assertFalse(
                bounded["absolute_paths_included"]
            )

    def test_bounds_exact_evidence_integrity_without_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            event_id = "evt_" + "e" * 32
            result = engine.bounded_tool_result(
                {
                    "tool_name": "evidence.verify_event",
                    "status": "SUCCEEDED",
                    "result": {
                        "status": "PASS",
                        "generated_at": "now",
                        "event": {
                            "event_id": event_id,
                            "event_type": "OBJECT_APPEARED",
                            "timestamp": "now",
                            "camera_id": "camera_01",
                            "zone_id": "global",
                            "object_class": "bottle",
                            "path": "/private",
                        },
                        "referenced_evidence_count": 1,
                        "valid_evidence_count": 1,
                        "issue_count": 0,
                        "evidence": [
                            {
                                "kind": "primary",
                                "status": "VALID",
                                "bytes": 10,
                                "sha256": "a" * 64,
                                "url": "/api/evidence/primary",
                                "path": "/private/evidence.jpg",
                            }
                        ],
                        "maximum_hash_bytes": 16777216,
                        "jpeg_signature_checked": True,
                        "sha256_checked": True,
                        "paths_included": False,
                        "absolute_paths_included": False,
                        "read_only": True,
                        "private_path": "/workspace/private",
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(
                bounded["event"]["event_id"],
                event_id,
            )
            self.assertEqual(
                bounded["evidence"][0]["sha256"],
                "a" * 64,
            )
            self.assertNotIn("path", bounded["event"])
            self.assertNotIn("path", bounded["evidence"][0])
            self.assertNotIn("private_path", bounded)

    def test_bounds_camera_restart_result_for_model_context(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "camera.restart",
                    "status": "SUCCEEDED",
                    "result": {
                        "request_id": "restart_" + "a" * 32,
                        "requested_at": "requested",
                        "completed_at": "completed",
                        "before_generation": 2,
                        "after_generation": 3,
                        "before_restart_count": 1,
                        "after_restart_count": 2,
                        "recovery_seconds": 3.5,
                        "vision_frame_id": 10,
                        "state_stale": False,
                        "worker_pid": 999,
                        "command": ["private"],
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(bounded["after_generation"], 3)
            self.assertEqual(bounded["vision_frame_id"], 10)
            self.assertNotIn("worker_pid", bounded)
            self.assertNotIn("command", bounded)

    def test_bounds_exact_event_detail_for_model_context(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ContextEngine(
                os.path.join(directory, "missing.db"),
                os.path.join(directory, "missing.json"),
            )
            result = engine.bounded_tool_result(
                {
                    "tool_name": "event.get_detail",
                    "status": "SUCCEEDED",
                    "result": {
                        "event_id": (
                            "evt_44444444444444444444444444444444"
                        ),
                        "event_type": "OBJECT_REMOVED",
                        "severity": "INFO",
                        "timestamp": "time",
                        "frame_id": 50,
                        "camera_id": "camera_01",
                        "zone_id": "global",
                        "zone_name": "Global Scene",
                        "track_id": None,
                        "object_class": "bottle",
                        "status": "OPEN",
                        "acknowledged_at": None,
                        "evidence_path": (
                            "data/evidence/private.jpg"
                        ),
                        "details": {
                            "previous_count": 1,
                            "current_count": 0,
                            "private_path": "/forbidden",
                        },
                        "evidence_urls": {
                            "primary": "/api/evidence/primary",
                        },
                        "read_only": True,
                    },
                }
            )

            bounded = result["result"]
            self.assertEqual(
                bounded["details"],
                {"previous_count": 1, "current_count": 0},
            )
            self.assertEqual(
                bounded["evidence_urls"],
                {"primary": "/api/evidence/primary"},
            )
            self.assertNotIn("evidence_path", bounded)
            self.assertNotIn("private_path", bounded["details"])


if __name__ == "__main__":
    unittest.main()
