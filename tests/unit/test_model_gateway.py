import json
import urllib.error
import unittest
from unittest import mock

from packages.harness.model_gateway import (
    ChatCompletionsModelGateway,
    ModelGatewayError,
    UrllibJsonTransport,
)


TOOLS = [
    {
        "name": "event.query",
        "description": "query events",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    }
]


class FakeTransport(object):
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(
        self,
        url,
        headers,
        payload,
        timeout_seconds,
    ):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


class ChatCompletionsModelGatewayTests(unittest.TestCase):
    def test_transport_classifies_retryable_http_failures(self):
        for status, code, retryable in (
            (401, "MODEL_AUTHENTICATION_FAILED", False),
            (429, "MODEL_RATE_LIMITED", True),
            (503, "MODEL_UPSTREAM_UNAVAILABLE", True),
        ):
            error = urllib.error.HTTPError(
                "https://example.invalid",
                status,
                "error",
                None,
                None,
            )
            with self.subTest(status=status):
                with mock.patch(
                    "urllib.request.urlopen",
                    side_effect=error,
                ):
                    with self.assertRaises(ModelGatewayError) as raised:
                        UrllibJsonTransport().post_json(
                            "https://example.invalid",
                            {},
                            {},
                            1,
                        )
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(
                    raised.exception.retryable, retryable
                )
                self.assertEqual(
                    raised.exception.status_code, status
                )

    def test_transport_classifies_network_failure_as_retryable(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            with self.assertRaises(ModelGatewayError) as raised:
                UrllibJsonTransport().post_json(
                    "https://example.invalid", {}, {}, 1
                )

        self.assertEqual(
            raised.exception.code, "MODEL_NETWORK_ERROR"
        )
        self.assertTrue(raised.exception.retryable)

    def test_builds_utf8_context_and_parses_tool_call(self):
        transport = FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "event_query",
                                        "arguments": (
                                            '{"object_class":'
                                            '"bottle","limit":2}'
                                        ),
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        )
        gateway = ChatCompletionsModelGateway(
            endpoint="https://example.invalid/v1/chat/completions",
            model="offline-demo",
            api_key="top-secret-key",
            transport=transport,
            max_tokens=256,
        )

        response = gateway.generate(
            {"user_message": "最近的瓶子事件"},
            tool_schemas=TOOLS,
        )

        self.assertEqual(
            response.tool_calls[0].name,
            "event.query",
        )
        self.assertEqual(
            response.tool_calls[0].arguments,
            {"object_class": "bottle", "limit": 2},
        )
        call = transport.calls[0]
        self.assertEqual(
            call["payload"]["model"],
            "offline-demo",
        )
        self.assertEqual(call["payload"]["max_tokens"], 256)
        self.assertIn(
            "最近的瓶子事件",
            call["payload"]["messages"][1]["content"],
        )
        self.assertEqual(
            call["payload"]["tools"][0]["function"]["parameters"],
            TOOLS[0]["inputSchema"],
        )
        self.assertEqual(
            call["payload"]["tools"][0]["function"]["name"],
            "event_query",
        )
        self.assertEqual(
            call["headers"]["Authorization"],
            "Bearer top-secret-key",
        )
        self.assertNotIn(
            "top-secret-key",
            json.dumps(call["payload"]),
        )

    def test_parses_plain_text_answer(self):
        gateway = ChatCompletionsModelGateway(
            endpoint="https://example.invalid/v1/chat/completions",
            model="offline-demo",
            api_key="secret",
            transport=FakeTransport(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "当前没有新事件。"
                            }
                        }
                    ]
                }
            ),
        )

        response = gateway.generate(
            {"user_message": "查询"},
            tool_schemas=TOOLS,
        )

        self.assertEqual(response.content, "当前没有新事件。")
        self.assertEqual(response.tool_calls, [])

    def test_can_force_one_named_routed_tool_for_one_call(self):
        transport = FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "event_query",
                                        "arguments": '{"limit":5}',
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        )
        gateway = ChatCompletionsModelGateway(
            endpoint="https://example.invalid/v1/chat/completions",
            model="offline-demo",
            api_key="secret",
            transport=transport,
        )

        gateway.generate_with_tool_choice(
            {"user_message": "查询最近事件"},
            tool_schemas=TOOLS,
            tool_choice={
                "type": "function",
                "function": {"name": "event.query"},
            },
        )

        self.assertEqual(
            transport.calls[0]["payload"]["tool_choice"],
            {
                "type": "function",
                "function": {"name": "event_query"},
            },
        )

    def test_parses_bounded_provider_usage(self):
        gateway = ChatCompletionsModelGateway(
            endpoint="https://example.invalid/v1/chat/completions",
            model="offline-demo",
            api_key="secret",
            transport=FakeTransport(
                {
                    "choices": [
                        {"message": {"content": "ok"}}
                    ],
                    "usage": {
                        "prompt_tokens": 80,
                        "completion_tokens": 5,
                        "total_tokens": 85,
                        "ignored_provider_field": 999,
                    },
                }
            ),
        )
        response = gateway.generate(
            {"user_message": "query"}, tool_schemas=[]
        )
        self.assertEqual(
            response.usage,
            {
                "prompt_tokens": 80,
                "completion_tokens": 5,
                "total_tokens": 85,
            },
        )
        self.assertEqual(response.to_dict()["usage"], response.usage)

    def test_omits_tool_fields_when_route_selects_no_tools(self):
        transport = FakeTransport(
            {
                "choices": [
                    {"message": {"content": "Wednesday"}}
                ],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 2,
                    "total_tokens": 52,
                },
            }
        )
        gateway = ChatCompletionsModelGateway(
            endpoint="https://example.invalid/v1/chat/completions",
            model="offline-demo",
            api_key="secret",
            transport=transport,
        )
        gateway.generate(
            {"user_message": "What weekday is it?"},
            tool_schemas=[],
        )
        payload = transport.calls[0]["payload"]
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)
        system_message = payload["messages"][0]["content"]
        self.assertIn(
            "online remote model gateway",
            system_message,
        )
        self.assertIn(
            "it never means that the model is offline",
            system_message,
        )
        self.assertIn(
            "Never infer model runtime mode from tool availability",
            system_message,
        )

    def test_rejects_invalid_provider_usage(self):
        invalid_usages = (
            "invalid",
            {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 1,
            },
            {
                "prompt_tokens": True,
                "completion_tokens": 2,
                "total_tokens": 3,
            },
        )
        for usage in invalid_usages:
            with self.subTest(usage=usage):
                gateway = ChatCompletionsModelGateway(
                    endpoint=(
                        "https://example.invalid/v1/chat/completions"
                    ),
                    model="offline-demo",
                    api_key="secret",
                    transport=FakeTransport(
                        {
                            "choices": [
                                {"message": {"content": "ok"}}
                            ],
                            "usage": usage,
                        }
                    ),
                )
                with self.assertRaises(ModelGatewayError):
                    gateway.generate(
                        {"user_message": "query"},
                        tool_schemas=[],
                    )

    def test_rejects_insecure_endpoint(self):
        with self.assertRaises(ValueError):
            ChatCompletionsModelGateway(
                endpoint="http://example.invalid/v1/chat/completions",
                model="demo",
                api_key="secret",
            )

    def test_rejects_endpoint_credentials_and_fragment(self):
        for endpoint in (
            (
                "https://user:password@example.invalid/"
                "v1/chat/completions"
            ),
            (
                "https://example.invalid/v1/chat/completions"
                "#unsafe"
            ),
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    ChatCompletionsModelGateway(
                        endpoint=endpoint,
                        model="demo",
                        api_key="secret",
                    )

    def test_rejects_invalid_output_limit_and_tool_choice(self):
        for max_tokens in (0, 5000):
            with self.subTest(max_tokens=max_tokens):
                with self.assertRaises(ValueError):
                    ChatCompletionsModelGateway(
                        endpoint=(
                            "https://example.invalid/"
                            "v1/chat/completions"
                        ),
                        model="demo",
                        api_key="secret",
                        max_tokens=max_tokens,
                    )
        with self.assertRaises(ValueError):
            ChatCompletionsModelGateway(
                endpoint=(
                    "https://example.invalid/v1/chat/completions"
                ),
                model="demo",
                api_key="secret",
                tool_choice="invalid",
            )

    def test_converts_named_tool_choice_and_deepseek_mode(self):
        transport = FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "event_query",
                                        "arguments": '{"limit":2}',
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )
        gateway = ChatCompletionsModelGateway(
            endpoint=(
                "https://api.deepseek.com/chat/completions"
            ),
            model="deepseek-v4-flash",
            api_key="secret",
            provider="deepseek",
            tool_choice={
                "type": "function",
                "function": {"name": "event.query"},
            },
            transport=transport,
        )

        response = gateway.generate(
            {"user_message": "query"},
            tool_schemas=TOOLS,
        )

        payload = transport.calls[0]["payload"]
        self.assertEqual(
            payload["tool_choice"]["function"]["name"],
            "event_query",
        )
        self.assertEqual(
            payload["thinking"],
            {"type": "disabled"},
        )
        self.assertEqual(
            response.tool_calls[0].name,
            "event.query",
        )

    def test_replays_assistant_and_bounded_tool_messages(self):
        transport = FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": "根据工具结果回答。"
                        }
                    }
                ]
            }
        )
        gateway = ChatCompletionsModelGateway(
            endpoint=(
                "https://api.deepseek.com/chat/completions"
            ),
            model="deepseek-v4-flash",
            api_key="secret",
            provider="deepseek",
            transport=transport,
        )
        conversation = [
            {
                "role": "user",
                "context": {"user_message": "查询瓶子"},
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "call_id": "provider_call_one",
                        "name": "event.query",
                        "arguments": {
                            "object_class": "bottle",
                            "limit": 2,
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "provider_call_one",
                "name": "event.query",
                "content": {
                    "tool_name": "event.query",
                    "status": "SUCCEEDED",
                    "result": {"count": 2},
                },
            },
        ]

        response = gateway.generate(
            {"user_message": "unused current context"},
            tool_schemas=TOOLS,
            conversation=conversation,
        )

        messages = transport.calls[0]["payload"]["messages"]
        self.assertEqual(
            [message["role"] for message in messages],
            ["system", "user", "assistant", "tool"],
        )
        self.assertEqual(
            messages[2]["tool_calls"][0]["function"]["name"],
            "event_query",
        )
        self.assertEqual(
            messages[2]["tool_calls"][0]["id"],
            messages[3]["tool_call_id"],
        )
        self.assertIn(
            '"count":2',
            messages[3]["content"],
        )
        self.assertEqual(
            response.content,
            "根据工具结果回答。",
        )

    def test_rejects_invalid_tool_arguments(self):
        gateway = ChatCompletionsModelGateway(
            endpoint="https://example.invalid/v1/chat/completions",
            model="offline-demo",
            api_key="secret",
            transport=FakeTransport(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "event.query",
                                            "arguments": "not-json",
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ),
        )

        with self.assertRaises(ModelGatewayError):
            gateway.generate(
                {"user_message": "查询"},
                tool_schemas=TOOLS,
            )

    def test_rejects_missing_message(self):
        gateway = ChatCompletionsModelGateway(
            endpoint="https://example.invalid/v1/chat/completions",
            model="offline-demo",
            api_key="secret",
            transport=FakeTransport({"choices": []}),
        )

        with self.assertRaises(ModelGatewayError):
            gateway.generate(
                {"user_message": "查询"},
                tool_schemas=TOOLS,
            )


if __name__ == "__main__":
    unittest.main()
