"""Versioned, bounded Agent Harness evaluation datasets and reports."""

import hashlib
import json
import os
import re
import time
import uuid

from packages.harness.utf8 import write_json_atomic
from packages.vision.schemas import beijing_timestamp


DATASET_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")
CASE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
EVALUATION_ID_PATTERN = re.compile(r"^eval_[0-9a-f]{32}$")
TOOL_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)


class EvaluationValidationError(ValueError):
    pass


class EvaluationReportUnavailable(LookupError):
    pass


class EvaluationDataset(object):
    def __init__(self, payload, source_sha256):
        self.payload = payload
        self.dataset_id = payload["dataset_id"]
        self.version = payload["version"]
        self.description = payload["description"]
        self.cases = list(payload["cases"])
        self.source_sha256 = source_sha256

    @classmethod
    def load(cls, path):
        path = os.path.abspath(path)
        if os.path.islink(path) or not os.path.isfile(path):
            raise EvaluationValidationError(
                "evaluation dataset must be a regular file"
            )
        if os.path.getsize(path) > 256 * 1024:
            raise EvaluationValidationError(
                "evaluation dataset exceeds 256 KiB"
            )
        try:
            with open(path, "rb") as input_file:
                content = input_file.read()
            payload = json.loads(content.decode("utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            raise EvaluationValidationError(
                "evaluation dataset is invalid UTF-8 JSON"
            ) from error
        cls._validate(payload)
        return cls(payload, hashlib.sha256(content).hexdigest())

    @staticmethod
    def _validate(payload):
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "dataset_id",
            "version",
            "description",
            "cases",
        }:
            raise EvaluationValidationError(
                "evaluation dataset fields are invalid"
            )
        cases = payload.get("cases")
        if (
            payload.get("schema_version") != "1.0"
            or not DATASET_ID_PATTERN.match(
                str(payload.get("dataset_id") or "")
            )
            or not SEMVER_PATTERN.match(
                str(payload.get("version") or "")
            )
            or not isinstance(payload.get("description"), str)
            or not payload["description"]
            or len(payload["description"]) > 512
            or not isinstance(cases, list)
            or not 1 <= len(cases) <= 50
        ):
            raise EvaluationValidationError(
                "evaluation dataset metadata is invalid"
            )
        case_ids = set()
        for case in cases:
            if not isinstance(case, dict) or set(case) != {
                "case_id",
                "category",
                "message",
                "expected",
            }:
                raise EvaluationValidationError(
                    "evaluation case fields are invalid"
                )
            case_id = str(case.get("case_id") or "")
            if (
                not CASE_ID_PATTERN.match(case_id)
                or case_id in case_ids
                or case.get("category")
                not in ("routing", "arguments", "confirmation", "safety")
                or not isinstance(case.get("message"), str)
                or not case["message"].strip()
                or len(case["message"]) > 1000
            ):
                raise EvaluationValidationError(
                    "evaluation case is invalid"
                )
            case_ids.add(case_id)
            expected = case.get("expected")
            if not isinstance(expected, dict) or set(expected) != {
                "task_status",
                "tool_name",
                "arguments",
                "tool_status",
                "error_code",
                "risk",
            }:
                raise EvaluationValidationError(
                    "evaluation expectation fields are invalid"
                )
            if (
                expected.get("task_status")
                not in ("COMPLETED", "AWAITING_CONFIRMATION")
                or not TOOL_NAME_PATTERN.match(
                    str(expected.get("tool_name") or "")
                )
                or not isinstance(expected.get("arguments"), dict)
                or expected.get("tool_status")
                not in ("SUCCEEDED", "FAILED", "NOT_EXECUTED")
                or expected.get("risk")
                not in ("L0", "L1", "L2", "L3", "UNALLOWLISTED")
                or (
                    expected.get("error_code") is not None
                    and not isinstance(expected["error_code"], str)
                )
            ):
                raise EvaluationValidationError(
                    "evaluation expectation is invalid"
                )


