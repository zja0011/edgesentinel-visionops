"""Fail-closed model selection from process environment variables."""

import os
import threading
import time

from packages.harness.mock_model import OfflineMockModel
from packages.harness.model_gateway import (
    ChatCompletionsModelGateway,
    ModelGatewayError,
)
from packages.vision.schemas import beijing_timestamp


MODEL_MODE_ENV = "EDGESENTINEL_MODEL_MODE"
MODEL_PROVIDER_ENV = "EDGESENTINEL_MODEL_PROVIDER"
MODEL_ENDPOINT_ENV = "EDGESENTINEL_MODEL_ENDPOINT"
MODEL_NAME_ENV = "EDGESENTINEL_MODEL_NAME"
MODEL_API_KEY_ENV = "EDGESENTINEL_MODEL_API_KEY"
MODEL_TIMEOUT_ENV = "EDGESENTINEL_MODEL_TIMEOUT_SECONDS"
MODEL_MAX_TOKENS_ENV = "EDGESENTINEL_MODEL_MAX_TOKENS"
MODEL_RETRY_ATTEMPTS_ENV = "EDGESENTINEL_MODEL_RETRY_ATTEMPTS"
MODEL_RETRY_BACKOFF_ENV = "EDGESENTINEL_MODEL_RETRY_BACKOFF_SECONDS"
MODEL_CIRCUIT_THRESHOLD_ENV = (
    "EDGESENTINEL_MODEL_CIRCUIT_FAILURE_THRESHOLD"
)
MODEL_CIRCUIT_COOLDOWN_ENV = (
    "EDGESENTINEL_MODEL_CIRCUIT_COOLDOWN_SECONDS"
)
MODEL_OFFLINE_FALLBACK_ENV = (
    "EDGESENTINEL_MODEL_OFFLINE_FALLBACK"
)

DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"


class ModelConfigurationError(ValueError):
    pass


class ModelModeUnavailable(ValueError):
    pass


