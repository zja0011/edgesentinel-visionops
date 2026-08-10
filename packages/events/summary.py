"""Bounded read-only summaries of recent structured events."""

import sqlite3
from datetime import datetime, timedelta

from packages.api.event_service import (
    EventDatabaseUnavailable,
    EventQueryService,
)
from packages.events.sqlite_store import SqliteEventStore
from packages.vision.schemas import BEIJING_TIMEZONE


class EventSummaryService(object):
    API_SCHEMA_VERSION = "1.0"
    GROUP_LIMIT = 20
    DEFAULT_CHANGE_THRESHOLD_PERCENT = 25
    DEFAULT_CHANGE_THRESHOLD_EVENTS = 10
    REFERENCE_STABILITY_SPREAD_PERCENT = 50

    def __init__(self, database_path, now_provider=None):
        self.database_path = database_path
        self.query_service = EventQueryService(
            database_path,
            now_provider=now_provider,
        )

    def summarize(
        self,
        minutes=10,
        event_type=None,
        object_class=None,
        camera_id=None,
        status=None,
        severity=None,
        bucket_minutes=None,
        compare_previous=False,
        comparison_offset_minutes=None,
        include_reference_baselines=False,
        change_threshold_percent=DEFAULT_CHANGE_THRESHOLD_PERCENT,
        change_threshold_events=DEFAULT_CHANGE_THRESHOLD_EVENTS,
        recent_limit=5,
    ):
        recent_limit = int(recent_limit)
        if recent_limit < 1 or recent_limit > 10:
            raise ValueError(
                "recent_limit must be between 1 and 10"
            )
        if bucket_minutes is not None:
            bucket_minutes = int(bucket_minutes)
            if bucket_minutes not in (15, 30, 60):
                raise ValueError(
                    "bucket_minutes must be 15, 30, or 60"
                )
        change_threshold_percent = int(
            change_threshold_percent
        )
        if (
            change_threshold_percent < 1
            or change_threshold_percent > 500
        ):
            raise ValueError(
                "change_threshold_percent must be between 1 and 500"
            )
        change_threshold_events = int(
            change_threshold_events
        )
        if (
            change_threshold_events < 1
            or change_threshold_events > 1000
        ):
            raise ValueError(
                "change_threshold_events must be between 1 and 1000"
            )
        if comparison_offset_minutes is not None:
            comparison_offset_minutes = int(
                comparison_offset_minutes
            )
            if (
                comparison_offset_minutes < 1
                or comparison_offset_minutes > 10080
            ):
                raise ValueError(
                    "comparison_offset_minutes must be between "
                    "1 and 10080"
                )
            if not bool(compare_previous):
                raise ValueError(
                    "comparison_offset_minutes requires "
                    "compare_previous=true"
                )
            if comparison_offset_minutes < int(minutes):
                raise ValueError(
                    "comparison_offset_minutes must be greater "
                    "than or equal to minutes"
                )
        recent = self.query_service.list_events(
            limit=recent_limit,
            event_type=event_type,
            object_class=object_class,
            camera_id=camera_id,
            status=status,
            severity=severity,
            minutes=minutes,
        )
        window = recent["window"]
        try:
            store = SqliteEventStore(
                self.database_path,
                read_only=True,
            )
            try:
                aggregate = store.summarize(
                    event_type=event_type,
                    object_class=object_class,
                    camera_id=camera_id,
                    status=recent["filters"]["status"],
                    severity=recent["filters"]["severity"],
                    since_timestamp=window["since_timestamp"],
                    group_limit=self.GROUP_LIMIT,
                )
                timeline_rows = (
                    store.summarize_timeline(
                        bucket_minutes=bucket_minutes,
                        event_type=event_type,
                        object_class=object_class,
                        camera_id=camera_id,
                        status=recent["filters"]["status"],
                        severity=recent["filters"]["severity"],
                        since_timestamp=window[
                            "since_timestamp"
                        ],
                    )
                    if bucket_minutes is not None
                    else None
                )
                previous_aggregate = None
                previous_window = None
                reference_baselines = None
                if bool(compare_previous):
                    current_since = self._parse_timestamp(
                        window["since_timestamp"]
                    )
                    comparison_offset = (
                        int(comparison_offset_minutes)
                        if comparison_offset_minutes is not None
                        else int(minutes)
                    )
                    previous_since = (
                        current_since
                        - timedelta(minutes=comparison_offset)
                    )
                    previous_until = (
                        previous_since
                        + timedelta(minutes=int(minutes))
                    )
                    previous_window = {
                        "minutes": int(minutes),
                        "offset_minutes": comparison_offset,
                        "alignment": (
                            "ADJACENT"
                            if comparison_offset == int(minutes)
                            else "OFFSET"
                        ),
                        "since_timestamp": self._format_timestamp(
                            previous_since
                        ),
                        "until_timestamp": self._format_timestamp(
                            previous_until
                        ),
                        "timezone": "Asia/Shanghai",
                    }
                    previous_aggregate = store.summarize(
                        event_type=event_type,
                        object_class=object_class,
                        camera_id=camera_id,
                        status=recent["filters"]["status"],
                        severity=recent["filters"]["severity"],
                        since_timestamp=previous_window[
                            "since_timestamp"
                        ],
                        until_timestamp=previous_window[
                            "until_timestamp"
                        ],
                        group_limit=self.GROUP_LIMIT,
                    )
                if bool(include_reference_baselines):
                    current_since = self._parse_timestamp(
                        window["since_timestamp"]
                    )
                    reference_baselines = []
                    for label, offset_minutes in (
                        ("SAME_TIME_YESTERDAY", 1440),
                        ("SAME_TIME_LAST_WEEK", 10080),
                    ):
                        reference_since = (
                            current_since
                            - timedelta(minutes=offset_minutes)
                        )
                        reference_until = (
                            reference_since
                            + timedelta(minutes=int(minutes))
                        )
                        reference_window = {
                            "label": label,
                            "minutes": int(minutes),
                            "offset_minutes": offset_minutes,
                            "since_timestamp": self._format_timestamp(
                                reference_since
                            ),
                            "until_timestamp": self._format_timestamp(
                                reference_until
                            ),
                            "timezone": "Asia/Shanghai",
                        }
                        reference_aggregate = store.summarize(
                            event_type=event_type,
                            object_class=object_class,
                            camera_id=camera_id,
                            status=recent["filters"]["status"],
                            severity=recent["filters"]["severity"],
                            since_timestamp=reference_window[
                                "since_timestamp"
                            ],
                            until_timestamp=reference_window[
                                "until_timestamp"
                            ],
                            group_limit=self.GROUP_LIMIT,
                        )
                        reference_window["total_events"] = int(
                            reference_aggregate["total_events"]
                        )
                        reference_baselines.append(
                            reference_window
                        )
            finally:
                store.close()
        except (OSError, sqlite3.Error) as error:
            raise EventDatabaseUnavailable(
                "event database is unavailable"
            ) from error

        groups = aggregate["groups"]
        payload = {
            "schema_version": self.API_SCHEMA_VERSION,
            "window": window,
            "filters": {
                "event_type": event_type,
                "object_class": object_class,
                "camera_id": camera_id,
                "status": recent["filters"]["status"],
                "severity": recent["filters"]["severity"],
            },
            "total_events": aggregate["total_events"],
            "counts": {
                "by_event_type": groups["event_type"],
                "by_severity": groups["severity"],
                "by_object_class": groups["object_class"],
                "by_zone": groups["zone_id"],
            },
            "recent_events": [
                self._bounded_event(event)
                for event in recent["events"]
            ],
            "recent_limit": recent_limit,
            "group_limit": self.GROUP_LIMIT,
            "read_only": True,
        }
        if bucket_minutes is not None:
            payload["timeline"] = self._fill_timeline(
                timeline_rows,
                bucket_minutes,
                window,
            )
        if bool(include_reference_baselines):
            baseline_totals = [
                int(item["total_events"])
                for item in reference_baselines
            ]
            baseline_average = round(
                float(sum(baseline_totals))
                / float(len(baseline_totals)),
                2,
            )
            current_total = int(payload["total_events"])
            change_from_average = round(
                float(current_total) - baseline_average,
                2,
            )
            reference_assessment = (
                self._assess_reference_baselines(
                    current_total=current_total,
                    baseline_average=baseline_average,
                    change_from_average=change_from_average,
                )
            )
            reference_consistency = (
                self._assess_reference_consistency(
                    baseline_totals=baseline_totals,
                    baseline_average=baseline_average,
                )
            )
            payload["reference_baselines"] = {
                "status": "AVAILABLE",
                "window_minutes": int(minutes),
                "timezone": "Asia/Shanghai",
                "current_total": current_total,
                "baseline_count": len(reference_baselines),
                "baseline_average_total": baseline_average,
                "change_from_average": change_from_average,
                "percent_change_from_average": (
                    round(
                        (
                            change_from_average
                            / baseline_average
                        )
                        * 100.0,
                        2,
                    )
                    if baseline_average
                    else None
                ),
                "direction": (
                    "INCREASE"
                    if change_from_average > 0
                    else (
                        "DECREASE"
                        if change_from_average < 0
                        else "UNCHANGED"
                    )
                ),
                "assessment": reference_assessment,
                "consistency": reference_consistency,
                "baselines": reference_baselines,
                "complete": True,
            }
        if bool(compare_previous):
            current_total = int(payload["total_events"])
            previous_total = int(
                previous_aggregate["total_events"]
            )
            change = current_total - previous_total
            direction = (
                "INCREASE"
                if change > 0
                else ("DECREASE" if change < 0 else "UNCHANGED")
            )
            contributors = self._compare_groups(
                aggregate["groups"],
                previous_aggregate["groups"],
                minimum_percent=change_threshold_percent,
                minimum_events=change_threshold_events,
            )
            significant_contributors = {
                name: [
                    item
                    for item in contributors[name]
                    if item["threshold_exceeded"]
                ]
                for name in contributors
            }
            percent_change = (
                round(
                    (float(change) / float(previous_total))
                    * 100.0,
                    2,
                )
                if previous_total
                else None
            )
            assessment = self._assess_change(
                current_total=current_total,
                previous_total=previous_total,
                absolute_change=change,
                percent_change=percent_change,
                minimum_percent=change_threshold_percent,
                minimum_events=change_threshold_events,
            )
            structural_change = self._structural_changes(
                contributors=contributors,
                current_truncated=aggregate[
                    "group_truncated"
                ],
                previous_truncated=previous_aggregate[
                    "group_truncated"
                ],
                total_change=change,
                overall_threshold_exceeded=assessment[
                    "threshold_exceeded"
                ],
            )
            payload["comparison"] = {
                "current_total": current_total,
                "previous_total": previous_total,
                "absolute_change": change,
                "percent_change": percent_change,
                "direction": direction,
                "previous_window": previous_window,
                "contributors": contributors,
                "significant_contributors": (
                    significant_contributors
                ),
                "significant_event_type_count": len(
                    significant_contributors["by_event_type"]
                ),
                "largest_event_type_change": (
                    contributors["by_event_type"][0]
                    if contributors["by_event_type"]
                    else None
                ),
                "largest_significant_event_type_change": (
                    significant_contributors["by_event_type"][0]
                    if significant_contributors["by_event_type"]
                    else None
                ),
                "assessment": assessment,
                "structural_change": structural_change,
            }
        return payload

    @staticmethod
    def _assess_reference_baselines(
        current_total,
        baseline_average,
        change_from_average,
    ):
        current_total = int(current_total)
        baseline_average = float(baseline_average)
        change_from_average = float(change_from_average)
        historical_activity_available = baseline_average > 0
        current_activity = current_total > 0
        if not historical_activity_available:
            if current_activity:
                status = "NEW_ACTIVITY"
                reason = "CURRENT_ACTIVITY_WITH_ZERO_HISTORY"
            else:
                status = "NO_HISTORICAL_ACTIVITY"
                reason = "CURRENT_AND_HISTORY_ARE_ZERO"
        elif change_from_average > 0:
            status = "ABOVE_HISTORICAL_AVERAGE"
            reason = "CURRENT_TOTAL_ABOVE_HISTORY"
        elif change_from_average < 0:
            status = "BELOW_HISTORICAL_AVERAGE"
            reason = "CURRENT_TOTAL_BELOW_HISTORY"
        else:
            status = "MATCHES_HISTORICAL_AVERAGE"
            reason = "CURRENT_TOTAL_MATCHES_HISTORY"
        return {
            "status": status,
            "reason": reason,
            "historical_activity_available": (
                historical_activity_available
            ),
            "current_activity": current_activity,
        }

    @classmethod
    def _assess_reference_consistency(
        cls,
        baseline_totals,
        baseline_average,
    ):
        totals = [int(value) for value in baseline_totals]
        minimum_total = min(totals)
        maximum_total = max(totals)
        spread = maximum_total - minimum_total
        baseline_average = float(baseline_average)
        spread_percent = (
            round(
                (float(spread) / baseline_average) * 100.0,
                2,
            )
            if baseline_average
            else None
        )
        if not baseline_average:
            status = "NO_HISTORICAL_ACTIVITY"
            reason = "BOTH_REFERENCE_TOTALS_ARE_ZERO"
        elif spread == 0:
            status = "STABLE"
            reason = "REFERENCE_TOTALS_MATCH"
        elif (
            spread_percent
            <= cls.REFERENCE_STABILITY_SPREAD_PERCENT
        ):
            status = "STABLE"
            reason = "SPREAD_WITHIN_THRESHOLD"
        else:
            status = "VARIABLE"
            reason = "SPREAD_EXCEEDS_THRESHOLD"
        return {
            "status": status,
            "reason": reason,
            "minimum_total": minimum_total,
            "maximum_total": maximum_total,
            "spread": spread,
            "spread_percent": spread_percent,
            "maximum_stable_spread_percent": (
                cls.REFERENCE_STABILITY_SPREAD_PERCENT
            ),
            "reliable_for_average": status == "STABLE",
        }

    @classmethod
    def _structural_changes(
        cls,
        contributors,
        current_truncated,
        previous_truncated,
        total_change,
        overall_threshold_exceeded,
    ):
        dimensions = (
            ("event_type", "by_event_type"),
            ("severity", "by_severity"),
            ("object_class", "by_object_class"),
            ("zone_id", "by_zone"),
        )
        payload = {}
        for source_name, output_name in dimensions:
            rows = contributors.get(output_name) or []
            complete = not (
                current_truncated.get(source_name)
                or previous_truncated.get(source_name)
            )
            gross_change = sum(
                abs(int(item["absolute_change"]))
                for item in rows
            )
            net_change = sum(
                int(item["absolute_change"])
                for item in rows
            )
            net_absolute_change = abs(net_change)
            offsetting_events = max(
                0,
                int(
                    (
                        gross_change
                        - net_absolute_change
                    )
                    / 2
                ),
            )
            masked_share_percent = (
                round(
                    (
                        float(
                            gross_change
                            - net_absolute_change
                        )
                        / float(gross_change)
                    )
                    * 100.0,
                    2,
                )
                if gross_change
                else 0.0
            )
            increasing_groups = sum(
                1
                for item in rows
                if int(item["absolute_change"]) > 0
            )
            decreasing_groups = sum(
                1
                for item in rows
                if int(item["absolute_change"]) < 0
            )
            significant_groups = sum(
                1
                for item in rows
                if item["threshold_exceeded"]
            )
            masked_significant_change = bool(
                complete
                and not overall_threshold_exceeded
                and significant_groups > 0
            )
            if not complete:
                status = "PARTIAL"
            elif masked_significant_change:
                status = "MASKED_SIGNIFICANT_CHANGE"
            elif offsetting_events > 0:
                status = "OPPOSING_CHANGES"
            elif gross_change > 0:
                status = "ONE_DIRECTION"
            else:
                status = "NO_CHANGE"
            payload[output_name] = {
                "status": status,
                "complete": complete,
                "gross_absolute_change": gross_change,
                "net_change": net_change,
                "net_absolute_change": net_absolute_change,
                "net_matches_total": bool(
                    complete and net_change == int(total_change)
                ),
                "offsetting_events": offsetting_events,
                "masked_share_percent": masked_share_percent,
                "increasing_groups": increasing_groups,
                "decreasing_groups": decreasing_groups,
                "significant_groups": significant_groups,
                "masked_significant_change": (
                    masked_significant_change
                ),
            }
        return payload

    @staticmethod
    def _assess_change(
        current_total,
        previous_total,
        absolute_change,
        percent_change,
        minimum_percent,
        minimum_events,
    ):
        magnitude = abs(int(absolute_change))
        if int(previous_total) == 0:
            exceeded = int(current_total) >= int(minimum_events)
            status = (
                "NEW_ACTIVITY"
                if exceeded
                else "INSUFFICIENT_BASELINE"
            )
            reason = (
                "NEW_ACTIVITY_ABOVE_MINIMUM"
                if exceeded
                else "BASELINE_ZERO_AND_ACTIVITY_BELOW_MINIMUM"
            )
        else:
            percent_magnitude = abs(float(percent_change))
            exceeded = (
                magnitude >= int(minimum_events)
                and percent_magnitude >= float(minimum_percent)
            )
            status = (
                "SIGNIFICANT_CHANGE"
                if exceeded
                else "WITHIN_THRESHOLD"
            )
            if exceeded:
                reason = "ABSOLUTE_AND_PERCENT_THRESHOLDS_EXCEEDED"
            elif magnitude < int(minimum_events):
                reason = "ABSOLUTE_CHANGE_BELOW_MINIMUM"
            else:
                reason = "PERCENT_CHANGE_BELOW_MINIMUM"
        return {
            "status": status,
            "threshold_exceeded": bool(exceeded),
            "reason": reason,
            "minimum_absolute_change": int(minimum_events),
            "minimum_percent_change": float(minimum_percent),
            "observed_absolute_change": int(absolute_change),
            "observed_percent_change": percent_change,
        }

    @classmethod
    def _compare_groups(
        cls,
        current_groups,
        previous_groups,
        minimum_percent,
        minimum_events,
    ):
        dimensions = (
            ("event_type", "by_event_type"),
            ("severity", "by_severity"),
            ("object_class", "by_object_class"),
            ("zone_id", "by_zone"),
        )
        contributors = {}
        for source_name, output_name in dimensions:
            current = {
                item["name"]: int(item["count"])
                for item in current_groups.get(source_name, [])
            }
            previous = {
                item["name"]: int(item["count"])
                for item in previous_groups.get(source_name, [])
            }
            rows = []
            for name in sorted(set(current) | set(previous)):
                current_count = current.get(name, 0)
                previous_count = previous.get(name, 0)
                change = current_count - previous_count
                percent_change = (
                    round(
                        (
                            float(change)
                            / float(previous_count)
                        )
                        * 100.0,
                        2,
                    )
                    if previous_count
                    else None
                )
                assessment = cls._assess_change(
                    current_total=current_count,
                    previous_total=previous_count,
                    absolute_change=change,
                    percent_change=percent_change,
                    minimum_percent=minimum_percent,
                    minimum_events=minimum_events,
                )
                rows.append(
                    {
                        "name": name,
                        "current_count": current_count,
                        "previous_count": previous_count,
                        "absolute_change": change,
                        "percent_change": percent_change,
                        "direction": (
                            "INCREASE"
                            if change > 0
                            else (
                                "DECREASE"
                                if change < 0
                                else "UNCHANGED"
                            )
                        ),
                        "status": assessment["status"],
                        "threshold_exceeded": assessment[
                            "threshold_exceeded"
                        ],
                        "reason": assessment["reason"],
                    }
                )
            rows.sort(
                key=lambda item: (
                    -abs(item["absolute_change"]),
                    item["name"],
                )
            )
            contributors[output_name] = rows[: cls.GROUP_LIMIT]
        return contributors

    @classmethod
    def _fill_timeline(
        cls,
        rows,
        bucket_minutes,
        window,
    ):
        counts = {
            cls._format_timestamp(
                cls._parse_timestamp(row["start"])
            ): int(row["count"])
            for row in rows
        }
        start = cls._parse_timestamp(
            window["since_timestamp"]
        )
        end = cls._parse_timestamp(window["queried_at"])
        start = start.replace(
            minute=(
                start.minute // bucket_minutes
            ) * bucket_minutes,
            second=0,
            microsecond=0,
        )
        end = end.replace(
            minute=(
                end.minute // bucket_minutes
            ) * bucket_minutes,
            second=0,
            microsecond=0,
        )
        buckets = []
        current = start
        while current <= end and len(buckets) < 100:
            key = cls._format_timestamp(current)
            buckets.append(
                {
                    "start": key,
                    "count": counts.get(key, 0),
                }
            )
            current += timedelta(minutes=bucket_minutes)
        return {
            "bucket_minutes": bucket_minutes,
            "timezone": "Asia/Shanghai",
            "buckets": buckets,
        }

    @staticmethod
    def _parse_timestamp(value):
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1]
        elif (
            len(text) >= 6
            and text[-6] in ("+", "-")
            and text[-3] == ":"
        ):
            text = text[:-6]
        parsed = datetime.strptime(
            text,
            (
                "%Y-%m-%dT%H:%M:%S.%f"
                if "." in text
                else "%Y-%m-%dT%H:%M:%S"
            ),
        )
        return parsed.replace(tzinfo=BEIJING_TIMEZONE)

    @staticmethod
    def _format_timestamp(value):
        return (
            value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "+08:00"
        )

    @staticmethod
    def _bounded_event(event):
        return {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "severity": event.get("severity"),
            "timestamp": event.get("timestamp"),
            "camera_id": event.get("camera_id"),
            "zone_id": event.get("zone_id"),
            "zone_name": event.get("zone_name"),
            "object_class": event.get("object_class"),
            "status": event.get("status"),
        }
