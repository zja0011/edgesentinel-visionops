import hashlib
import os
import tempfile
import unittest

from packages.api.agent_report_service import (
    AgentReportIntegrityError,
    AgentReportNotFound,
    AgentReportService,
)


TASK_ID = "task_0123456789abcdef0123456789abcdef"


def make_task(result=None):
    tool_results = []
    if result is not None:
        tool_results.append(
            {
                "tool_name": "report.generate",
                "status": "SUCCEEDED",
                "result": result,
            }
        )
    return {
        "task_id": TASK_ID,
        "status": "COMPLETED",
        "tool_results": tool_results,
    }


class AgentReportServiceTests(unittest.TestCase):
    def _report(self, directory):
        content = (
            "# EdgeSentinel VisionOps 每日事件报告\n\n"
            "test report\n"
        ).encode("utf-8")
        relative_path = "data/reports/2026-07-27/test.md"
        absolute_path = os.path.join(
            directory,
            *relative_path.split("/"),
        )
        os.makedirs(os.path.dirname(absolute_path))
        with open(absolute_path, "wb") as report_file:
            report_file.write(content)
        result = {
            "report_id": "rpt_test",
            "date": "2026-07-27",
            "event_count": 2,
            "report_path": relative_path,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        return absolute_path, result, content

    def test_adds_task_url_and_resolves_verified_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            absolute_path, result, content = self._report(
                directory
            )
            service = AgentReportService(directory)
            task = make_task(result)

            payload = service.add_url(task)
            report = service.resolve(task)

            self.assertEqual(
                payload["report_url"],
                (
                    "/api/v1/agent/tasks/{0}/report".format(
                        TASK_ID
                    )
                ),
            )
            self.assertEqual(report["content"], content)
            self.assertEqual(report["path"], absolute_path)
            self.assertEqual(report["event_count"], 2)

    def test_task_without_report_has_no_url(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentReportService(directory)

            self.assertNotIn(
                "report_url",
                service.add_url(make_task()),
            )
            with self.assertRaises(AgentReportNotFound):
                service.resolve(make_task())

    def test_rejects_path_escape_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            unused_path, result, unused_content = self._report(
                directory
            )
            escaped = dict(result)
            escaped["report_path"] = (
                "data/reports/../../outside.md"
            )
            with self.assertRaises(AgentReportNotFound):
                AgentReportService(directory).resolve(
                    make_task(escaped)
                )

            path = os.path.join(
                directory,
                *result["report_path"].split("/"),
            )
            with open(path, "ab") as report_file:
                report_file.write(b"tampered")
            with self.assertRaises(AgentReportIntegrityError):
                AgentReportService(directory).resolve(
                    make_task(result)
                )


if __name__ == "__main__":
    unittest.main()
