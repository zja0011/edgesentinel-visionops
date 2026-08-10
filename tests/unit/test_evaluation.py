import json
import os
import tempfile
import unittest

from apps.run_agent_evaluation import (
    IsolatedAgentCaseExecutor,
    run_evaluation,
)
from packages.harness.evaluation import (
    EvaluationDataset,
    EvaluationReportStore,
    EvaluationReportUnavailable,
    EvaluationValidationError,
    HarnessEvaluationRunner,
)


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
DATASET_PATH = os.path.join(
    PROJECT_DIR, "evals", "agent-routing-v1.json"
)


class EvaluationDatasetTests(unittest.TestCase):
    def test_loads_versioned_dataset_with_stable_hash(self):
        dataset = EvaluationDataset.load(DATASET_PATH)
        self.assertEqual(
            dataset.dataset_id, "edgesentinel.agent-routing"
        )
        self.assertEqual(dataset.version, "1.0.0")
        self.assertEqual(len(dataset.cases), 7)
        self.assertEqual(len(dataset.source_sha256), 64)

    def test_rejects_unknown_fields(self):
        with open(DATASET_PATH, "r", encoding="utf-8") as source:
            payload = json.load(source)
        payload["unexpected"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "invalid.json")
            with open(path, "w", encoding="utf-8") as output:
                json.dump(payload, output)
            with self.assertRaises(EvaluationValidationError):
                EvaluationDataset.load(path)

    def test_rejects_duplicate_case_ids(self):
        with open(DATASET_PATH, "r", encoding="utf-8") as source:
            payload = json.load(source)
        payload["cases"].append(dict(payload["cases"][0]))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "duplicate.json")
            with open(path, "w", encoding="utf-8") as output:
                json.dump(payload, output)
            with self.assertRaises(EvaluationValidationError):
                EvaluationDataset.load(path)


class HarnessEvaluationRunnerTests(unittest.TestCase):
    def test_real_isolated_agent_path_passes_all_cases(self):
        dataset = EvaluationDataset.load(DATASET_PATH)
        report = HarnessEvaluationRunner(
            dataset, IsolatedAgentCaseExecutor()
        ).run()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["summary"]["passed_cases"], 7)
        self.assertEqual(
            report["metrics"]["tool_selection_accuracy"]["rate"],
            1.0,
        )
        self.assertEqual(
            report["metrics"]["argument_accuracy"]["rate"], 1.0
        )
        self.assertEqual(
            report["metrics"]["unexpected_policy_violations"], 0
        )
        self.assertFalse(report["runtime"]["external_requests"])
        self.assertFalse(report["runtime"]["device_tools_executed"])
        self.assertTrue(report["read_only"])
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("摄像头里面现在站着几位", serialized)
        self.assertNotIn("How many people", serialized)

    def test_failed_safety_case_is_reported_as_violation(self):
        dataset = EvaluationDataset.load(DATASET_PATH)
        delegate = IsolatedAgentCaseExecutor()

        def execute(case):
            observation = delegate(case)
            if case["category"] == "safety":
                observation["executed_handler_count"] = 1
            return observation

        report = HarnessEvaluationRunner(dataset, execute).run()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(
            report["metrics"]["unexpected_policy_violations"], 1
        )


class EvaluationReportStoreTests(unittest.TestCase):
    def test_saves_and_loads_latest_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report, path = run_evaluation(DATASET_PATH, directory)
            self.assertTrue(os.path.isfile(path))
            loaded = EvaluationReportStore(directory).latest()
            self.assertEqual(
                loaded["evaluation_id"], report["evaluation_id"]
            )

    def test_missing_report_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = os.path.join(directory, "not-created")
            with self.assertRaises(EvaluationReportUnavailable):
                EvaluationReportStore(missing).latest()
            self.assertFalse(os.path.exists(missing))

    @unittest.skipIf(
        os.name == "nt", "symbolic-link behavior is privilege-dependent"
    )
    def test_rejects_symlinked_latest_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report, path = run_evaluation(DATASET_PATH, directory)
            del report
            latest = os.path.join(directory, "latest.json")
            os.unlink(latest)
            os.symlink(path, latest)
            with self.assertRaises(EvaluationReportUnavailable):
                EvaluationReportStore(directory).latest()

    def test_api_exposes_only_the_latest_read_only_report(self):
        api_path = os.path.join(PROJECT_DIR, "apps", "api_server.py")
        with open(api_path, "r", encoding="utf-8") as source:
            api_source = source.read()
        self.assertIn(
            '"/api/v1/harness/evaluations/latest"', api_source
        )
        self.assertIn(
            "evaluation_report_store.latest()", api_source
        )
        self.assertNotIn(
            'post("/api/v1/harness/evaluations',
            api_source.lower(),
        )


if __name__ == "__main__":
    unittest.main()
