"""Verify model runtime selection without making a network request."""

import argparse
import json
import os
import sys

from packages.harness.model_runtime import (
    MODEL_API_KEY_ENV,
    MODEL_ENDPOINT_ENV,
    MODEL_MODE_ENV,
    MODEL_PROVIDER_ENV,
    MODEL_NAME_ENV,
    MODEL_TIMEOUT_ENV,
    MODEL_MAX_TOKENS_ENV,
    ModelConfigurationError,
    build_model_from_environment,
    model_runtime_summary,
)
from packages.harness.utf8 import (
    print_json_utf8,
    write_json_atomic,
)


class NoNetworkTransport(object):
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
                        "content": "configuration probe"
                    }
                }
            ]
        }


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Verify offline and remote model configuration "
            "without network access."
        )
    )
    parser.add_argument("--output", default="")
    return parser


def main():
    args = build_parser().parse_args()
    secret = "runtime-probe-secret"
    offline_model = build_model_from_environment({})
    transport = NoNetworkTransport()
    remote_model = build_model_from_environment(
        {
            MODEL_MODE_ENV: "remote",
            MODEL_PROVIDER_ENV: "custom",
            MODEL_ENDPOINT_ENV: (
                "https://offline.invalid/v1/chat/completions"
            ),
            MODEL_NAME_ENV: "configuration-probe",
            MODEL_API_KEY_ENV: secret,
            MODEL_TIMEOUT_ENV: "7",
            MODEL_MAX_TOKENS_ENV: "128",
        },
        transport=transport,
    )
    remote_model.generate(
        {
            "schema_version": "1.0",
            "user_message": "configuration probe",
        },
        tool_schemas=[],
    )

    missing_key_rejected = False
    try:
        build_model_from_environment(
            {
                MODEL_MODE_ENV: "remote",
                MODEL_PROVIDER_ENV: "custom",
                MODEL_ENDPOINT_ENV: (
                    "https://offline.invalid/v1/chat/completions"
                ),
                MODEL_NAME_ENV: "configuration-probe",
            },
            transport=transport,
        )
    except ModelConfigurationError:
        missing_key_rejected = True

    remote_summary = model_runtime_summary(remote_model)
    result = {
        "schema_version": "1.0",
        "default": model_runtime_summary(offline_model),
        "configured": remote_summary,
        "network_used": False,
        "injected_transport_calls": len(transport.calls),
        "authorization_header_present": bool(
            transport.calls[0]["headers"].get("Authorization")
        ),
        "missing_key_rejected": missing_key_rejected,
        "environment_variables": [
            MODEL_MODE_ENV,
            MODEL_PROVIDER_ENV,
            MODEL_ENDPOINT_ENV,
            MODEL_NAME_ENV,
            MODEL_API_KEY_ENV,
            MODEL_TIMEOUT_ENV,
            MODEL_MAX_TOKENS_ENV,
        ],
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
