"""Bounded Agent execution budgets and cooperative cancellation."""

from decimal import Decimal, ROUND_HALF_UP
import re
import threading
import time


STOP_CODES = (
    "TASK_CANCELLED",
    "DEADLINE_EXCEEDED",
    "MODEL_CALL_BUDGET_EXCEEDED",
    "TOOL_CALL_BUDGET_EXCEEDED",
    "EXTERNAL_REQUEST_BUDGET_EXCEEDED",
    "MODEL_TOKEN_BUDGET_EXCEEDED",
    "MODEL_COST_BUDGET_EXCEEDED",
    "MODEL_USAGE_INVALID",
)


class AgentExecutionStopped(RuntimeError):
    def __init__(self, code, stage, snapshot):
        code = str(code)
        if code not in STOP_CODES:
            raise ValueError("invalid execution stop code")
        super(AgentExecutionStopped, self).__init__(code)
        self.code = code
        self.stage = str(stage)
        self.snapshot = dict(snapshot)


class ExecutionLimits(object):
    def __init__(
        self,
        max_wall_seconds=60.0,
        max_model_calls=5,
        max_tool_calls=8,
        max_external_tool_calls=2,
        max_total_tokens=16384,
    ):
        self.max_wall_seconds = self._bounded_float(
            "max_wall_seconds", max_wall_seconds, 1.0, 300.0
        )
        self.max_model_calls = self._bounded_int(
            "max_model_calls", max_model_calls, 1, 10
        )
        self.max_tool_calls = self._bounded_int(
            "max_tool_calls", max_tool_calls, 1, 32
        )
        self.max_external_tool_calls = self._bounded_int(
            "max_external_tool_calls",
            max_external_tool_calls,
            0,
            8,
        )
        self.max_total_tokens = self._bounded_int(
            "max_total_tokens", max_total_tokens, 128, 1048576
        )

    def to_dict(self):
        return {
            "max_wall_seconds": self.max_wall_seconds,
            "max_model_calls": self.max_model_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_external_tool_calls": (
                self.max_external_tool_calls
            ),
            "max_total_tokens": self.max_total_tokens,
        }

    @staticmethod
    def _bounded_int(name, value, minimum, maximum):
        if isinstance(value, bool):
            raise ValueError("{0} is invalid".format(name))
        value = int(value)
        if value < minimum or value > maximum:
            raise ValueError(
                "{0} must be between {1} and {2}".format(
                    name, minimum, maximum
                )
            )
        return value

    @staticmethod
    def _bounded_float(name, value, minimum, maximum):
        if isinstance(value, bool):
            raise ValueError("{0} is invalid".format(name))
        value = float(value)
        if value < minimum or value > maximum:
            raise ValueError(
                "{0} must be between {1} and {2}".format(
                    name, minimum, maximum
                )
            )
        return value


class ModelCostPolicy(object):
    """Optional operator-supplied rate card for cost estimates."""

    RATE_CARD_PATTERN = re.compile(r"^[a-zA-Z0-9._:-]{1,64}$")

    def __init__(
        self,
        input_usd_per_million=None,
        output_usd_per_million=None,
        max_estimated_cost_usd=None,
        rate_card_id=None,
    ):
        configured = any(
            value is not None
            for value in (
                input_usd_per_million,
                output_usd_per_million,
                max_estimated_cost_usd,
                rate_card_id,
            )
        )
        if not configured:
            self.available = False
            self.input_usd_per_million = None
            self.output_usd_per_million = None
            self.max_estimated_cost_usd = None
            self.rate_card_id = None
            return
        if (
            input_usd_per_million is None
            or output_usd_per_million is None
            or max_estimated_cost_usd is None
            or rate_card_id is None
        ):
            raise ValueError(
                "cost policy requires rates, cap, and rate_card_id"
            )
        self.input_usd_per_million = self._bounded_rate(
            "input_usd_per_million", input_usd_per_million
        )
        self.output_usd_per_million = self._bounded_rate(
            "output_usd_per_million", output_usd_per_million
        )
        self.max_estimated_cost_usd = self._bounded_rate(
            "max_estimated_cost_usd",
            max_estimated_cost_usd,
            allow_zero=False,
        )
        self.rate_card_id = str(rate_card_id)
        if not self.RATE_CARD_PATTERN.match(self.rate_card_id):
            raise ValueError("rate_card_id is invalid")
        self.available = True

    @staticmethod
    def _bounded_rate(name, value, allow_zero=True):
        if isinstance(value, bool):
            raise ValueError("{0} is invalid".format(name))
        value = float(value)
        minimum = 0.0 if allow_zero else 0.000001
        if value < minimum or value > 10000.0:
            raise ValueError("{0} is out of range".format(name))
        return value

    def to_dict(self, estimated_micro_usd=0):
        return {
            "available": self.available,
            "currency": "USD",
            "rate_card_id": self.rate_card_id,
            "input_usd_per_million": self.input_usd_per_million,
            "output_usd_per_million": self.output_usd_per_million,
            "max_estimated_cost_usd": self.max_estimated_cost_usd,
            "estimated_cost_usd": (
                round(float(estimated_micro_usd) / 1000000.0, 6)
                if self.available
                else None
            ),
        }

    def estimate_micro_usd(self, prompt_tokens, completion_tokens):
        if not self.available:
            return 0
        estimate = (
            Decimal(int(prompt_tokens))
            * Decimal(str(self.input_usd_per_million))
            + Decimal(int(completion_tokens))
            * Decimal(str(self.output_usd_per_million))
        )
        return int(estimate.quantize(Decimal("1"), ROUND_HALF_UP))

    @property
    def max_estimated_micro_usd(self):
        if not self.available:
            return None
        return int(
            (
                Decimal(str(self.max_estimated_cost_usd))
                * Decimal("1000000")
            ).quantize(Decimal("1"), ROUND_HALF_UP)
        )

