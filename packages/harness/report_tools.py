"""Confirmation-gated deterministic local event reports."""

import datetime
import hashlib
import os
import sqlite3
import tempfile
import uuid

from packages.events.sqlite_store import SqliteEventStore
from packages.vision.schemas import beijing_timestamp


class ReportGenerationUnavailable(RuntimeError):
    """Raised when a requested report cannot be safely generated."""


class DailyEventReportTools(object):
    MAX_EVENTS = 500

    EVENT_LABELS = {
        "ZONE_ENTER": "进入区域",
        "ZONE_EXIT": "离开区域",
        "ZONE_DWELL": "长时间停留",
        "OBJECT_APPEARED": "物品出现",
        "OBJECT_REMOVED": "物品移除",
        "OBJECT_LEFT_BEHIND": "物品遗留",
        "CAMERA_OFFLINE": "摄像头离线",
        "CAMERA_RECOVERED": "摄像头恢复",
    }

    def __init__(self, project_dir, database_path, clock=None):
        self.project_dir = os.path.abspath(project_dir)
        self.database_path = os.path.abspath(database_path)
        self.clock = clock or beijing_timestamp
        self.report_root = os.path.join(
            self.project_dir,
            "data",
            "reports",
        )
        self._require_inside(self.report_root, self.project_dir)

    def generate(self, arguments):
        arguments = dict(arguments or {})
        created_at = str(self.clock())
        report_date = arguments.get("date") or created_at[:10]
        self._validate_date(report_date)
        camera_id = self._optional_filter(
            arguments.get("camera_id"),
            "camera_id",
        )
        object_class = self._optional_filter(
            arguments.get("object_class"),
            "object_class",
        )
        events = self._query(
            report_date,
            camera_id,
            object_class,
        )
        truncated = len(events) > self.MAX_EVENTS
        events = events[: self.MAX_EVENTS]
        report_id = "rpt_{0}".format(uuid.uuid4().hex)
        content = self._render(
            report_id=report_id,
            report_date=report_date,
            created_at=created_at,
            camera_id=camera_id,
            object_class=object_class,
            events=events,
            truncated=truncated,
        ).encode("utf-8")
        report_directory = os.path.join(
            self.report_root,
            report_date,
        )
        filename = "{0}_{1}_{2}.md".format(
            report_date,
            self._safe_component(created_at),
            report_id,
        )
        path = os.path.abspath(
            os.path.join(report_directory, filename)
        )
        self._require_inside(path, self.report_root)
        self._write_atomic(path, content)
        return {
            "schema_version": "1.0",
            "report_id": report_id,
            "created_at": created_at,
            "date": report_date,
            "filters": {
                "camera_id": camera_id,
                "object_class": object_class,
            },
            "event_count": len(events),
            "truncated": truncated,
            "report_path": os.path.relpath(
                path,
                self.project_dir,
            ).replace(os.sep, "/"),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def _query(self, report_date, camera_id, object_class):
        try:
            store = SqliteEventStore(
                self.database_path,
                read_only=True,
            )
            try:
                return store.query_day(
                    report_date,
                    limit=self.MAX_EVENTS + 1,
                    camera_id=camera_id,
                    object_class=object_class,
                )
            finally:
                store.close()
        except (OSError, sqlite3.Error) as error:
            raise ReportGenerationUnavailable(
                "event database is unavailable"
            ) from error

    def _render(
        self,
        report_id,
        report_date,
        created_at,
        camera_id,
        object_class,
        events,
        truncated,
    ):
        type_counts = {}
        severity_counts = {}
        for event in events:
            event_type = str(event.get("event_type") or "UNKNOWN")
            severity = str(event.get("severity") or "UNKNOWN")
            type_counts[event_type] = type_counts.get(event_type, 0) + 1
            severity_counts[severity] = (
                severity_counts.get(severity, 0) + 1
            )

        lines = [
            "# EdgeSentinel VisionOps 每日事件报告",
            "",
            "- 报告编号：`{0}`".format(report_id),
            "- 报告日期：{0}（北京时间）".format(report_date),
            "- 生成时间：{0}".format(created_at),
            "- 摄像头筛选：{0}".format(camera_id or "全部"),
            "- 目标类别筛选：{0}".format(object_class or "全部"),
            "- 报告事件数：{0}".format(len(events)),
            "- 结果截断：{0}".format("是" if truncated else "否"),
            "",
            "## 严重级别统计",
            "",
            "| 严重级别 | 数量 |",
            "| --- | ---: |",
        ]
        if severity_counts:
            for severity in sorted(severity_counts):
                lines.append(
                    "| {0} | {1} |".format(
                        self._cell(severity),
                        severity_counts[severity],
                    )
                )
        else:
            lines.append("| 无事件 | 0 |")

        lines.extend(
            [
                "",
                "## 事件类型统计",
                "",
                "| 事件类型 | 中文名称 | 数量 |",
                "| --- | --- | ---: |",
            ]
        )
        if type_counts:
            for event_type in sorted(type_counts):
                lines.append(
                    "| `{0}` | {1} | {2} |".format(
                        self._cell(event_type),
                        self._cell(
                            self.EVENT_LABELS.get(
                                event_type,
                                event_type,
                            )
                        ),
                        type_counts[event_type],
                    )
                )
        else:
            lines.append("| 无事件 | 无事件 | 0 |")

        lines.extend(
            [
                "",
                "## 事件时间线",
                "",
                (
                    "| 时间 | 严重级别 | 事件 | 处置状态 | "
                    "摄像头 | 区域 | 目标 | 轨迹 | 事件编号 | "
                    "证据路径 |"
                ),
                (
                    "| --- | --- | --- | --- | --- | --- | --- | "
                    "---: | --- | --- |"
                ),
            ]
        )
        if events:
            for event in reversed(events):
                event_type = str(
                    event.get("event_type") or "UNKNOWN"
                )
                lines.append(
                    (
                        "| {0} | {1} | {2} | {3} | {4} | {5} | "
                        "{6} | {7} | `{8}` | {9} |"
                    ).format(
                        self._cell(event.get("timestamp")),
                        self._cell(event.get("severity")),
                        self._cell(
                            self.EVENT_LABELS.get(
                                event_type,
                                event_type,
                            )
                        ),
                        (
                            "已处理"
                            if event.get("status")
                            == "ACKNOWLEDGED"
                            else "待处理"
                        ),
                        self._cell(event.get("camera_id")),
                        self._cell(
                            event.get("zone_name")
                            or event.get("zone_id")
                        ),
                        self._cell(event.get("object_class")),
                        self._cell(
                            event.get("track_id")
                            if event.get("track_id") is not None
                            else "aggregate"
                        ),
                        self._cell(event.get("event_id")),
                        self._cell(
                            event.get("evidence_path") or "无"
                        ),
                    )
                )
        else:
            lines.append(
                "| 无事件 | - | - | - | - | - | - | - | - | - |"
            )
        lines.extend(
            [
                "",
                "---",
                "",
                (
                    "本报告由 Jetson 上的确定性本地工具生成，"
                    "未向外部模型发送事件明细。"
                ),
                "",
            ]
        )
        return "\n".join(lines)

    def _write_atomic(self, path, content):
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        self._require_inside(directory, self.report_root)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".report-",
            suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def _validate_date(value):
        if not isinstance(value, str):
            raise ReportGenerationUnavailable(
                "date must be YYYY-MM-DD"
            )
        try:
            parsed = datetime.datetime.strptime(
                value,
                "%Y-%m-%d",
            )
        except ValueError as error:
            raise ReportGenerationUnavailable(
                "date must be YYYY-MM-DD"
            ) from error
        if parsed.strftime("%Y-%m-%d") != value:
            raise ReportGenerationUnavailable(
                "date must be YYYY-MM-DD"
            )

    @staticmethod
    def _optional_filter(value, name):
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value.strip()) > 64
        ):
            raise ReportGenerationUnavailable(
                "{0} must contain 1 to 64 characters".format(name)
            )
        return value.strip()

    @staticmethod
    def _safe_component(value):
        safe = "".join(
            character
            if character.isalnum() or character in ("-", "_", "+")
            else "_"
            for character in str(value)
        )
        if not safe:
            raise ReportGenerationUnavailable(
                "report filename component is empty"
            )
        return safe

    @staticmethod
    def _cell(value):
        return str(value if value is not None else "").replace(
            "|",
            "\\|",
        ).replace("\r", " ").replace("\n", " ")

    @staticmethod
    def _require_inside(path, root):
        path = os.path.realpath(os.path.abspath(path))
        root = os.path.realpath(os.path.abspath(root))
        try:
            inside = os.path.commonpath([path, root]) == root
        except ValueError:
            inside = False
        if not inside:
            raise ReportGenerationUnavailable(
                "report path escapes the project"
            )