class SwitchableModel(object):
    """Select online or offline generation without restarting vision."""

    def __init__(
        self,
        configured_model,
        environ=None,
        clock=None,
        sleeper=None,
    ):
        self._lock = threading.RLock()
        values = os.environ if environ is None else environ
        self._retry_attempts = _bounded_int(
            values,
            MODEL_RETRY_ATTEMPTS_ENV,
            2,
            1,
            3,
        )
        self._retry_backoff_seconds = _bounded_float(
            values,
            MODEL_RETRY_BACKOFF_ENV,
            0.25,
            0.0,
            2.0,
        )
        self._failure_threshold = _bounded_int(
            values,
            MODEL_CIRCUIT_THRESHOLD_ENV,
            3,
            1,
            10,
        )
        self._cooldown_seconds = _bounded_float(
            values,
            MODEL_CIRCUIT_COOLDOWN_ENV,
            60.0,
            1.0,
            600.0,
        )
        self._offline_fallback_enabled = _boolean_value(
            values,
            MODEL_OFFLINE_FALLBACK_ENV,
            True,
        )
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._circuit_state = "CLOSED"
        self._circuit_opened_at = None
        self._probe_in_flight = False
        self._consecutive_failures = 0
        self._remote_requests = 0
        self._remote_successes = 0
        self._remote_failures = 0
        self._retry_count = 0
        self._fallback_count = 0
        self._last_failure_code = None
        self._last_failure_at = None
        self._models = {"offline": OfflineMockModel()}
        configured_summary = model_runtime_summary(configured_model)
        if configured_summary.get("mode") == "remote":
            self._models["remote"] = configured_model
            self._active_mode = "remote"
            self._boot_mode = "remote"
        else:
            self._active_mode = "offline"
            self._boot_mode = "offline"

    @property
    def name(self):
        with self._lock:
            return self._models[self._active_mode].name

    @property
    def identity(self):
        with self._lock:
            model = self._models[self._active_mode]
            return getattr(model, "identity", model.name)

    @property
    def active_mode(self):
        with self._lock:
            return self._active_mode

    @property
    def boot_mode(self):
        return self._boot_mode

    @property
    def available_modes(self):
        with self._lock:
            return sorted(self._models)

    def set_mode(self, mode):
        normalized = str(mode or "").strip().lower()
        with self._lock:
            if normalized not in self._models:
                raise ModelModeUnavailable(
                    "requested model mode is unavailable"
                )
            self._active_mode = normalized
            if normalized == "remote":
                self._reset_circuit_locked()
        return self.summary()

    def generate(self, context, tool_schemas=None, conversation=None):
        return self._generate(
            context,
            tool_schemas=tool_schemas,
            conversation=conversation,
            tool_choice=None,
        )

    def generate_with_tool_choice(
        self,
        context,
        tool_schemas=None,
        conversation=None,
        tool_choice="auto",
    ):
        return self._generate(
            context,
            tool_schemas=tool_schemas,
            conversation=conversation,
            tool_choice=tool_choice,
        )

    def _generate(
        self,
        context,
        tool_schemas=None,
        conversation=None,
        tool_choice=None,
    ):
        with self._lock:
            active_mode = self._active_mode
            model = self._models[active_mode]
        if active_mode == "offline":
            response = model.generate(
                context,
                tool_schemas=tool_schemas,
                conversation=conversation,
            )
            return self._mark_response(
                response,
                requested_mode="offline",
                served_mode="offline",
                attempts=1,
                fallback_used=False,
                fallback_reason=None,
            )
        return self._generate_remote(
            model,
            context,
            tool_schemas=tool_schemas,
            conversation=conversation,
            tool_choice=tool_choice,
        )

    def _generate_remote(
        self,
        model,
        context,
        tool_schemas=None,
        conversation=None,
        tool_choice=None,
    ):
        with self._lock:
            now = float(self._clock())
            if self._circuit_state == "OPEN":
                ready_at = (
                    float(self._circuit_opened_at)
                    + self._cooldown_seconds
                )
                if now < ready_at or self._probe_in_flight:
                    return self._fallback(
                        context,
                        tool_schemas,
                        conversation,
                        "MODEL_CIRCUIT_OPEN",
                        0,
                    )
                self._circuit_state = "HALF_OPEN"
                self._probe_in_flight = True
            elif self._circuit_state == "HALF_OPEN":
                return self._fallback(
                    context,
                    tool_schemas,
                    conversation,
                    "MODEL_CIRCUIT_OPEN",
                    0,
                )
            self._remote_requests += 1

        last_error = None
        attempts = 0
        for attempt in range(1, self._retry_attempts + 1):
            attempts = attempt
            try:
                if tool_choice is not None:
                    response = model.generate_with_tool_choice(
                        context,
                        tool_schemas=tool_schemas,
                        conversation=conversation,
                        tool_choice=tool_choice,
                    )
                else:
                    response = model.generate(
                        context,
                        tool_schemas=tool_schemas,
                        conversation=conversation,
                    )
            except ModelGatewayError as error:
                last_error = error
                if not error.retryable or attempt >= self._retry_attempts:
                    break
                with self._lock:
                    self._retry_count += 1
                delay = self._retry_backoff_seconds * attempt
                if delay > 0:
                    self._sleeper(delay)
                continue
            with self._lock:
                self._remote_successes += 1
                self._reset_circuit_locked()
            return self._mark_response(
                response,
                requested_mode="remote",
                served_mode="remote",
                attempts=attempts,
                fallback_used=False,
                fallback_reason=None,
            )

        if last_error is None:
            last_error = ModelGatewayError(
                "model request failed",
                code="MODEL_GATEWAY_ERROR",
            )
        with self._lock:
            self._remote_failures += 1
            self._consecutive_failures += 1
            self._last_failure_code = last_error.code
            self._last_failure_at = beijing_timestamp()
            self._probe_in_flight = False
            if (
                not last_error.retryable
                or self._consecutive_failures >= self._failure_threshold
                or self._circuit_state == "HALF_OPEN"
            ):
                self._circuit_state = "OPEN"
                self._circuit_opened_at = float(self._clock())
            else:
                self._circuit_state = "CLOSED"
        if not self._offline_fallback_enabled:
            raise last_error
        return self._fallback(
            context,
            tool_schemas,
            conversation,
            last_error.code,
            attempts,
        )

    def _fallback(
        self,
        context,
        tool_schemas,
        conversation,
        reason,
        attempts,
    ):
        if not self._offline_fallback_enabled:
            raise ModelGatewayError(
                "remote model circuit is open",
                code=str(reason),
                retryable=True,
            )
        with self._lock:
            self._fallback_count += 1
            offline_model = self._models["offline"]
        response = offline_model.generate(
            context,
            tool_schemas=tool_schemas,
            conversation=conversation,
        )
        if response.content:
            response.content = (
                "在线模型暂不可用，已自动使用离线规则模式。\n\n"
                + response.content
            )
        return self._mark_response(
            response,
            requested_mode="remote",
            served_mode="offline",
            attempts=attempts,
            fallback_used=True,
            fallback_reason=reason,
        )

    def _mark_response(
        self,
        response,
        requested_mode,
        served_mode,
        attempts,
        fallback_used,
        fallback_reason,
    ):
        with self._lock:
            circuit_state = self._circuit_state
        response.runtime = {
            "schema_version": "1.0",
            "requested_mode": requested_mode,
            "served_mode": served_mode,
            "remote_attempts": int(attempts),
            "retry_count": max(0, int(attempts) - 1),
            "fallback_used": bool(fallback_used),
            "fallback_reason": fallback_reason,
            "circuit_state": circuit_state,
        }
        return response

    def _reset_circuit_locked(self):
        self._circuit_state = "CLOSED"
        self._circuit_opened_at = None
        self._probe_in_flight = False
        self._consecutive_failures = 0

    def summary(self):
        with self._lock:
            summary = model_runtime_summary(
                self._models[self._active_mode]
            )
            summary["available_modes"] = sorted(self._models)
            summary["boot_mode"] = self._boot_mode
            summary["runtime_switchable"] = True
            summary["resilience"] = {
                "schema_version": "1.0",
                "enabled": "remote" in self._models,
                "circuit_state": self._circuit_state,
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self._failure_threshold,
                "cooldown_seconds": self._cooldown_seconds,
                "retry_max_attempts": self._retry_attempts,
                "retry_backoff_seconds": (
                    self._retry_backoff_seconds
                ),
                "offline_fallback_enabled": (
                    self._offline_fallback_enabled
                ),
                "remote_requests": self._remote_requests,
                "remote_successes": self._remote_successes,
                "remote_failures": self._remote_failures,
                "retry_count": self._retry_count,
                "fallback_count": self._fallback_count,
                "last_failure_code": self._last_failure_code,
                "last_failure_at": self._last_failure_at,
            }
            return summary


