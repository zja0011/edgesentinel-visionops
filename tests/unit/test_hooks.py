import time
import unittest

from packages.harness.hooks import (
    HOOK_POINTS,
    HookDefinition,
    HookDispatcher,
    HookDispatchError,
    build_default_hook_dispatcher,
)


class MemoryRecorder(object):
    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(dict(record))


class HookDispatcherTests(unittest.TestCase):
    def test_default_catalog_covers_six_lifecycle_points(self):
        dispatcher = build_default_hook_dispatcher()
        hooks = dispatcher.list_public()

        self.assertEqual(len(hooks), 6)
        self.assertEqual(
            {hook["point"] for hook in hooks},
            set(HOOK_POINTS),
        )
        self.assertEqual(
            next(
                hook
                for hook in hooks
                if hook["point"] == "before_tool"
            )["failure_policy"],
            "FAIL_CLOSED",
        )

    def test_records_success_without_payload_exposure(self):
        audit = MemoryRecorder()
        trace = MemoryRecorder()
        dispatcher = HookDispatcher(
            [
                HookDefinition(
                    "guard.example",
                    "before_tool",
                    lambda payload: {"allow": True},
                    description="Allow a test tool.",
                )
            ],
            audit_recorder=audit,
            trace_recorder=trace,
        )

        result = dispatcher.dispatch(
            "before_tool",
            {
                "task_id": "task_" + ("a" * 32),
                "step": 1,
                "tool_name": "event.query",
                "api_key": "must-not-be-recorded",
            },
        )

        self.assertTrue(result["allowed"])
        self.assertEqual(audit.records, trace.records)
        record = audit.records[0]
        self.assertEqual(record["status"], "SUCCEEDED")
        self.assertEqual(record["decision"], "ALLOW")
        self.assertNotIn("api_key", record)
        self.assertNotIn("tool_name", record)

    def test_fail_closed_denial_raises(self):
        dispatcher = HookDispatcher(
            [
                HookDefinition(
                    "guard.deny",
                    "before_tool",
                    lambda payload: {
                        "allow": False,
                        "code": "TEST_DENIED",
                    },
                    description="Deny the test request.",
                )
            ]
        )

        with self.assertRaises(HookDispatchError) as context:
            dispatcher.dispatch(
                "before_tool",
                {"task_id": "task_" + ("b" * 32), "step": 1},
            )

        self.assertEqual(context.exception.code, "TEST_DENIED")

    def test_timeout_is_bounded_and_fail_closed(self):
        def slow_hook(_payload):
            time.sleep(0.2)
            return {"allow": True}

        dispatcher = HookDispatcher(
            [
                HookDefinition(
                    "guard.timeout",
                    "before_model",
                    slow_hook,
                    timeout_ms=20,
                    description="Exercise the timeout boundary.",
                )
            ]
        )
        started = time.monotonic()

        with self.assertRaises(HookDispatchError) as context:
            dispatcher.dispatch(
                "before_model",
                {"task_id": "task_" + ("c" * 32), "step": 1},
            )

        self.assertEqual(context.exception.code, "HOOK_TIMEOUT")
        self.assertLess(time.monotonic() - started, 0.15)

    def test_continue_policy_records_failure_without_raising(self):
        def broken_hook(_payload):
            raise RuntimeError("private failure")

        dispatcher = HookDispatcher(
            [
                HookDefinition(
                    "observer.broken",
                    "after_tool",
                    broken_hook,
                    failure_policy="CONTINUE",
                    description="Record and continue after failure.",
                )
            ]
        )

        result = dispatcher.dispatch(
            "after_tool",
            {"task_id": "task_" + ("d" * 32), "step": 1},
        )

        self.assertFalse(result["allowed"])
        self.assertEqual(
            result["records"][0]["error_code"],
            "HOOK_EXECUTION_FAILED",
        )

    def test_before_tool_guard_denies_unadvertised_tool(self):
        dispatcher = build_default_hook_dispatcher()

        with self.assertRaises(HookDispatchError) as context:
            dispatcher.dispatch(
                "before_tool",
                {
                    "task_id": "task_" + ("e" * 32),
                    "step": 1,
                    "tool_name": "system.shell",
                    "visible_tool_names": ["event.query"],
                },
            )

        self.assertEqual(
            context.exception.code,
            "TOOL_NOT_VISIBLE",
        )


if __name__ == "__main__":
    unittest.main()
