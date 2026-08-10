import unittest

from packages.harness.execution_control import (
    AgentExecutionStopped,
    ExecutionControl,
    ExecutionLimits,
    ModelCostPolicy,
)


class MutableClock(object):
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class ExecutionControlTests(unittest.TestCase):
    def test_tracks_bounded_model_tool_and_external_usage(self):
        control = ExecutionControl(
            ExecutionLimits(
                max_wall_seconds=30,
                max_model_calls=2,
                max_tool_calls=3,
                max_external_tool_calls=1,
                max_total_tokens=1000,
            )
        )
        control.consume_model_call()
        control.consume_tool_call()
        control.consume_tool_call(external_request=True)
        snapshot = control.snapshot()
        self.assertEqual(snapshot["usage"]["model_calls"], 1)
        self.assertEqual(snapshot["usage"]["tool_calls"], 2)
        self.assertEqual(
            snapshot["usage"]["external_tool_calls"], 1
        )
        self.assertTrue(snapshot["cooperative"])
        self.assertFalse(snapshot["force_terminated"])
        self.assertEqual(snapshot["usage"]["total_tokens"], 0)
        self.assertFalse(snapshot["cost_estimate"]["available"])

    def test_tracks_provider_tokens_and_configured_cost(self):
        control = ExecutionControl(
            ExecutionLimits(max_total_tokens=1000),
            cost_policy=ModelCostPolicy(
                input_usd_per_million=1.0,
                output_usd_per_million=2.0,
                max_estimated_cost_usd=0.01,
                rate_card_id="test-2026-08",
            ),
        )
        control.consume_model_call()
        snapshot = control.record_model_usage(
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            }
        )
        self.assertEqual(snapshot["usage"]["model_usage_reports"], 1)
        self.assertEqual(snapshot["usage"]["prompt_tokens"], 100)
        self.assertEqual(snapshot["usage"]["total_tokens"], 120)
        self.assertTrue(snapshot["cost_estimate"]["available"])
        self.assertEqual(
            snapshot["cost_estimate"]["estimated_cost_usd"],
            0.00014,
        )

    def test_missing_provider_usage_is_not_reported_as_zero_usage(self):
        control = ExecutionControl()
        control.consume_model_call()
        snapshot = control.record_model_usage(None)
        self.assertEqual(snapshot["usage"]["model_usage_reports"], 0)
        self.assertEqual(snapshot["usage"]["model_usage_missing"], 1)
        self.assertEqual(snapshot["usage"]["total_tokens"], 0)

    def test_stops_after_provider_exceeds_token_budget(self):
        control = ExecutionControl(
            ExecutionLimits(max_total_tokens=128)
        )
        with self.assertRaises(AgentExecutionStopped) as captured:
            control.record_model_usage(
                {
                    "prompt_tokens": 100,
                    "completion_tokens": 40,
                    "total_tokens": 140,
                }
            )
        self.assertEqual(
            captured.exception.code,
            "MODEL_TOKEN_BUDGET_EXCEEDED",
        )
        self.assertEqual(
            captured.exception.snapshot["usage"]["total_tokens"],
            140,
        )

    def test_stops_after_estimated_cost_exceeds_cap(self):
        control = ExecutionControl(
            cost_policy=ModelCostPolicy(
                input_usd_per_million=10.0,
                output_usd_per_million=10.0,
                max_estimated_cost_usd=0.001,
                rate_card_id="test-cap",
            )
        )
        with self.assertRaises(AgentExecutionStopped) as captured:
            control.record_model_usage(
                {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                }
            )
        self.assertEqual(
            captured.exception.code,
            "MODEL_COST_BUDGET_EXCEEDED",
        )

    def test_rejects_model_call_over_budget(self):
        control = ExecutionControl(
            ExecutionLimits(max_model_calls=1)
        )
        control.consume_model_call()
        with self.assertRaises(AgentExecutionStopped) as captured:
            control.consume_model_call()
        self.assertEqual(
            captured.exception.code,
            "MODEL_CALL_BUDGET_EXCEEDED",
        )

    def test_rejects_external_call_over_budget(self):
        control = ExecutionControl(
            ExecutionLimits(max_external_tool_calls=0)
        )
        with self.assertRaises(AgentExecutionStopped) as captured:
            control.consume_tool_call(external_request=True)
        self.assertEqual(
            captured.exception.code,
            "EXTERNAL_REQUEST_BUDGET_EXCEEDED",
        )
        self.assertEqual(
            captured.exception.snapshot["usage"]["tool_calls"], 0
        )

    def test_cancel_is_idempotent_and_stops_at_safe_point(self):
        control = ExecutionControl()
        self.assertTrue(control.request_cancel())
        self.assertFalse(control.request_cancel())
        with self.assertRaises(AgentExecutionStopped) as captured:
            control.check("after_model")
        self.assertEqual(captured.exception.code, "TASK_CANCELLED")
        self.assertEqual(captured.exception.stage, "after_model")
        self.assertEqual(
            captured.exception.snapshot["cancel_reason"],
            "USER_REQUESTED",
        )

    def test_deadline_uses_monotonic_clock(self):
        clock = MutableClock()
        control = ExecutionControl(
            ExecutionLimits(max_wall_seconds=2),
            clock=clock,
        )
        clock.value += 2.1
        with self.assertRaises(AgentExecutionStopped) as captured:
            control.check("before_tool")
        self.assertEqual(
            captured.exception.code, "DEADLINE_EXCEEDED"
        )

    def test_limits_are_strictly_bounded(self):
        with self.assertRaises(ValueError):
            ExecutionLimits(max_wall_seconds=301)
        with self.assertRaises(ValueError):
            ExecutionLimits(max_model_calls=0)
        with self.assertRaises(ValueError):
            ExecutionLimits(max_tool_calls=33)
        with self.assertRaises(ValueError):
            ExecutionLimits(max_external_tool_calls=9)
        with self.assertRaises(ValueError):
            ExecutionLimits(max_total_tokens=127)
        with self.assertRaises(ValueError):
            ModelCostPolicy(input_usd_per_million=1.0)


if __name__ == "__main__":
    unittest.main()
