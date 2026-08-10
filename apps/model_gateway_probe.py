"""Offline contract probe for the cloud model gateway boundary."""

import argparse
import json
import os
import sys

from packages.harness.default_tools import build_default_registry
from packages.harness.model_gateway import (
    ChatCompletionsModelGateway,
)
from packages.harness.utf8 import (
    print_json_utf8,
    write_json_atomic,
)


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)


class OfflineRecordingTransport(object):
    def __init__(self):
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
                "headers": dict(headers),
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
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


def build_parser():
    parser = argparse.ArgumentParser(
        description="Probe the model gateway without network access."
    )
    parser.add_argument("--output", default="")
    return parser


def main():
    args = build_parser().parse_args()
    secret = "offline-probe-secret"
    transport = OfflineRecordingTransport()
    registry = build_default_registry(
        PROJECT_DIR,
        os.path.join(
            PROJECT_DIR,
            "data",
            "events",
            "edgesentinel.db",
        ),
    )
    gateway = ChatCompletionsModelGateway(
        endpoint=(
            "https://offline.invalid/v1/chat/completions"
        ),
        model="offline-demo",
        api_key=secret,
        transport=transport,
    )
    response = gateway.generate(
        {
            "schema_version": "1.0",
            "user_message": "最近是否有人拿走瓶子？",
            "permissions": {
                "mode": "default_deny",
                "arbitrary_shell": False,
            },
        },
        tool_schemas=registry.schemas(),
    )
    request = transport.calls[0]
    result = {
        "schema_version": "1.0",
        "gateway": gateway.name,
        "network_used": False,
        "request": {
            "https": request["url"].startswith("https://"),
            "model": request["payload"]["model"],
            "tools_sent": len(request["payload"]["tools"]),
            "authorization_header_present": bool(
                request["headers"].get("Authorization")
            ),
        },
        "parsed_response": {
            "content": response.content,
            "tool_calls": [
                tool_call.to_dict()
                for tool_call in response.tool_calls
            ],
        },
    }
    result["api_key_exposed"] = secret in json.dumps(
        result,
        ensure_ascii=False,
    )
    if args.output:
        write_json_atomic(args.output, result)
    print_json_utf8(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
