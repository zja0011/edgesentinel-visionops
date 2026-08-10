"""Safe, integrity-checked access to Agent-created reports."""

import hashlib
import os
from urllib.parse import quote


class AgentReportNotFound(LookupError):
    """Raised when a task has no safely resolvable report."""


class AgentReportIntegrityError(RuntimeError):
    """Raised when a report no longer matches its tool result."""


class AgentReportService(object):
    MAX_REPORT_BYTES = 2 * 1024 * 1024

    def __init__(self, project_dir):
        self.project_dir = os.path.realpath(
            os.path.abspath(project_dir)
        )
        self.report_directory = os.path.realpath(
            os.path.join(
                self.project_dir,
                "data",
                "reports",
            )
        )

    def add_url(self, task):
        payload = dict(task)
        if self._report_result(task) is not None:
            task_id = quote(str(task["task_id"]), safe="")
            payload["report_url"] = (
                "/api/v1/agent/tasks/{0}/report".format(
                    task_id
                )
            )
        return payload

    def resolve(self, task):
        result = self._report_result(task)
        if result is None:
            raise AgentReportNotFound(
                "task has no completed report"
            )
        stored_path = result.get("report_path")
        if (
            not isinstance(stored_path, str)
            or not stored_path
            or os.path.isabs(stored_path)
        ):
            raise AgentReportNotFound(
                "report path is unavailable"
            )
        candidate = os.path.realpath(
            os.path.abspath(
                os.path.join(self.project_dir, stored_path)
            )
        )
        try:
            common_root = os.path.commonpath(
                [self.report_directory, candidate]
            )
        except ValueError:
            common_root = ""
        if common_root != self.report_directory:
            raise AgentReportNotFound(
                "report path is outside the report directory"
            )
        if os.path.splitext(candidate)[1].lower() != ".md":
            raise AgentReportNotFound(
                "unsupported report file type"
            )
        if not os.path.isfile(candidate):
            raise AgentReportNotFound(
                "report file does not exist"
            )
        try:
            size = os.path.getsize(candidate)
            if size <= 0 or size > self.MAX_REPORT_BYTES:
                raise AgentReportIntegrityError(
                    "report size is invalid"
                )
            with open(candidate, "rb") as report_file:
                content = report_file.read(
                    self.MAX_REPORT_BYTES + 1
                )
        except OSError as error:
            raise AgentReportNotFound(
                "report file is unavailable"
            ) from error
        if len(content) != size:
            raise AgentReportIntegrityError(
                "report size changed while reading"
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AgentReportIntegrityError(
                "report is not valid UTF-8"
            ) from error
        if not text.startswith(
            "# EdgeSentinel VisionOps 每日事件报告"
        ):
            raise AgentReportIntegrityError(
                "report header is invalid"
            )
        recorded_size = result.get("bytes")
        recorded_sha256 = str(result.get("sha256") or "").lower()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if (
            not isinstance(recorded_size, int)
            or recorded_size != size
            or recorded_sha256 != actual_sha256
        ):
            raise AgentReportIntegrityError(
                "report does not match its audit result"
            )
        return {
            "content": content,
            "path": candidate,
            "filename": os.path.basename(candidate),
            "bytes": size,
            "sha256": actual_sha256,
            "report_id": result.get("report_id"),
            "date": result.get("date"),
            "event_count": result.get("event_count"),
        }

    @staticmethod
    def _report_result(task):
        tool_results = task.get("tool_results") or []
        for tool_result in reversed(tool_results):
            if (
                tool_result.get("tool_name") == "report.generate"
                and tool_result.get("status") == "SUCCEEDED"
                and isinstance(tool_result.get("result"), dict)
            ):
                return tool_result["result"]
        return None