class ExecutionControl(object):
    """Thread-safe task-local counters and cancellation signal."""

    def __init__(self, limits=None, clock=None, cost_policy=None):
        self.limits = limits or ExecutionLimits()
        if not isinstance(self.limits, ExecutionLimits):
            raise TypeError("limits must be ExecutionLimits")
        self._clock = clock or time.monotonic
        self.cost_policy = cost_policy or ModelCostPolicy()
        if not isinstance(self.cost_policy, ModelCostPolicy):
            raise TypeError("cost_policy must be ModelCostPolicy")
        self._started = float(self._clock())
        self._lock = threading.Lock()
        self._cancelled = False
        self._cancel_reason = None
        self._model_calls = 0
        self._tool_calls = 0
        self._external_tool_calls = 0
        self._model_usage_reports = 0
        self._model_usage_missing = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._estimated_micro_usd = 0
        self._stop_code = None
        self._stop_stage = None

    def request_cancel(self):
        with self._lock:
            if self._cancelled:
                return False
            self._cancelled = True
            self._cancel_reason = "USER_REQUESTED"
            return True

    def check(self, stage):
        with self._lock:
            self._check_locked(stage)
            return self._snapshot_locked()

    def consume_model_call(self, stage="before_model"):
        with self._lock:
            self._check_locked(stage)
            if self._model_calls >= self.limits.max_model_calls:
                self._stop_locked(
                    "MODEL_CALL_BUDGET_EXCEEDED", stage
                )
            self._model_calls += 1
            return self._snapshot_locked()

    def consume_tool_call(
        self, stage="before_tool", external_request=False
    ):
        with self._lock:
            self._check_locked(stage)
            if self._tool_calls >= self.limits.max_tool_calls:
                self._stop_locked(
                    "TOOL_CALL_BUDGET_EXCEEDED", stage
                )
            if (
                external_request
                and self._external_tool_calls
                >= self.limits.max_external_tool_calls
            ):
                self._stop_locked(
                    "EXTERNAL_REQUEST_BUDGET_EXCEEDED", stage
                )
            self._tool_calls += 1
            if external_request:
                self._external_tool_calls += 1
            return self._snapshot_locked()

    def record_model_usage(self, usage, stage="after_model"):
        with self._lock:
            if usage is None:
                self._model_usage_missing += 1
                return self._snapshot_locked()
            normalized = self._normalize_usage_locked(usage, stage)
            self._model_usage_reports += 1
            self._prompt_tokens += normalized["prompt_tokens"]
            self._completion_tokens += normalized[
                "completion_tokens"
            ]
            self._total_tokens += normalized["total_tokens"]
            self._estimated_micro_usd += (
                self.cost_policy.estimate_micro_usd(
                    normalized["prompt_tokens"],
                    normalized["completion_tokens"],
                )
            )
            if self._total_tokens > self.limits.max_total_tokens:
                self._stop_locked(
                    "MODEL_TOKEN_BUDGET_EXCEEDED", stage
                )
            maximum_cost = (
                self.cost_policy.max_estimated_micro_usd
            )
            if (
                maximum_cost is not None
                and self._estimated_micro_usd > maximum_cost
            ):
                self._stop_locked(
                    "MODEL_COST_BUDGET_EXCEEDED", stage
                )
            return self._snapshot_locked()

    def snapshot(self):
        with self._lock:
            return self._snapshot_locked()

    def _check_locked(self, stage):
        if self._cancelled:
            self._stop_locked("TASK_CANCELLED", stage)
        if self._elapsed_locked() >= self.limits.max_wall_seconds:
            self._stop_locked("DEADLINE_EXCEEDED", stage)

    def _normalize_usage_locked(self, usage, stage):
        if not isinstance(usage, dict):
            self._stop_locked("MODEL_USAGE_INVALID", stage)
        result = {}
        for field in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            value = usage.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                self._stop_locked("MODEL_USAGE_INVALID", stage)
            result[field] = value
        if result["total_tokens"] < (
            result["prompt_tokens"]
            + result["completion_tokens"]
        ):
            self._stop_locked("MODEL_USAGE_INVALID", stage)
        return result

    def _stop_locked(self, code, stage):
        self._stop_code = code
        self._stop_stage = str(stage)
        raise AgentExecutionStopped(
            code,
            stage,
            self._snapshot_locked(),
        )

    def _elapsed_locked(self):
        return max(0.0, float(self._clock()) - self._started)

    def _snapshot_locked(self):
        elapsed = self._elapsed_locked()
        return {
            "schema_version": "1.0",
            "limits": self.limits.to_dict(),
            "usage": {
                "elapsed_seconds": round(elapsed, 3),
                "model_calls": self._model_calls,
                "tool_calls": self._tool_calls,
                "external_tool_calls": self._external_tool_calls,
                "model_usage_reports": self._model_usage_reports,
                "model_usage_missing": self._model_usage_missing,
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._total_tokens,
            },
            "cost_estimate": self.cost_policy.to_dict(
                self._estimated_micro_usd
            ),
            "remaining_wall_seconds": round(
                max(0.0, self.limits.max_wall_seconds - elapsed),
                3,
            ),
            "cancel_requested": self._cancelled,
            "cancel_reason": self._cancel_reason,
            "stop_code": self._stop_code,
            "stop_stage": self._stop_stage,
            "cooperative": True,
            "force_terminated": False,
        }
