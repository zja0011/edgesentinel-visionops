import unittest

from packages.api.agent_service import (
    AGENT_CONFIRMATION_PHRASE,
    AgentRequestInvalid,
    add_agent_runtime_health,
    validate_agent_cancellation,
    validate_agent_confirmation,
    validate_agent_request,
    validate_agent_task_request,
    validate_model_mode_request,
    validate_session_clear,
)


class AgentRequestValidationTests(unittest.TestCase):
    def test_model_mode_requires_explicit_confirmation(self):
        with self.assertRaises(AgentRequestInvalid):
            validate_model_mode_request({"mode": "online"})
        with self.assertRaises(AgentRequestInvalid):
            validate_model_mode_request(
                {
                    "mode": "online",
                    "confirmation": "yes",
                }
            )

        self.assertEqual(
            validate_model_mode_request(
                {
                    "mode": "online",
                    "confirmation": "SWITCH_AGENT_MODEL",
                }
            ),
            "remote",
        )
        self.assertEqual(
            validate_model_mode_request(
                {
                    "mode": "offline",
                    "confirmation": "SWITCH_AGENT_MODEL",
                }
            ),
            "offline",
        )

    def test_health_metadata_uses_strict_allowlist(self):
        health = add_agent_runtime_health(
            {"status": "ok", "database": {"status": "ok"}},
            {
                "mode": "remote",
                "provider": "deepseek",
                "gateway": "chat-completions-compatible",
                "model": "deepseek-v4-flash",
                "external_requests_enabled": True,
                "credential_source": "environment",
                "api_key": "must-not-leak",
            },
        )

        self.assertEqual(health["status"], "ok")
        self.assertEqual(
            health["agent_model"]["provider"],
            "deepseek",
        )
        self.assertNotIn("api_key", health["agent_model"])
        self.assertNotIn("must-not-leak", str(health))

    def test_accepts_and_strips_message(self):
        self.assertEqual(
            validate_agent_request({"message": "  当前有几个人？  "}),
            "当前有几个人？",
        )

    def test_accepts_optional_bounded_session_id(self):
        session_id = "sess_" + ("a" * 32)

        request = validate_agent_task_request(
            {
                "message": "  What did I mention?  ",
                "session_id": session_id,
            }
        )

        self.assertEqual(request["message"], "What did I mention?")
        self.assertEqual(request["session_id"], session_id)
        self.assertIsNone(
            validate_agent_task_request(
                {"message": "New conversation"}
            )["session_id"]
        )

    def test_rejects_invalid_session_id(self):
        for session_id in ("session", "../session", "sess_bad"):
            with self.subTest(session_id=session_id):
                with self.assertRaises(AgentRequestInvalid):
                    validate_agent_task_request(
                        {
                            "message": "Question",
                            "session_id": session_id,
                        }
                    )

    def test_session_clear_requires_exact_confirmation(self):
        self.assertTrue(
            validate_session_clear(
                {"confirmation": "CLEAR_AGENT_SESSION"}
            )
        )
        with self.assertRaises(AgentRequestInvalid):
            validate_session_clear({"confirmation": "yes"})

    def test_rejects_missing_empty_and_non_string_message(self):
        for payload in (
            {},
            {"message": "   "},
            {"message": 123},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(AgentRequestInvalid):
                    validate_agent_request(payload)

    def test_rejects_unknown_fields(self):
        with self.assertRaises(AgentRequestInvalid):
            validate_agent_request(
                {
                    "message": "查询",
                    "max_steps": 100,
                }
            )

    def test_rejects_oversized_message(self):
        with self.assertRaises(AgentRequestInvalid):
            validate_agent_request(
                {"message": "x" * 1001}
            )

    def test_accepts_explicit_confirmation_and_cancellation(self):
        self.assertTrue(
            validate_agent_confirmation(
                {
                    "confirmation": (
                        AGENT_CONFIRMATION_PHRASE
                    )
                }
            )
        )
        self.assertTrue(
            validate_agent_cancellation({"cancel": True})
        )

    def test_rejects_implicit_or_malformed_task_actions(self):
        invalid_confirmations = (
            {},
            {"confirmation": "yes"},
            {"confirmation": AGENT_CONFIRMATION_PHRASE, "x": 1},
        )
        invalid_cancellations = (
            {},
            {"cancel": False},
            {"cancel": True, "x": 1},
        )
        for payload in invalid_confirmations:
            with self.subTest(confirmation=payload):
                with self.assertRaises(AgentRequestInvalid):
                    validate_agent_confirmation(payload)
        for payload in invalid_cancellations:
            with self.subTest(cancellation=payload):
                with self.assertRaises(AgentRequestInvalid):
                    validate_agent_cancellation(payload)


if __name__ == "__main__":
    unittest.main()
