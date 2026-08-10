import json
import unittest

from packages.api.auth_service import (
    AUTH_ADMIN_PASSWORD_HASH_ENV,
    AUTH_ADMIN_USERNAME_ENV,
    AUTH_ENABLED_ENV,
    AUTH_SESSION_SECRET_ENV,
    AuthConfigurationError,
    AuthenticationError,
    AuthService,
    hash_password,
    verify_password,
)


class MemoryAudit(object):
    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(dict(record))


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = [1000000000.0]
        self.audit = MemoryAudit()
        self.password = "correct horse battery staple"
        self.encoded = hash_password(
            self.password,
            salt=b"1" * 16,
        )
        self.service = AuthService(
            enabled=True,
            session_secret="a" * 64,
            users={
                "admin": {
                    "role": "admin",
                    "password_hash": self.encoded,
                },
                "operator": {
                    "role": "operator",
                    "password_hash": self.encoded,
                },
                "viewer": {
                    "role": "viewer",
                    "password_hash": self.encoded,
                },
            },
            session_ttl_seconds=600,
            audit_recorder=self.audit,
            clock=lambda: self.now[0],
        )

    def test_hashes_and_verifies_password_without_plaintext(self):
        self.assertTrue(verify_password(self.password, self.encoded))
        self.assertFalse(verify_password("wrong", self.encoded))
        self.assertNotIn(self.password, self.encoded)

    def test_login_authenticate_csrf_and_logout(self):
        token, session = self.service.login(
            "admin", self.password, client_id="client"
        )

        self.assertTrue(session["authenticated"])
        self.assertEqual(session["role"], "admin")
        self.assertNotIn(self.password, json.dumps(session))
        principal = self.service.authenticate(token)
        self.service.verify_csrf(
            principal, session["csrf_token"]
        )
        self.service.require_role(principal, "admin")
        self.assertTrue(self.service.logout(token, principal))
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(token)

    def test_rejects_tampered_and_expired_sessions(self):
        token, session = self.service.login("admin", self.password)
        replacement = "0" if token[-1] != "0" else "1"
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(token[:-1] + replacement)
        self.now[0] = session["expires_at"] + 1
        with self.assertRaises(AuthenticationError) as expired:
            self.service.authenticate(token)
        self.assertEqual(
            expired.exception.code, "AUTH_SESSION_EXPIRED"
        )

    def test_enforces_role_hierarchy(self):
        viewer_token, _ = self.service.login(
            "viewer", self.password
        )
        operator_token, _ = self.service.login(
            "operator", self.password
        )
        viewer = self.service.authenticate(viewer_token)
        operator = self.service.authenticate(operator_token)

        self.service.require_role(viewer, "viewer")
        with self.assertRaises(AuthenticationError):
            self.service.require_role(viewer, "operator")
        self.service.require_role(operator, "operator")
        with self.assertRaises(AuthenticationError):
            self.service.require_role(operator, "admin")

    def test_requires_matching_csrf_for_mutation(self):
        token, _ = self.service.login("admin", self.password)
        principal = self.service.authenticate(token)
        with self.assertRaises(AuthenticationError) as raised:
            self.service.verify_csrf(principal, "wrong")
        self.assertEqual(raised.exception.code, "AUTH_CSRF_INVALID")

    def test_rate_limits_repeated_login_failures(self):
        for unused in range(5):
            with self.assertRaises(AuthenticationError):
                self.service.login(
                    "admin", "wrong", client_id="same-client"
                )
        with self.assertRaises(AuthenticationError) as limited:
            self.service.login(
                "admin", self.password, client_id="same-client"
            )
        self.assertEqual(limited.exception.status_code, 429)
        self.now[0] += 301
        token, unused_session = self.service.login(
            "admin", self.password, client_id="same-client"
        )
        self.assertTrue(token)

    def test_environment_summary_never_exposes_credentials(self):
        service = AuthService.from_environment(
            {
                AUTH_ENABLED_ENV: "1",
                AUTH_SESSION_SECRET_ENV: "b" * 64,
                AUTH_ADMIN_USERNAME_ENV: "admin",
                AUTH_ADMIN_PASSWORD_HASH_ENV: self.encoded,
            }
        )
        summary = service.summary()

        self.assertTrue(summary["enabled"])
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["configured_roles"], ["admin"])
        text = json.dumps(summary)
        self.assertNotIn(self.encoded, text)
        self.assertNotIn("b" * 64, text)

    def test_enabled_without_credentials_is_fail_closed(self):
        service = AuthService.from_environment(
            {AUTH_ENABLED_ENV: "1"}
        )
        self.assertFalse(service.ready)
        with self.assertRaises(AuthenticationError) as raised:
            service.authenticate(None)
        self.assertEqual(raised.exception.status_code, 503)

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(AuthConfigurationError):
            hash_password("short")
        with self.assertRaises(AuthConfigurationError):
            AuthService(
                enabled=True,
                session_secret="a" * 64,
                users={
                    "bad user": {
                        "role": "admin",
                        "password_hash": self.encoded,
                    }
                },
            )

    def test_audit_contains_no_password_or_session_token(self):
        token, unused = self.service.login("admin", self.password)
        self.service.audit_authorized(
            self.service.authenticate(token),
            "camera.restart",
        )
        text = json.dumps(self.audit.records)

        self.assertNotIn(self.password, text)
        self.assertNotIn(token, text)
        self.assertIn("AUTHORIZATION_ALLOWED", text)


if __name__ == "__main__":
    unittest.main()