def build_model_from_environment(
    environ=None,
    transport=None,
    tool_choice="auto",
):
    """Build the offline model or an explicitly configured remote model."""
    values = os.environ if environ is None else environ
    mode = str(values.get(MODEL_MODE_ENV, "offline")).strip().lower()

    if mode == "offline":
        return OfflineMockModel()
    if mode != "remote":
        raise ModelConfigurationError(
            "{0} must be 'offline' or 'remote'".format(
                MODEL_MODE_ENV
            )
        )

    provider = str(
        values.get(MODEL_PROVIDER_ENV, "custom")
    ).strip().lower()
    if provider == "deepseek":
        endpoint = DEEPSEEK_ENDPOINT
        model_name = DEEPSEEK_MODEL
    elif provider == "custom":
        endpoint = _required(values, MODEL_ENDPOINT_ENV)
        model_name = _required(values, MODEL_NAME_ENV)
    else:
        raise ModelConfigurationError(
            "{0} must be 'deepseek' or 'custom'".format(
                MODEL_PROVIDER_ENV
            )
        )
    api_key = _required(values, MODEL_API_KEY_ENV)
    timeout_text = str(
        values.get(MODEL_TIMEOUT_ENV, "20")
    ).strip()
    try:
        timeout_seconds = float(timeout_text)
    except (TypeError, ValueError) as error:
        raise ModelConfigurationError(
            "{0} must be a number".format(MODEL_TIMEOUT_ENV)
        ) from error
    max_tokens_text = str(
        values.get(MODEL_MAX_TOKENS_ENV, "512")
    ).strip()
    try:
        max_tokens = int(max_tokens_text)
    except (TypeError, ValueError) as error:
        raise ModelConfigurationError(
            "{0} must be an integer".format(
                MODEL_MAX_TOKENS_ENV
            )
        ) from error

    try:
        return ChatCompletionsModelGateway(
            endpoint=endpoint,
            model=model_name,
            api_key=api_key,
            transport=transport,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            provider=provider,
        )
    except ValueError as error:
        raise ModelConfigurationError(str(error)) from error


def model_runtime_summary(model):
    """Return a log-safe summary that never contains credentials."""
    if isinstance(model, SwitchableModel):
        return model.summary()
    if isinstance(model, OfflineMockModel):
        return {
            "mode": "offline",
            "provider": "offline",
            "gateway": model.name,
            "model": model.name,
            "external_requests_enabled": False,
            "credential_source": None,
        }
    if isinstance(model, ChatCompletionsModelGateway):
        return {
            "mode": "remote",
            "provider": model.provider,
            "gateway": model.name,
            "model": model.model,
            "external_requests_enabled": True,
            "credential_source": "environment",
        }
    return {
        "mode": "custom",
        "provider": "custom",
        "gateway": getattr(model, "name", "unknown"),
        "model": getattr(model, "name", "unknown"),
        "external_requests_enabled": None,
        "credential_source": None,
    }


def _required(values, name):
    value = str(values.get(name, "")).strip()
    if not value:
        raise ModelConfigurationError(
            "{0} is required in remote mode".format(name)
        )
    return value


def _bounded_int(values, name, default, minimum, maximum):
    text = str(values.get(name, default)).strip()
    try:
        value = int(text)
    except (TypeError, ValueError) as error:
        raise ModelConfigurationError(
            "{0} must be an integer".format(name)
        ) from error
    if value < minimum or value > maximum:
        raise ModelConfigurationError(
            "{0} must be between {1} and {2}".format(
                name, minimum, maximum
            )
        )
    return value


def _bounded_float(values, name, default, minimum, maximum):
    text = str(values.get(name, default)).strip()
    try:
        value = float(text)
    except (TypeError, ValueError) as error:
        raise ModelConfigurationError(
            "{0} must be a number".format(name)
        ) from error
    if value < minimum or value > maximum:
        raise ModelConfigurationError(
            "{0} must be between {1} and {2}".format(
                name, minimum, maximum
            )
        )
    return value


def _boolean_value(values, name, default):
    raw = values.get(name)
    if raw is None:
        return bool(default)
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    raise ModelConfigurationError(
        "{0} must be true or false".format(name)
    )