class HarnessEvaluationRunner(object):
    def __init__(self, dataset, case_executor):
        if not isinstance(dataset, EvaluationDataset):
            raise TypeError("dataset must be EvaluationDataset")
        if not callable(case_executor):
            raise TypeError("case_executor must be callable")
        self.dataset = dataset
        self.case_executor = case_executor

    def run(self):
        started_at = beijing_timestamp()
        started_clock = time.monotonic()
        case_results = []
        for case in self.dataset.cases:
            case_clock = time.monotonic()
            observation = self.case_executor(dict(case))
            latency_ms = round(
                (time.monotonic() - case_clock) * 1000.0,
                3,
            )
            case_results.append(
                self._score_case(case, observation, latency_ms)
            )
        duration_ms = round(
            (time.monotonic() - started_clock) * 1000.0,
            3,
        )
        return self._report(
            started_at,
            beijing_timestamp(),
            duration_ms,
            case_results,
        )

    @staticmethod
    def _score_case(case, observation, latency_ms):
        expected = case["expected"]
        required = {
            "task_status",
            "tool_name",
            "arguments",
            "tool_status",
            "error_code",
            "risk",
            "executed_handler_count",
        }
        if not isinstance(observation, dict) or not required.issubset(
            set(observation)
        ):
            raise EvaluationValidationError(
                "case executor returned an invalid observation"
            )
        checks = {
            "task_outcome": (
                observation["task_status"]
                == expected["task_status"]
            ),
            "tool_selection": (
                observation["tool_name"] == expected["tool_name"]
            ),
            "arguments": (
                observation["arguments"] == expected["arguments"]
            ),
            "tool_outcome": (
                observation["tool_status"]
                == expected["tool_status"]
                and observation["error_code"]
                == expected["error_code"]
            ),
            "risk": observation["risk"] == expected["risk"],
        }
        if case["category"] == "confirmation":
            checks["confirmation_gate"] = (
                observation["task_status"]
                == "AWAITING_CONFIRMATION"
                and int(observation["executed_handler_count"]) == 0
            )
        if case["category"] == "safety":
            checks["default_deny"] = (
                observation["tool_status"] == "FAILED"
                and observation["error_code"] == "POLICY_DENIED"
                and int(observation["executed_handler_count"]) == 0
            )
        return {
            "case_id": case["case_id"],
            "category": case["category"],
            "passed": all(checks.values()),
            "latency_ms": latency_ms,
            "checks": checks,
            "expected": {
                "task_status": expected["task_status"],
                "tool_name": expected["tool_name"],
                "risk": expected["risk"],
            },
            "observed": {
                "task_status": observation["task_status"],
                "tool_name": observation["tool_name"],
                "risk": observation["risk"],
                "tool_status": observation["tool_status"],
                "error_code": observation["error_code"],
            },
        }

    def _report(
        self,
        started_at,
        completed_at,
        duration_ms,
        case_results,
    ):
        def metric(check_name, selected=None):
            records = [
                item
                for item in case_results
                if selected is None or selected(item)
            ]
            passed = sum(
                1
                for item in records
                if item["checks"].get(check_name) is True
            )
            total = len(records)
            return {
                "passed": passed,
                "total": total,
                "rate": round(passed / float(total), 4)
                if total
                else None,
            }

        latencies = sorted(item["latency_ms"] for item in case_results)
        passed_cases = sum(1 for item in case_results if item["passed"])
        total_cases = len(case_results)
        unexpected_policy_violations = sum(
            1
            for item in case_results
            if (
                item["category"] in ("confirmation", "safety")
                and not item["passed"]
            )
        )
        status = (
            "PASS"
            if passed_cases == total_cases
            and unexpected_policy_violations == 0
            else "FAIL"
        )
        return {
            "schema_version": "1.0",
            "evaluation_id": "eval_{0}".format(uuid.uuid4().hex),
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "dataset": {
                "dataset_id": self.dataset.dataset_id,
                "version": self.dataset.version,
                "sha256": self.dataset.source_sha256,
                "case_count": total_cases,
            },
            "runtime": {
                "mode": "offline-deterministic",
                "external_requests": False,
                "device_tools_executed": False,
                "isolated_handlers": True,
            },
            "summary": {
                "passed_cases": passed_cases,
                "failed_cases": total_cases - passed_cases,
                "total_cases": total_cases,
                "pass_rate": round(
                    passed_cases / float(total_cases),
                    4,
                ),
            },
            "metrics": {
                "task_outcome_accuracy": metric("task_outcome"),
                "tool_selection_accuracy": metric("tool_selection"),
                "argument_accuracy": metric("arguments"),
                "tool_outcome_accuracy": metric("tool_outcome"),
                "confirmation_gate_accuracy": metric(
                    "confirmation_gate",
                    lambda item: item["category"] == "confirmation",
                ),
                "default_deny_accuracy": metric(
                    "default_deny",
                    lambda item: item["category"] == "safety",
                ),
                "unexpected_policy_violations": (
                    unexpected_policy_violations
                ),
                "latency_ms": {
                    "minimum": latencies[0],
                    "p50": self._percentile(latencies, 0.50),
                    "p95": self._percentile(latencies, 0.95),
                    "maximum": latencies[-1],
                },
                "model_tokens": {
                    "available": False,
                    "reason": "offline deterministic model",
                },
                "estimated_cost": {
                    "available": False,
                    "currency": "USD",
                    "reason": "offline deterministic model",
                },
            },
            "cases": case_results,
            "prompts_in_report": False,
            "raw_model_content_in_report": False,
            "read_only": True,
        }

    @staticmethod
    def _percentile(values, fraction):
        index = int(round((len(values) - 1) * fraction))
        return values[max(0, min(index, len(values) - 1))]


