"""Validation boundary for Agent HTTP requests."""

import re


AGENT_HEALTH_FIELDS = (
    "mode",
    "provider",
    "gateway",
    "model",
    "external_requests_enabled",
    "credential_source",
    "available_modes",
    "boot_mode",
    "runtime_switchable",
    "resilience",
)
AGENT_CONFIRMATION_PHRASE = "CONFIRM_TOOL_EXECUTION"
MODEL_MODE_CONFIRMATION_PHRASE = "SWITCH_AGENT_MODEL"
SESSION_CLEAR_CONFIRMATION_PHRASE = "CLEAR_AGENT_SESSION"
SESSION_ID_PATTERN = re.compile(r"^sess_[0-9a-f]{32}$")


class AgentRequestInvalid(ValueError):
    pass


def add_agent_runtime_health(payload, runtime_summary):
    """Add allowlisted model metadata without exposing credentials."""
    result = dict(payload)
    result["agent_model"] = {
        field: runtime_summary.get(field)
        for field in AGENT_HEALTH_FIELDS
    }
    return result


def validate_agent_request(payload):
    if not isinstance(payload, dict):
        raise AgentRequestInvalid(
            "request body must be a JSON object"
        )
    unknown = sorted(set(payload) - {"message"})
    if unknown:
        raise AgentRequestInvalid(
            "unknown fields: {0}".format(", ".join(unknown))
        )
    return _validate_message(payload)


def validate_agent_task_request(payload):
    if not isinstance(payload, dict):
        raise AgentRequestInvalid(
            "request body must be a JSON object"
        )
    unknown = sorted(set(payload) - {"message", "session_id"})
    if unknown:
        raise AgentRequestInvalid(
            "unknown fields: {0}".format(", ".join(unknown))
        )
    message = _validate_message(payload)
    session_id = payload.get("session_id")
    if session_id is not None:
        if (
            not isinstance(session_id, str)
            or not SESSION_ID_PATTERN.match(session_id)
        ):
            raise AgentRequestInvalid("session_id is invalid")
    return {
        "message": message,
        "session_id": session_id,
    }


def validate_session_clear(payload):
    if not isinstance(payload, dict):
        raise AgentRequestInvalid(
            "request body must be a JSON object"
        )
    unknown = sorted(set(payload) - {"confirmation"})
    if unknown:
        raise AgentRequestInvalid(
            "unknown fields: {0}".format(", ".join(unknown))
        )
    if (
        payload.get("confirmation")
        != SESSION_CLEAR_CONFIRMATION_PHRASE
    ):
        raise AgentRequestInvalid(
            "session clear confirmation phrase does not match"
        )
    return True


def _validate_message(payload):
    if "message" not in payload:
        raise AgentRequestInvalid("message is required")
    message = payload["message"]
    if not isinstance(message, str):
        raise AgentRequestInvalid("message must be a string")
    message = message.strip()
    if not message:
        raise AgentRequestInvalid("message must not be empty")
    if len(message) > 1000:
        raise AgentRequestInvalid(
            "message must not exceed 1000 characters"
        )
    return message


def validate_agent_confirmation(payload):
    if not isinstance(payload, dict):
        raise AgentRequestInvalid(
            "request body must be a JSON object"
        )
    unknown = sorted(set(payload) - {"confirmation"})
    if unknown:
        raise AgentRequestInvalid(
            "unknown fields: {0}".format(", ".join(unknown))
        )
    if payload.get("confirmation") != AGENT_CONFIRMATION_PHRASE:
        raise AgentRequestInvalid(
            "confirmation phrase does not match"
        )
    return True


def validate_agent_cancellation(payload):
    if not isinstance(payload, dict):
        raise AgentRequestInvalid(
            "request body must be a JSON object"
        )
    unknown = sorted(set(payload) - {"cancel"})
    if unknown:
        raise AgentRequestInvalid(
            "unknown fields: {0}".format(", ".join(unknown))
        )
    if payload.get("cancel") is not True:
        raise AgentRequestInvalid("cancel must be true")
    return True


def validate_model_mode_request(payload):
    if not isinstance(payload, dict):
        raise AgentRequestInvalid(
            "request body must be a JSON object"
        )
    unknown = sorted(set(payload) - {"mode", "confirmation"})
    if unknown:
        raise AgentRequestInvalid(
            "unknown fields: {0}".format(", ".join(unknown))
        )
    mode = str(payload.get("mode") or "").strip().lower()
    if mode not in ("online", "offline", "remote"):
        raise AgentRequestInvalid(
            "mode must be online or offline"
        )
    if payload.get("confirmation") != MODEL_MODE_CONFIRMATION_PHRASE:
        raise AgentRequestInvalid(
            "model mode confirmation phrase does not match"
        )
    return "remote" if mode in ("online", "remote") else "offline"
