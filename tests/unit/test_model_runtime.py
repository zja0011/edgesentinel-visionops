import json
import unittest

from packages.harness.mock_model import (
    ModelResponse,
    OfflineMockModel,
)
from packages.harness.model_gateway import (
    ChatCompletionsModelGateway,
    ModelGatewayError,
)
from packages.harness.model_runtime import (
    MODEL_API_KEY_ENV,
    MODEL_ENDPOINT_ENV,
    MODEL_MODE_ENV,
    MODEL_PROVIDER_ENV,
    MODEL_NAME_ENV,
    MODEL_TIMEOUT_ENV,
    MODEL_MAX_TOKENS_ENV,
    MODEL_RETRY_ATTEMPTS_ENV,
    MODEL_RETRY_BACKOFF_ENV,
    MODEL_CIRCUIT_THRESHOLD_ENV,
    MODEL_CIRCUIT_COOLDOWN_ENV,
    MODEL_OFFLINE_FALLBACK_ENV,
    ModelConfigurationError,
    ModelModeUnavailable,
    SwitchableModel,
    build_model_from_environment,
    model_runtime_summary,
)


class SequencedRemoteModel(ChatCompletionsModelGateway):
    name = "chat-completions-compatible"
    identity = "chat-completions-compatible:remote-test"
    provider = "test"
    model = "remote-test"

    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0

    def generate(self, context, tool_schemas=None, conversation=None):
        self.calls += 1
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class ModelRuntimeTests(unittest.TestCase):
    def test_switchable_remote_runtime_can_toggle_offline_and_back(self):
        remote = build_model_from_environment(
            {
                MODEL_MODE_ENV: "remote",
                MODEL_PROVIDER_ENV: "deepseek",
                MODEL_API_KEY_ENV: "secret",
            }
        )
        model = SwitchableModel(remote)

        self.assertEqual(model.active_mode, "remote")
        self.assertEqual(model.available_modes, ["offline", "remote"])
        offline = model.set_mode("offline")
        self.assertEqual(offline["mode"], "offline")
        self.assertEqual(model.name, "offline-rule-mock")
        online = model.set_mode("remote")
        self.assertEqual(online["mode"], "remote")
        self.assertEqual(online["provider"], "deepseek")
        self.assertTrue(online["runtime_switchable"])

    def test_offline_runtime_rejects_unavailable_remote_mode(self):
        model = SwitchableModel(OfflineMockModel())

        self.assertEqual(model.available_modes, ["offline"])
        with self.assertRaises(ModelModeUnavailable):
            model.set_mode("remote")

    def test_defaults_to_offline_model(self):
        model = build_model_from_environment({})

        self.assertIsInstance(model, OfflineMockModel)
        self.assertEqual(
            model_runtime_summary(model)["mode"],
            "offline",
        )

    def test_builds_remote_gateway_from_environment(self):
        secret = "test-secret"
        model = build_model_from_environment(
            {
                MODEL_MODE_ENV: "remote",
                MODEL_PROVIDER_ENV: "custom",
                MODEL_ENDPOINT_ENV: (
                    "https://example.invalid/v1/chat/completions"
                ),
                MODEL_NAME_ENV: "test-model",
                MODEL_API_KEY_ENV: secret,
                MODEL_TIMEOUT_ENV: "9",
                MODEL_MAX_TOKENS_ENV: "256",
            }
        )

        self.assertIsInstance(
            model,
            ChatCompletionsModelGateway,
        )
        self.assertEqual(model.model, "test-model")
        self.assertEqual(model.timeout_seconds, 9.0)
        self.assertEqual(model.max_tokens, 256)
        summary = model_runtime_summary(model)
        self.assertEqual(summary["mode"], "remote")
        self.assertEqual(summary["provider"], "custom")
        self.assertEqual(
            summary["credential_source"],
            "environment",
        )
        self.assertNotIn(secret, json.dumps(summary))

    def test_remote_mode_requires_all_settings(self):
        base = {
            MODEL_MODE_ENV: "remote",
            MODEL_PROVIDER_ENV: "custom",
            MODEL_ENDPOINT_ENV: (
                "https://example.invalid/v1/chat/completions"
            ),
            MODEL_NAME_ENV: "test-model",
            MODEL_API_KEY_ENV: "secret",
        }
        for missing in (
            MODEL_ENDPOINT_ENV,
            MODEL_NAME_ENV,
            MODEL_API_KEY_ENV,
        ):
            values = dict(base)
            del values[missing]
            with self.subTest(missing=missing):
                with self.assertRaises(ModelConfigurationError):
                    build_model_from_environment(values)

    def test_rejects_unknown_mode_and_invalid_timeout(self):
        with self.assertRaises(ModelConfigurationError):
            build_model_from_environment(
                {MODEL_MODE_ENV: "automatic"}
            )
        with self.assertRaises(ModelConfigurationError):
            build_model_from_environment(
                {
                    MODEL_MODE_ENV: "remote",
                    MODEL_PROVIDER_ENV: "custom",
                    MODEL_ENDPOINT_ENV: (
                        "https://example.invalid/v1/chat/completions"
                    ),
                    MODEL_NAME_ENV: "test-model",
                    MODEL_API_KEY_ENV: "secret",
                    MODEL_TIMEOUT_ENV: "not-a-number",
                }
            )

    def test_builds_fixed_deepseek_preset(self):
        model = build_model_from_environment(
            {
                MODEL_MODE_ENV: "remote",
                MODEL_PROVIDER_ENV: "deepseek",
                MODEL_API_KEY_ENV: "secret",
            }
        )

        self.assertEqual(
            model.endpoint,
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(model.model, "deepseek-v4-flash")
        self.assertEqual(model.provider, "deepseek")

    def test_rejects_invalid_provider_and_max_tokens(self):
        with self.assertRaises(ModelConfigurationError):
            build_model_from_environment(
                {
                    MODEL_MODE_ENV: "remote",
                    MODEL_PROVIDER_ENV: "unknown",
                    MODEL_API_KEY_ENV: "secret",
                }
            )
        with self.assertRaises(ModelConfigurationError):
            build_model_from_environment(
                {
                    MODEL_MODE_ENV: "remote",
                    MODEL_PROVIDER_ENV: "deepseek",
                    MODEL_API_KEY_ENV: "secret",
                    MODEL_MAX_TOKENS_ENV: "invalid",
                }
            )

    def test_retries_retryable_failure_then_recovers_online(self):
        remote = SequencedRemoteModel(
            [
                ModelGatewayError(
                    "temporary",
                    code="MODEL_UPSTREAM_UNAVAILABLE",
                    retryable=True,
                ),
                ModelResponse("online answer"),
            ]
        )
        delays = []
        model = SwitchableModel(
            remote,
            environ={
                MODEL_RETRY_ATTEMPTS_ENV: "2",
                MODEL_RETRY_BACKOFF_ENV: "0.1",
            },
            sleeper=delays.append,
        )

        response = model.generate({"user_message": "hello"})

        self.assertEqual(response.content, "online answer")
        self.assertEqual(response.runtime["served_mode"], "remote")
        self.assertEqual(response.runtime["remote_attempts"], 2)
        self.assertEqual(response.runtime["retry_count"], 1)
        self.assertFalse(response.runtime["fallback_used"])
        self.assertEqual(delays, [0.1])
        summary = model.summary()["resilience"]
        self.assertEqual(summary["remote_successes"], 1)
        self.assertEqual(summary["retry_count"], 1)
        self.assertEqual(summary["circuit_state"], "CLOSED")

    def test_exhausted_remote_request_falls_back_offline(self):
        remote = SequencedRemoteModel(
            [
                ModelGatewayError(
                    "temporary",
                    code="MODEL_NETWORK_ERROR",
                    retryable=True,
                ),
                ModelGatewayError(
                    "temporary",
                    code="MODEL_NETWORK_ERROR",
                    retryable=True,
                ),
            ]
        )
        model = SwitchableModel(
            remote,
            environ={
                MODEL_RETRY_ATTEMPTS_ENV: "2",
                MODEL_RETRY_BACKOFF_ENV: "0",
            },
        )

        response = model.generate({"user_message": "hello"})

        self.assertTrue(response.runtime["fallback_used"])
        self.assertEqual(response.runtime["served_mode"], "offline")
        self.assertEqual(
            response.runtime["fallback_reason"],
            "MODEL_NETWORK_ERROR",
        )
        self.assertIn("在线模型暂不可用", response.content)
        summary = model.summary()["resilience"]
        self.assertEqual(summary["remote_failures"], 1)
        self.assertEqual(summary["fallback_count"], 1)

    def test_circuit_opens_and_skips_remote_until_cooldown(self):
        failure = ModelGatewayError(
            "temporary",
            code="MODEL_UPSTREAM_UNAVAILABLE",
            retryable=True,
        )
        remote = SequencedRemoteModel([failure, failure])
        now = [100.0]
        model = SwitchableModel(
            remote,
            environ={
                MODEL_RETRY_ATTEMPTS_ENV: "1",
                MODEL_CIRCUIT_THRESHOLD_ENV: "2",
                MODEL_CIRCUIT_COOLDOWN_ENV: "30",
            },
            clock=lambda: now[0],
        )

        model.generate({"user_message": "one"})
        model.generate({"user_message": "two"})
        skipped = model.generate({"user_message": "three"})

        self.assertEqual(remote.calls, 2)
        self.assertEqual(
            skipped.runtime["fallback_reason"],
            "MODEL_CIRCUIT_OPEN",
        )
        summary = model.summary()["resilience"]
        self.assertEqual(summary["circuit_state"], "OPEN")
        self.assertEqual(summary["fallback_count"], 3)

    def test_half_open_probe_closes_circuit_after_success(self):
        remote = SequencedRemoteModel(
            [
                ModelGatewayError(
                    "temporary",
                    code="MODEL_NETWORK_ERROR",
                    retryable=True,
                ),
                ModelResponse("recovered"),
            ]
        )
        now = [100.0]
        model = SwitchableModel(
            remote,
            environ={
                MODEL_RETRY_ATTEMPTS_ENV: "1",
                MODEL_CIRCUIT_THRESHOLD_ENV: "1",
                MODEL_CIRCUIT_COOLDOWN_ENV: "10",
            },
            clock=lambda: now[0],
        )

        model.generate({"user_message": "fail"})
        now[0] = 111.0
        response = model.generate({"user_message": "probe"})

        self.assertEqual(response.content, "recovered")
        self.assertEqual(response.runtime["served_mode"], "remote")
        self.assertEqual(
            model.summary()["resilience"]["circuit_state"],
            "CLOSED",
        )

    def test_nonretryable_failure_opens_without_retry(self):
        remote = SequencedRemoteModel(
            [
                ModelGatewayError(
                    "unauthorized",
                    code="MODEL_AUTHENTICATION_FAILED",
                    retryable=False,
                )
            ]
        )
        model = SwitchableModel(remote, environ={})

        response = model.generate({"user_message": "hello"})

        self.assertEqual(remote.calls, 1)
        self.assertEqual(response.runtime["remote_attempts"], 1)
        self.assertEqual(
            model.summary()["resilience"]["circuit_state"],
            "OPEN",
        )

    def test_can_fail_closed_when_offline_fallback_disabled(self):
        remote = SequencedRemoteModel(
            [
                ModelGatewayError(
                    "temporary",
                    code="MODEL_NETWORK_ERROR",
                    retryable=True,
                )
            ]
        )
        model = SwitchableModel(
            remote,
            environ={
                MODEL_RETRY_ATTEMPTS_ENV: "1",
                MODEL_OFFLINE_FALLBACK_ENV: "false",
            },
        )

        with self.assertRaises(ModelGatewayError):
            model.generate({"user_message": "hello"})

    def test_rejects_invalid_resilience_environment(self):
        with self.assertRaises(ModelConfigurationError):
            SwitchableModel(
                OfflineMockModel(),
                environ={MODEL_RETRY_ATTEMPTS_ENV: "9"},
            )
        with self.assertRaises(ModelConfigurationError):
            SwitchableModel(
                OfflineMockModel(),
                environ={MODEL_OFFLINE_FALLBACK_ENV: "sometimes"},
            )


if __name__ == "__main__":
    unittest.main()
