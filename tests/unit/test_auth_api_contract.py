import os
import unittest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


class AuthApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(
            os.path.join(PROJECT_DIR, "apps", "api_server.py"),
            "r",
            encoding="utf-8",
        ) as source_file:
            cls.source = source_file.read()

    def test_health_and_dashboard_assets_remain_public(self):
        self.assertIn('path == "/health"', self.source)
        self.assertIn('"/health/"', self.source)
        self.assertIn('"/health/vision"', self.source)
        self.assertIn('"scene_content_exposed": False', self.source)
        self.assertIn('path == "/dashboard"', self.source)
        self.assertIn(
            'path.startswith("/dashboard/assets/")', self.source
        )
        self.assertIn(
            'payload["authentication"] = auth_service.summary()',
            self.source,
        )

    def test_protected_api_requires_session_and_csrf(self):
        self.assertIn("request.cookies.get(AUTH_COOKIE_NAME)", self.source)
        self.assertIn('"X-EdgeSentinel-CSRF"', self.source)
        self.assertIn('request.method.upper() not in (', self.source)
        self.assertIn('"AUTH_REQUIRED"', self.source)

    def test_confirmation_role_depends_on_risk_and_is_audited(self):
        self.assertIn(
            '"operator" if risk in ("L0", "L1") else "admin"',
            self.source,
        )
        self.assertIn('result["confirmed_by"]', self.source)
        self.assertIn('terminal_checkpoint["confirmed_by"]', self.source)
        self.assertIn("auth_service.audit_authorized", self.source)

    def test_admin_only_control_plane_routes_are_explicit(self):
        self.assertIn('"/api/v1/zones"', self.source)
        self.assertIn('"/api/v1/agent/model-mode"', self.source)
        self.assertIn('"admin", action=path', self.source)

    def test_external_plaintext_is_redirected_or_rejected(self):
        self.assertIn('"TLS_REQUIRED"', self.source)
        self.assertIn("status_code=426", self.source)
        self.assertIn("RedirectResponse(destination, status_code=307)", self.source)
        self.assertIn("TLS requires Secure authentication cookies", self.source)
        self.assertIn('"private_key_exposed": False', self.source)


if __name__ == "__main__":
    unittest.main()
