"""Perform one bounded DeepSeek tool-call compatibility request."""

import argparse
import json
import os
import sys

from packages.harness.default_tools import build_default_registry
from packages.harness.model_gateway import UrllibJsonTransport
from packages.harness.model_runtime import (
    build_model_from_environment,
    model_runtime_summary,
)
from packages.harness.utf8 import (
    print_json_utf8,
    write_json_atomic,
)


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)


class LiveRecordingTransport(object):
    """Record only non-secret response metadata around the real transport."""

    def __init__(self):
        self.delegate = UrllibJsonTransport()
        self.network_used = False
        self.usage = {}

    def post_json(
        self,
        url,
        headers,
        payload,
        timeout_seconds,
    ):
        self.network_used = True
        response = self.delegate.post_json(
            url,
            headers,
            payload,
            timeout_seconds,
        )
        usage = response.get("usage") or {}
        self.usage = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get(
                "completion_tokens"
            ),
            "total_tokens": usage.get("total_tokens"),
        }
        return response


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Make one bounded real DeepSeek tool-call request."
        )
    )
    parser.add_argument("--output", default="")
    return parser


def main():
    args = build_parser().parse_args()
    secret = os.environ.get(
        "EDGESENTINEL_MODEL_API_KEY",
        "",
    )
    transport = LiveRecordingTransport()
    tool_choice = {
        "type": "function",
        "function": {"name": "event.query"},
    }
    model = build_model_from_environment(
        transport=transport,
        tool_choice=tool_choice,
    )
    registry = build_default_registry(
        PROJECT_DIR,
        os.path.join(
            PROJECT_DIR,
            "data",
            "events",
            "edgesentinel.db",
        ),
    )
    response = model.generate(
        {
            "schema_version": "1.0",
            "user_message": (
                "请调用 event.query 查询最近2条 bottle 事件。"
            ),
            "permissions": {
                "mode": "default_deny",
                "arbitrary_shell": False,
            },
        },
        tool_schemas=registry.schemas(),
    )
    result = {
        "schema_version": "1.0",
        "runtime": model_runtime_summary(model),
        "network_used": transport.network_used,
        "request_limits": {
            "timeout_seconds": model.timeout_seconds,
            "max_tokens": model.max_tokens,
            "forced_tool": "event.query",
        },
        "response": response.to_dict(),
        "usage": transport.usage,
    }
    result["api_key_exposed"] = bool(
        secret
        and secret in json.dumps(result, ensure_ascii=False)
    )
    if args.output:
        write_json_atomic(args.output, result)
    print_json_utf8(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
