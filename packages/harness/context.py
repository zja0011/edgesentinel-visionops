"""Build compact, bounded context for a future Agent model call."""

from packages.api.event_service import (
    EventDatabaseUnavailable,
    EventQueryService,
)
from packages.vision.schemas import beijing_timestamp
from packages.vision.state_store import (
    CurrentVisionStateStore,
    VisionStateUnavailable,
)


class ContextEngine(object):
    def __init__(
        self,
        database_path,
        state_path,
        max_events=5,
        max_tool_results=3,
        state_max_age_seconds=5.0,
        include_tool_descriptions=True,
    ):
        max_events = int(max_events)
        max_tool_results = int(max_tool_results)
        if max_events <= 0 or max_events > 20:
            raise ValueError("max_events must be between 1 and 20")
        if max_tool_results < 0 or max_tool_results > 10:
            raise ValueError(
                "max_tool_results must be between 0 and 10"
            )
        self.event_service = EventQueryService(database_path)
        self.state_store = CurrentVisionStateStore(state_path)
        self.max_events = max_events
        self.max_tool_results = max_tool_results
        self.state_max_age_seconds = float(state_max_age_seconds)
        self.include_tool_descriptions = bool(
            include_tool_descriptions
        )

    def build(
        self,
        user_message,
        tool_schemas,
        recent_tool_results=None,
        active_skill=None,
        available_skills=None,
    ):
        user_message = str(user_message).strip()
        if not user_message:
            raise ValueError("user_message must not be empty")
        tool_schemas = list(tool_schemas)
        tool_results = list(recent_tool_results or [])

        return {
            "schema_version": "1.0",
            "generated_at": beijing_timestamp(),
            "user_message": user_message,
            "task_goal": user_message,
            "vision": self._vision_summary(),
            "recent_events": self._event_summary(),
            "available_tools": self._tool_summary(tool_schemas),
            "recent_tool_results": self._result_summary(
                tool_results
            ),
            "active_skill": (
                dict(active_skill)
                if isinstance(active_skill, dict)
                else None
            ),
            "available_skills": [
                dict(skill)
                for skill in list(available_skills or [])[:20]
                if isinstance(skill, dict)
            ],
            "permissions": {
                "mode": "default_deny",
                "arbitrary_shell": False,
                "allowed_tools": sorted(
                    schema.get("name", "")
                    for schema in tool_schemas
                    if schema.get("name")
                ),
            },
            "limits": {
                "max_events": self.max_events,
                "max_tool_results": self.max_tool_results,
                "full_frame_detections_included": False,
            },
        }

    def _vision_summary(self):
        try:
            state = self.state_store.read(
                self.state_max_age_seconds
            )
        except VisionStateUnavailable:
            return {
                "status": "unavailable",
                "stale": True,
                "people": None,
                "objects": [],
            }

        snapshot = state["snapshot"]
        analytics = snapshot.get("analytics") or {}
        people = analytics.get("people") or {}
        inventory = analytics.get("inventory") or {}
        current_counts = inventory.get("current_counts") or {}
        objects = [
            {
                "class_name": class_name,
                "count": int(count),
            }
            for class_name, count in sorted(current_counts.items())
            if int(count) > 0
        ]
        return {
            "status": "available",
            "timestamp": snapshot.get("timestamp"),
            "camera_id": snapshot.get("camera_id"),
            "frame_id": snapshot.get("frame_id"),
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "people": {
                "current": int(people.get("current_people", 0)),
                "visible": int(people.get("visible_people", 0)),
            },
            "objects": objects,
        }

    def _event_summary(self):
        try:
            payload = self.event_service.list_events(
                limit=self.max_events
            )
        except EventDatabaseUnavailable:
            return {
                "status": "unavailable",
                "count": 0,
                "events": [],
            }

        events = []
        for event in payload["events"]:
            events.append(
                {
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                    "severity": event.get("severity"),
                    "timestamp": event.get("timestamp"),
                    "camera_id": event.get("camera_id"),
                    "zone_id": event.get("zone_id"),
                    "object_class": event.get("object_class"),
                    "disposition_status": event.get("status"),
                    "acknowledged_at": event.get(
                        "acknowledged_at"
                    ),
                }
            )
        return {
            "status": "available",
            "count": len(events),
            "events": events,
        }

    def _tool_summary(self, tool_schemas):
        tools = []
        for schema in tool_schemas:
            annotations = schema.get("annotations") or {}
            tool = {
                "name": schema.get("name"),
                "risk": annotations.get("riskLevel"),
                "auto_execute": annotations.get(
                    "autoExecute",
                    False,
                ),
                "requires_confirmation": annotations.get(
                    "requiresConfirmation",
                    False,
                ),
            }
            if self.include_tool_descriptions:
                tool["description"] = schema.get("description")
            tools.append(tool)
        return tools

    def _result_summary(self, results):
        if self.max_tool_results == 0:
            return []
        summaries = []
        for result in results[-self.max_tool_results :]:
            if not isinstance(result, dict):
                continue
            error = result.get("error") or {}
            summary = {
                "tool_name": result.get("tool_name"),
                "status": result.get("status"),
                "error_code": error.get("code"),
            }
            payload = result.get("result")
            if isinstance(payload, dict):
                summary["result"] = self._bounded_tool_payload(
                    result.get("tool_name"),
                    payload,
                )
            summaries.append(summary)
        return summaries

    def bounded_tool_result(self, result):
        """Return one provider-safe bounded tool result."""
        summaries = self._result_summary([result])
        if summaries:
            return summaries[0]
        return {
            "tool_name": None,
            "status": "FAILED",
            "error_code": "INVALID_TOOL_RESULT",
        }

    def _bounded_tool_payload(self, tool_name, payload):
        if tool_name == "memory.search":
            return {
                "status": payload.get("status"),
                "query": payload.get("query"),
                "selected_kind": payload.get("selected_kind"),
                "count": payload.get("count"),
                "total_records": payload.get("total_records"),
                "records": [
                    {
                        key: record.get(key)
                        for key in (
                            "memory_id",
                            "kind",
                            "key",
                            "value",
                            "revision",
                            "updated_at",
                        )
                    }
                    for record in (payload.get("records") or [])[:20]
                    if isinstance(record, dict)
                ],
                "bounded": True,
                "read_only": True,
            }
        if tool_name in ("memory.remember", "memory.forget"):
            return {
                key: payload.get(key)
                for key in (
                    "status",
                    "memory_id",
                    "kind",
                    "key",
                    "value",
                    "revision",
                    "delete_performed",
                    "read_only",
                )
                if key in payload
            }
        if tool_name == "evidence.verify_event":
            event = payload.get("event") or {}
            evidence = []
            for item in (payload.get("evidence") or [])[:3]:
                evidence.append(
                    {
                        "kind": item.get("kind"),
                        "status": item.get("status"),
                        "bytes": item.get("bytes"),
                        "sha256": item.get("sha256"),
                        "url": item.get("url"),
                    }
                )
            return {
                "status": payload.get("status"),
                "generated_at": payload.get("generated_at"),
                "event": {
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                    "timestamp": event.get("timestamp"),
                    "camera_id": event.get("camera_id"),
                    "zone_id": event.get("zone_id"),
                    "object_class": event.get("object_class"),
                },
                "referenced_evidence_count": payload.get(
                    "referenced_evidence_count"
                ),
                "valid_evidence_count": payload.get(
                    "valid_evidence_count"
                ),
                "issue_count": payload.get("issue_count"),
                "evidence": evidence,
                "maximum_hash_bytes": payload.get(
                    "maximum_hash_bytes"
                ),
                "jpeg_signature_checked": payload.get(
                    "jpeg_signature_checked"
                ),
                "sha256_checked": payload.get(
                    "sha256_checked"
                ),
                "paths_included": False,
                "absolute_paths_included": False,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "evidence.verify_recent":
            return {
                "status": payload.get("status"),
                "generated_at": payload.get("generated_at"),
                "requested_event_limit": payload.get(
                    "requested_event_limit"
                ),
                "checked_event_count": payload.get(
                    "checked_event_count"
                ),
                "events_with_evidence": payload.get(
                    "events_with_evidence"
                ),
                "events_without_evidence": payload.get(
                    "events_without_evidence"
                ),
                "referenced_evidence_count": payload.get(
                    "referenced_evidence_count"
                ),
                "valid_evidence_count": payload.get(
                    "valid_evidence_count"
                ),
                "unique_valid_file_count": payload.get(
                    "unique_valid_file_count"
                ),
                "issue_count": payload.get("issue_count"),
                "issues": [
                    {
                        "event_id": item.get("event_id"),
                        "evidence_kind": item.get(
                            "evidence_kind"
                        ),
                        "code": item.get("code"),
                    }
                    for item in (
                        payload.get("issues") or []
                    )[:20]
                ],
                "issues_truncated": payload.get(
                    "issues_truncated"
                ),
                "window": payload.get("window"),
                "jpeg_signature_checked": payload.get(
                    "jpeg_signature_checked"
                ),
                "paths_included": False,
                "absolute_paths_included": False,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "event.query":
            events = []
            for event in (payload.get("events") or [])[
                : self.max_events
            ]:
                events.append(
                    {
                        "event_type": event.get("event_type"),
                        "severity": event.get("severity"),
                        "timestamp": event.get("timestamp"),
                        "zone_id": event.get("zone_id"),
                        "object_class": event.get("object_class"),
                        "event_id": event.get("event_id"),
                        "track_id": event.get("track_id"),
                        "disposition_status": event.get("status"),
                        "acknowledged_at": event.get(
                            "acknowledged_at"
                        ),
                    }
                )
            return {
                "count": len(events),
                "events": events,
                "window": payload.get("window"),
                "pagination": {
                    "order": (
                        payload.get("pagination") or {}
                    ).get("order"),
                    "has_more": (
                        payload.get("pagination") or {}
                    ).get("has_more"),
                    "next_cursor": (
                        payload.get("pagination") or {}
                    ).get("next_cursor"),
                },
                "filters": {
                    key: (payload.get("filters") or {}).get(key)
                    for key in (
                        "event_type",
                        "object_class",
                        "camera_id",
                        "status",
                        "severity",
                    )
                },
                "read_only": payload.get("read_only"),
            }
        if tool_name == "event.summarize":
            recent_events = []
            for event in (payload.get("recent_events") or [])[
                : self.max_events
            ]:
                recent_events.append(
                    {
                        "event_id": event.get("event_id"),
                        "event_type": event.get("event_type"),
                        "severity": event.get("severity"),
                        "timestamp": event.get("timestamp"),
                        "camera_id": event.get("camera_id"),
                        "zone_id": event.get("zone_id"),
                        "object_class": event.get(
                            "object_class"
                        ),
                    }
                )
            counts = payload.get("counts") or {}
            return {
                "window": payload.get("window"),
                "filters": {
                    key: (payload.get("filters") or {}).get(key)
                    for key in (
                        "event_type",
                        "object_class",
                        "camera_id",
                        "status",
                        "severity",
                    )
                },
                "total_events": payload.get("total_events"),
                "counts": {
                    name: (counts.get(name) or [])[:20]
                    for name in (
                        "by_event_type",
                        "by_severity",
                        "by_object_class",
                        "by_zone",
                    )
                },
                "timeline": {
                    "bucket_minutes": (
                        payload.get("timeline") or {}
                    ).get("bucket_minutes"),
                    "timezone": (
                        payload.get("timeline") or {}
                    ).get("timezone"),
                    "buckets": [
                        {
                            "start": bucket.get("start"),
                            "count": bucket.get("count"),
                        }
                        for bucket in (
                            (
                                payload.get("timeline") or {}
                            ).get("buckets")
                            or []
                        )[:100]
                    ],
                }
                if payload.get("timeline") is not None
                else None,
                "comparison": {
                    "current_total": (
                        payload.get("comparison") or {}
                    ).get("current_total"),
                    "previous_total": (
                        payload.get("comparison") or {}
                    ).get("previous_total"),
                    "absolute_change": (
                        payload.get("comparison") or {}
                    ).get("absolute_change"),
                    "percent_change": (
                        payload.get("comparison") or {}
                    ).get("percent_change"),
                    "direction": (
                        payload.get("comparison") or {}
                    ).get("direction"),
                    "previous_window": (
                        {
                            key: (
                                (
                                    (
                                        payload.get(
                                            "comparison"
                                        )
                                        or {}
                                    ).get("previous_window")
                                    or {}
                                ).get(key)
                            )
                            for key in (
                                "minutes",
                                "offset_minutes",
                                "alignment",
                                "since_timestamp",
                                "until_timestamp",
                                "timezone",
                            )
                        }
                        if (
                            payload.get("comparison") or {}
                        ).get("previous_window")
                        is not None
                        else None
                    ),
                    "contributors": {
                        name: [
                            {
                                "name": item.get("name"),
                                "current_count": item.get(
                                    "current_count"
                                ),
                                "previous_count": item.get(
                                    "previous_count"
                                ),
                                "absolute_change": item.get(
                                    "absolute_change"
                                ),
                                "percent_change": item.get(
                                    "percent_change"
                                ),
                                "direction": item.get(
                                    "direction"
                                ),
                                "status": item.get("status"),
                                "threshold_exceeded": item.get(
                                    "threshold_exceeded"
                                ),
                                "reason": item.get("reason"),
                            }
                            for item in (
                                (
                                    (
                                        payload.get(
                                            "comparison"
                                        )
                                        or {}
                                    ).get("contributors")
                                    or {}
                                ).get(name)
                                or []
                            )[:20]
                        ]
                        for name in (
                            "by_event_type",
                            "by_severity",
                            "by_object_class",
                            "by_zone",
                        )
                    },
                    "significant_contributors": {
                        name: [
                            {
                                key: item.get(key)
                                for key in (
                                    "name",
                                    "current_count",
                                    "previous_count",
                                    "absolute_change",
                                    "percent_change",
                                    "direction",
                                    "status",
                                    "threshold_exceeded",
                                    "reason",
                                )
                            }
                            for item in (
                                (
                                    (
                                        payload.get(
                                            "comparison"
                                        )
                                        or {}
                                    ).get(
                                        "significant_contributors"
                                    )
                                    or {}
                                ).get(name)
                                or []
                            )[:20]
                        ]
                        for name in (
                            "by_event_type",
                            "by_severity",
                            "by_object_class",
                            "by_zone",
                        )
                    },
                    "significant_event_type_count": (
                        payload.get("comparison") or {}
                    ).get("significant_event_type_count"),
                    "largest_event_type_change": {
                        key: (
                            (
                                payload.get("comparison")
                                or {}
                            ).get(
                                "largest_event_type_change"
                            )
                            or {}
                        ).get(key)
                        for key in (
                            "name",
                            "current_count",
                            "previous_count",
                            "absolute_change",
                            "direction",
                        )
                    }
                    if (
                        payload.get("comparison") or {}
                    ).get("largest_event_type_change")
                    is not None
                    else None,
                    "largest_significant_event_type_change": {
                        key: (
                            (
                                payload.get("comparison")
                                or {}
                            ).get(
                                "largest_significant_event_type_change"
                            )
                            or {}
                        ).get(key)
                        for key in (
                            "name",
                            "current_count",
                            "previous_count",
                            "absolute_change",
                            "percent_change",
                            "direction",
                            "status",
                            "threshold_exceeded",
                            "reason",
                        )
                    }
                    if (
                        payload.get("comparison") or {}
                    ).get(
                        "largest_significant_event_type_change"
                    )
                    is not None
                    else None,
                    "assessment": {
                        key: (
                            (
                                payload.get("comparison")
                                or {}
                            ).get("assessment")
                            or {}
                        ).get(key)
                        for key in (
                            "status",
                            "threshold_exceeded",
                            "reason",
                            "minimum_absolute_change",
                            "minimum_percent_change",
                            "observed_absolute_change",
                            "observed_percent_change",
                        )
                    }
                    if (
                        payload.get("comparison") or {}
                    ).get("assessment")
                    is not None
                    else None,
                    "structural_change": {
                        name: {
                            key: item.get(key)
                            for key in (
                                "status",
                                "complete",
                                "gross_absolute_change",
                                "net_change",
                                "net_absolute_change",
                                "net_matches_total",
                                "offsetting_events",
                                "masked_share_percent",
                                "increasing_groups",
                                "decreasing_groups",
                                "significant_groups",
                                "masked_significant_change",
                            )
                        }
                        for name, item in (
                            (
                                payload.get("comparison")
                                or {}
                            ).get("structural_change")
                            or {}
                        ).items()
                        if name
                        in (
                            "by_event_type",
                            "by_severity",
                            "by_object_class",
                            "by_zone",
                        )
                    },
                }
                if payload.get("comparison") is not None
                else None,
                "reference_baselines": {
                    "status": (
                        payload.get("reference_baselines") or {}
                    ).get("status"),
                    "window_minutes": (
                        payload.get("reference_baselines") or {}
                    ).get("window_minutes"),
                    "timezone": (
                        payload.get("reference_baselines") or {}
                    ).get("timezone"),
                    "current_total": (
                        payload.get("reference_baselines") or {}
                    ).get("current_total"),
                    "baseline_count": (
                        payload.get("reference_baselines") or {}
                    ).get("baseline_count"),
                    "baseline_average_total": (
                        payload.get("reference_baselines") or {}
                    ).get("baseline_average_total"),
                    "change_from_average": (
                        payload.get("reference_baselines") or {}
                    ).get("change_from_average"),
                    "percent_change_from_average": (
                        payload.get("reference_baselines") or {}
                    ).get("percent_change_from_average"),
                    "direction": (
                        payload.get("reference_baselines") or {}
                    ).get("direction"),
                    "assessment": {
                        key: (
                            (
                                payload.get(
                                    "reference_baselines"
                                )
                                or {}
                            ).get("assessment")
                            or {}
                        ).get(key)
                        for key in (
                            "status",
                            "reason",
                            "historical_activity_available",
                            "current_activity",
                        )
                    }
                    if (
                        payload.get("reference_baselines") or {}
                    ).get("assessment")
                    is not None
                    else None,
                    "consistency": {
                        key: (
                            (
                                payload.get(
                                    "reference_baselines"
                                )
                                or {}
                            ).get("consistency")
                            or {}
                        ).get(key)
                        for key in (
                            "status",
                            "reason",
                            "minimum_total",
                            "maximum_total",
                            "spread",
                            "spread_percent",
                            "maximum_stable_spread_percent",
                            "reliable_for_average",
                        )
                    }
                    if (
                        payload.get("reference_baselines") or {}
                    ).get("consistency")
                    is not None
                    else None,
                    "complete": (
                        payload.get("reference_baselines") or {}
                    ).get("complete"),
                    "baselines": [
                        {
                            key: baseline.get(key)
                            for key in (
                                "label",
                                "minutes",
                                "offset_minutes",
                                "since_timestamp",
                                "until_timestamp",
                                "timezone",
                                "total_events",
                            )
                        }
                        for baseline in (
                            (
                                payload.get(
                                    "reference_baselines"
                                )
                                or {}
                            ).get("baselines")
                            or []
                        )[:2]
                    ],
                }
                if payload.get("reference_baselines") is not None
                else None,
                "recent_events": recent_events,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "event.get_detail":
            details = payload.get("details") or {}
            allowed_detail_keys = (
                "previous_count",
                "current_count",
                "count_change",
                "confirmation_frames",
                "current_people",
                "current_track_ids",
                "previous_track_ids",
                "dwell_seconds_threshold",
                "observed_dwell_seconds",
                "entered_frame_id",
                "transition_status",
                "generation",
                "restart_count",
                "last_exit_code",
                "offline_event_id",
                "outage_duration_seconds",
                "evidence_pair_complete",
            )
            evidence_urls = payload.get("evidence_urls") or {}
            return {
                "event_id": payload.get("event_id"),
                "event_type": payload.get("event_type"),
                "severity": payload.get("severity"),
                "timestamp": payload.get("timestamp"),
                "frame_id": payload.get("frame_id"),
                "camera_id": payload.get("camera_id"),
                "zone_id": payload.get("zone_id"),
                "zone_name": payload.get("zone_name"),
                "track_id": payload.get("track_id"),
                "object_class": payload.get("object_class"),
                "disposition_status": payload.get("status"),
                "acknowledged_at": payload.get(
                    "acknowledged_at"
                ),
                "details": {
                    key: details.get(key)
                    for key in allowed_detail_keys
                    if key in details
                },
                "evidence_urls": {
                    key: evidence_urls.get(key)
                    for key in ("primary", "before", "after")
                    if evidence_urls.get(key)
                },
                "read_only": payload.get("read_only"),
            }
        if tool_name == "vision.get_people_count":
            return {
                "timestamp": payload.get("timestamp"),
                "stale": payload.get("stale"),
                "current_people": payload.get("current_people"),
                "visible_people": payload.get("visible_people"),
            }
        if tool_name == "weather.get_current":
            location = payload.get("location") or {}
            current = payload.get("current") or {}
            return {
                "provider": payload.get("provider"),
                "queried_at": payload.get("queried_at"),
                "location": {
                    "name": location.get("name"),
                    "admin1": location.get("admin1"),
                    "country": location.get("country"),
                    "timezone": location.get("timezone"),
                },
                "current": {
                    key: current.get(key)
                    for key in (
                        "timestamp",
                        "temperature_c",
                        "apparent_temperature_c",
                        "relative_humidity_percent",
                        "precipitation_mm",
                        "weather_code",
                        "condition",
                        "wind_speed_kmh",
                        "wind_direction_degrees",
                        "is_day",
                    )
                },
                "external_request": True,
                "read_only": True,
            }
        if tool_name == "vision.get_current_objects":
            objects = []
            for item in (payload.get("objects") or [])[:20]:
                objects.append(
                    {
                        "class_name": item.get("class_name"),
                        "count": item.get("count"),
                    }
                )
            return {
                "timestamp": payload.get("timestamp"),
                "stale": payload.get("stale"),
                "total_current": payload.get("total_current"),
                "objects": objects,
            }
        if tool_name == "vision.get_model_info":
            artifact = payload.get("artifact") or {}
            platform_info = payload.get("platform") or {}
            verification = payload.get("verification") or {}
            return {
                "manifest_id": payload.get("manifest_id"),
                "generated_at": payload.get("generated_at"),
                "network": payload.get("network"),
                "backend": payload.get("backend"),
                "runtime": payload.get("runtime"),
                "threshold": payload.get("threshold"),
                "artifact": {
                    "name": artifact.get("name"),
                    "relative_path": artifact.get(
                        "relative_path"
                    ),
                    "size_bytes": artifact.get("size_bytes"),
                    "sha256": artifact.get("sha256"),
                    "precision": artifact.get("precision"),
                },
                "platform": {
                    "architecture": platform_info.get(
                        "architecture"
                    ),
                    "l4t_release": platform_info.get(
                        "l4t_release"
                    ),
                },
                "verification": {
                    "status": verification.get("status"),
                    "checked_at": verification.get(
                        "checked_at"
                    ),
                    "expected_sha256": verification.get(
                        "expected_sha256"
                    ),
                    "current_sha256": verification.get(
                        "current_sha256"
                    ),
                    "size_bytes": verification.get(
                        "size_bytes"
                    ),
                },
                "absolute_paths_included": False,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "vision.get_performance":
            latency = payload.get("pipeline_latency_ms") or {}
            targets = payload.get("targets") or {}
            return {
                "timestamp": payload.get("timestamp"),
                "stale": payload.get("stale"),
                "status": payload.get("status"),
                "total_frames": payload.get("total_frames"),
                "sample_count": payload.get("sample_count"),
                "window_size_frames": payload.get(
                    "window_size_frames"
                ),
                "processing_fps": payload.get(
                    "processing_fps"
                ),
                "pipeline_latency_ms": {
                    key: latency.get(key)
                    for key in (
                        "latest",
                        "average",
                        "p50",
                        "p95",
                        "maximum",
                    )
                },
                "targets": {
                    "minimum_fps": targets.get("minimum_fps"),
                    "maximum_p95_ms": targets.get(
                        "maximum_p95_ms"
                    ),
                    "fps_met": targets.get("fps_met"),
                    "p95_met": targets.get("p95_met"),
                    "all_met": targets.get("all_met"),
                },
                "read_only": payload.get("read_only"),
            }
        if tool_name == "vision.count_objects":
            counts = []
            for item in (payload.get("counts") or [])[:20]:
                counts.append(
                    {
                        "class_name": item.get("class_name"),
                        "count": item.get("count"),
                    }
                )
            return {
                "timestamp": payload.get("timestamp"),
                "stale": payload.get("stale"),
                "requested_classes": list(
                    payload.get("requested_classes") or []
                )[:20],
                "selected_zone_id": payload.get(
                    "selected_zone_id"
                ),
                "minimum_confidence": payload.get(
                    "minimum_confidence"
                ),
                "class_count": len(counts),
                "detected_class_count": payload.get(
                    "detected_class_count"
                ),
                "total_count": payload.get("total_count"),
                "counts": counts,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "vision.get_track_history":
            tracks = []
            for item in (payload.get("tracks") or [])[:20]:
                points = []
                for point in (item.get("points") or [])[:20]:
                    points.append(
                        {
                            "frame_id": point.get("frame_id"),
                            "x": point.get("x"),
                            "y": point.get("y"),
                        }
                    )
                tracks.append(
                    {
                        "track_id": item.get("track_id"),
                        "class_name": item.get("class_name"),
                        "visible": item.get("visible"),
                        "hits": item.get("hits"),
                        "first_seen_frame": item.get(
                            "first_seen_frame"
                        ),
                        "last_seen_frame": item.get(
                            "last_seen_frame"
                        ),
                        "observation_count": item.get(
                            "observation_count"
                        ),
                        "sampled_point_count": len(points),
                        "movement": item.get("movement"),
                        "displacement": item.get("displacement"),
                        "current_zone_ids": list(
                            item.get("current_zone_ids") or []
                        )[:10],
                        "points": points,
                    }
                )
            return {
                "timestamp": payload.get("timestamp"),
                "stale": payload.get("stale"),
                "selected_track_id": payload.get(
                    "selected_track_id"
                ),
                "selected_object_class": payload.get(
                    "selected_object_class"
                ),
                "track_count": len(tracks),
                "tracks": tracks,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "inventory.get_current_state":
            items = []
            for item in (payload.get("items") or [])[:20]:
                items.append(
                    {
                        "class_name": item.get("class_name"),
                        "current_count": item.get(
                            "current_count"
                        ),
                        "visible_count": item.get(
                            "visible_count"
                        ),
                        "active_track_ids": list(
                            item.get("active_track_ids") or []
                        )[:20],
                    }
                )
            return {
                "timestamp": payload.get("timestamp"),
                "stale": payload.get("stale"),
                "selected_object_class": payload.get(
                    "selected_object_class"
                ),
                "target_class_count": len(items),
                "total_current": payload.get("total_current"),
                "total_visible": payload.get("total_visible"),
                "nonzero_current_class_count": payload.get(
                    "nonzero_current_class_count"
                ),
                "items": items,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "inventory.compare_state":
            comparisons = []
            for item in (payload.get("comparisons") or [])[:20]:
                comparisons.append(
                    {
                        "class_name": item.get("class_name"),
                        "expected_count": item.get(
                            "expected_count"
                        ),
                        "current_count": item.get(
                            "current_count"
                        ),
                        "visible_count": item.get(
                            "visible_count"
                        ),
                        "delta": item.get("delta"),
                        "missing_count": item.get(
                            "missing_count"
                        ),
                        "extra_count": item.get("extra_count"),
                        "matches": item.get("matches"),
                        "active_track_ids": list(
                            item.get("active_track_ids") or []
                        )[:20],
                    }
                )
            return {
                "timestamp": payload.get("timestamp"),
                "stale": payload.get("stale"),
                "compared_class_count": len(comparisons),
                "total_expected": payload.get("total_expected"),
                "total_current": payload.get("total_current"),
                "total_missing": payload.get("total_missing"),
                "total_extra": payload.get("total_extra"),
                "matches": payload.get("matches"),
                "comparisons": comparisons,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "inventory.get_removed_items":
            removals = []
            for removal in (payload.get("removals") or [])[
                : self.max_events
            ]:
                evidence_urls = removal.get("evidence_urls") or {}
                removals.append(
                    {
                        "event_id": removal.get("event_id"),
                        "timestamp": removal.get("timestamp"),
                        "camera_id": removal.get("camera_id"),
                        "zone_id": removal.get("zone_id"),
                        "object_class": removal.get("object_class"),
                        "previous_count": removal.get(
                            "previous_count"
                        ),
                        "current_count": removal.get(
                            "current_count"
                        ),
                        "removed_units": removal.get(
                            "removed_units"
                        ),
                        "previous_track_ids": list(
                            removal.get("previous_track_ids") or []
                        )[:20],
                        "current_track_ids": list(
                            removal.get("current_track_ids") or []
                        )[:20],
                        "disposition_status": removal.get(
                            "disposition_status"
                        ),
                        "evidence_urls": {
                            key: evidence_urls.get(key)
                            for key in ("primary", "before", "after")
                            if evidence_urls.get(key)
                        },
                    }
                )
            return {
                "queried_at": payload.get("queried_at"),
                "since_timestamp": payload.get("since_timestamp"),
                "window_minutes": payload.get("window_minutes"),
                "selected_object_class": payload.get(
                    "selected_object_class"
                ),
                "selected_camera_id": payload.get(
                    "selected_camera_id"
                ),
                "count": len(removals),
                "total_removed_units": sum(
                    int(item.get("removed_units") or 0)
                    for item in removals
                ),
                "removals": removals,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "vision.get_zone_status":
            zones = []
            for zone in (payload.get("zones") or [])[:20]:
                zones.append(
                    {
                        "zone_id": zone.get("zone_id"),
                        "name": zone.get("name"),
                        "current_count": zone.get(
                            "current_count"
                        ),
                        "track_ids": list(
                            zone.get("track_ids") or []
                        )[:20],
                    }
                )
            return {
                "timestamp": payload.get("timestamp"),
                "stale": payload.get("stale"),
                "selected_zone_id": payload.get(
                    "selected_zone_id"
                ),
                "zone_count": len(zones),
                "occupied_zone_count": payload.get(
                    "occupied_zone_count"
                ),
                "unique_current_count": payload.get(
                    "unique_current_count"
                ),
                "zones": zones,
            }
        if tool_name == "camera.capture_snapshot":
            return {
                "snapshot_id": payload.get("snapshot_id"),
                "created_at": payload.get("created_at"),
                "camera_id": payload.get("camera_id"),
                "vision_frame_id": payload.get(
                    "vision_frame_id"
                ),
                "evidence_path": payload.get("evidence_path"),
                "bytes": payload.get("bytes"),
            }
        if tool_name == "camera.get_status":
            vision = payload.get("vision") or {}
            return {
                "status": payload.get("status"),
                "healthy": payload.get("healthy"),
                "device_available": payload.get(
                    "device_available"
                ),
                "worker_running": payload.get("worker_running"),
                "generation": payload.get("generation"),
                "restart_count": payload.get("restart_count"),
                "last_exit_code": payload.get("last_exit_code"),
                "updated_at": payload.get("updated_at"),
                "state_age_seconds": payload.get(
                    "state_age_seconds"
                ),
                "state_stale": payload.get("state_stale"),
                "vision": {
                    "available": vision.get("available"),
                    "age_seconds": vision.get("age_seconds"),
                    "frame_id": vision.get("frame_id"),
                    "timestamp": vision.get("timestamp"),
                },
                "read_only": payload.get("read_only"),
            }
        if tool_name == "camera.restart":
            return {
                "request_id": payload.get("request_id"),
                "requested_at": payload.get("requested_at"),
                "completed_at": payload.get("completed_at"),
                "before_generation": payload.get(
                    "before_generation"
                ),
                "after_generation": payload.get(
                    "after_generation"
                ),
                "before_restart_count": payload.get(
                    "before_restart_count"
                ),
                "after_restart_count": payload.get(
                    "after_restart_count"
                ),
                "recovery_seconds": payload.get(
                    "recovery_seconds"
                ),
                "vision_frame_id": payload.get(
                    "vision_frame_id"
                ),
                "state_stale": payload.get("state_stale"),
            }
        if tool_name == "report.generate":
            return {
                "report_id": payload.get("report_id"),
                "created_at": payload.get("created_at"),
                "date": payload.get("date"),
                "event_count": payload.get("event_count"),
                "truncated": payload.get("truncated"),
                "report_path": payload.get("report_path"),
                "bytes": payload.get("bytes"),
            }
        if tool_name == "event.acknowledge":
            return {
                "event_id": payload.get("event_id"),
                "event_type": payload.get("event_type"),
                "object_class": payload.get("object_class"),
                "status": payload.get("status"),
                "acknowledged_at": payload.get(
                    "acknowledged_at"
                ),
                "already_acknowledged": payload.get(
                    "already_acknowledged"
                ),
            }
        if tool_name == "system.get_runtime_benchmark":
            performance = payload.get("performance") or {}
            resources = payload.get("resources") or {}
            camera = payload.get("camera") or {}
            progress = payload.get("frame_progress") or {}
            return {
                "status": payload.get("status"),
                "started_at": payload.get("started_at"),
                "completed_at": payload.get("completed_at"),
                "actual_duration_seconds": payload.get(
                    "actual_duration_seconds"
                ),
                "sample_count": payload.get("sample_count"),
                "expected_sample_count": payload.get(
                    "expected_sample_count"
                ),
                "api_success_percent": payload.get(
                    "api_success_percent"
                ),
                "vision_fresh_percent": payload.get(
                    "vision_fresh_percent"
                ),
                "frame_progress": {
                    "advanced_frames": progress.get(
                        "advanced_frames"
                    ),
                },
                "performance": {
                    "minimum_fps": performance.get(
                        "minimum_fps"
                    ),
                    "average_fps": performance.get(
                        "average_fps"
                    ),
                    "maximum_observed_p95_ms": performance.get(
                        "maximum_observed_p95_ms"
                    ),
                },
                "resources": {
                    "peak_memory_used_gib": resources.get(
                        "peak_memory_used_gib"
                    ),
                    "maximum_temperature_celsius": resources.get(
                        "maximum_temperature_celsius"
                    ),
                },
                "camera": {
                    "restart_count_delta": camera.get(
                        "restart_count_delta"
                    ),
                },
                "report_sha256": payload.get("report_sha256"),
                "samples_included": False,
                "contains_secret": False,
                "absolute_paths_included": False,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "system.get_health":
            checks = payload.get("checks") or {}
            return {
                "status": payload.get("status"),
                "timestamp": payload.get("timestamp"),
                "checks": {
                    name: {
                        key: value
                        for key, value in check.items()
                        if key
                        in (
                            "status",
                            "used_percent",
                            "max_celsius",
                            "available_bytes",
                            "cpu_count",
                            "one_minute",
                        )
                    }
                    for name, check in checks.items()
                    if name
                    in (
                        "load",
                        "memory",
                        "disk",
                        "temperature",
                    )
                },
                "issues": list(payload.get("issues") or [])[:8],
                "uptime_seconds": payload.get("uptime_seconds"),
                "read_only": payload.get("read_only"),
            }
        if (
            tool_name
            == "system.get_retention_cleanup_history"
        ):
            return {
                "status": payload.get("status"),
                "generated_at": payload.get("generated_at"),
                "audit_exists": payload.get("audit_exists"),
                "record_count": payload.get("record_count"),
                "returned_count": payload.get(
                    "returned_count"
                ),
                "records": [
                    {
                        "cleanup_id": item.get("cleanup_id"),
                        "timestamp": item.get("timestamp"),
                        "status": item.get("status"),
                        "plan_id": item.get("plan_id"),
                        "candidate_file_count": item.get(
                            "candidate_file_count"
                        ),
                        "candidate_bytes": item.get(
                            "candidate_bytes"
                        ),
                        "deleted_file_count": item.get(
                            "deleted_file_count"
                        ),
                        "deleted_bytes": item.get(
                            "deleted_bytes"
                        ),
                        "failed_file_count": item.get(
                            "failed_file_count"
                        ),
                    }
                    for item in (
                        payload.get("records") or []
                    )[:20]
                ],
                "totals": payload.get("totals"),
                "invalid_records": payload.get(
                    "invalid_records"
                ),
                "truncated": payload.get("truncated"),
                "paths_included": False,
                "absolute_paths_included": False,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "system.cleanup_retained_data":
            return {
                "status": payload.get("status"),
                "cleanup_id": payload.get("cleanup_id"),
                "plan_id": payload.get("plan_id"),
                "deleted_file_count": payload.get(
                    "deleted_file_count"
                ),
                "deleted_bytes": payload.get("deleted_bytes"),
                "failed_file_count": payload.get(
                    "failed_file_count"
                ),
                "audit_path": payload.get("audit_path"),
                "delete_performed": payload.get(
                    "delete_performed"
                ),
                "confirmation_required": payload.get(
                    "confirmation_required"
                ),
                "absolute_paths_included": False,
                "read_only": False,
            }
        if tool_name == "system.preview_data_retention":
            return {
                "status": payload.get("status"),
                "generated_at": payload.get("generated_at"),
                "mode": payload.get("mode"),
                "root": payload.get("root"),
                "plan_id": payload.get("plan_id"),
                "policy": [
                    {
                        "category": item.get("category"),
                        "relative_root": item.get(
                            "relative_root"
                        ),
                        "retention_days": item.get(
                            "retention_days"
                        ),
                        "min_keep_files": item.get(
                            "min_keep_files"
                        ),
                        "filename_rule": item.get(
                            "filename_rule"
                        ),
                    }
                    for item in (
                        payload.get("policy") or []
                    )[:3]
                ],
                "protected_scopes": list(
                    payload.get("protected_scopes") or []
                )[:8],
                "scanned": payload.get("scanned"),
                "candidates": payload.get("candidates"),
                "by_category": [
                    {
                        "category": item.get("category"),
                        "retention_days": item.get(
                            "retention_days"
                        ),
                        "min_keep_files": item.get(
                            "min_keep_files"
                        ),
                        "matched_file_count": item.get(
                            "matched_file_count"
                        ),
                        "candidate_file_count": item.get(
                            "candidate_file_count"
                        ),
                        "candidate_bytes": item.get(
                            "candidate_bytes"
                        ),
                    }
                    for item in (
                        payload.get("by_category") or []
                    )[:3]
                ],
                "candidate_files": [
                    {
                        "category": item.get("category"),
                        "path": item.get("path"),
                        "bytes": item.get("bytes"),
                        "age_days": item.get("age_days"),
                        "modified_at": item.get(
                            "modified_at"
                        ),
                    }
                    for item in (
                        payload.get("candidate_files") or []
                    )[:100]
                ],
                "candidate_files_truncated": payload.get(
                    "candidate_files_truncated"
                ),
                "skipped_symlinks": payload.get(
                    "skipped_symlinks"
                ),
                "scan_errors": payload.get("scan_errors"),
                "truncated": payload.get("truncated"),
                "max_files": payload.get("max_files"),
                "candidate_limit": payload.get(
                    "candidate_limit"
                ),
                "delete_performed": False,
                "absolute_paths_included": False,
                "read_only": payload.get("read_only"),
            }
        if tool_name == "system.get_storage_usage":
            return {
                "status": payload.get("status"),
                "timestamp": payload.get("timestamp"),
                "root": payload.get("root"),
                "totals": payload.get("totals"),
                "categories": [
                    {
                        "name": item.get("name"),
                        "file_count": item.get("file_count"),
                        "directory_count": item.get(
                            "directory_count"
                        ),
                        "bytes": item.get("bytes"),
                    }
                    for item in (
                        payload.get("categories") or []
                    )[:9]
                ],
                "skipped_symlinks": payload.get(
                    "skipped_symlinks"
                ),
                "scan_errors": payload.get("scan_errors"),
                "truncated": payload.get("truncated"),
                "max_files": payload.get("max_files"),
                "absolute_paths_included": False,
                "read_only": payload.get("read_only"),
            }
        return {"returned": payload is not None}