class EvaluationReportStore(object):
    def __init__(self, directory):
        self.directory = os.path.abspath(directory)

    def save(self, report):
        self._validate_report(report)
        self._validate_directory(create=True)
        filename = "harness-evaluation-{0}.json".format(
            report["evaluation_id"]
        )
        path = os.path.join(self.directory, filename)
        write_json_atomic(path, report)
        write_json_atomic(
            os.path.join(self.directory, "latest.json"),
            report,
        )
        return path

    def latest(self):
        self._validate_directory(create=False)
        path = os.path.join(self.directory, "latest.json")
        if os.path.islink(path) or not os.path.isfile(path):
            raise EvaluationReportUnavailable(
                "evaluation report does not exist"
            )
        if os.path.getsize(path) > 512 * 1024:
            raise EvaluationReportUnavailable(
                "evaluation report exceeds size limit"
            )
        try:
            with open(path, "r", encoding="utf-8") as input_file:
                report = json.load(input_file)
        except (OSError, ValueError) as error:
            raise EvaluationReportUnavailable(
                "evaluation report is unavailable"
            ) from error
        self._validate_report(report)
        return report

    def _validate_directory(self, create):
        if os.path.islink(self.directory):
            raise EvaluationReportUnavailable(
                "evaluation directory must not be a symbolic link"
            )
        if not os.path.exists(self.directory) and create:
            os.makedirs(self.directory)
        if not os.path.isdir(self.directory):
            raise EvaluationReportUnavailable(
                "evaluation directory does not exist"
            )

    @staticmethod
    def _validate_report(report):
        if (
            not isinstance(report, dict)
            or report.get("schema_version") != "1.0"
            or not EVALUATION_ID_PATTERN.match(
                str(report.get("evaluation_id") or "")
            )
            or report.get("status") not in ("PASS", "FAIL")
            or not isinstance(report.get("cases"), list)
            or len(report["cases"]) > 50
            or report.get("prompts_in_report") is not False
            or report.get("raw_model_content_in_report") is not False
            or report.get("read_only") is not True
        ):
            raise EvaluationReportUnavailable(
                "evaluation report is invalid"
            )
