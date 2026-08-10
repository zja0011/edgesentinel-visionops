"""Bounded local authentication, RBAC sessions, and audit metadata."""

import hashlib
import hmac
import re
import secrets
import threading
import time

from packages.vision.schemas import beijing_timestamp


AUTH_ENABLED_ENV = "EDGESENTINEL_AUTH_ENABLED"
AUTH_SESSION_SECRET_ENV = "EDGESENTINEL_AUTH_SESSION_SECRET"
AUTH_SESSION_TTL_ENV = "EDGESENTINEL_AUTH_SESSION_TTL_SECONDS"
AUTH_COOKIE_SECURE_ENV = "EDGESENTINEL_AUTH_COOKIE_SECURE"
AUTH_ADMIN_USERNAME_ENV = "EDGESENTINEL_AUTH_ADMIN_USERNAME"
AUTH_ADMIN_PASSWORD_HASH_ENV = (
    "EDGESENTINEL_AUTH_ADMIN_PASSWORD_HASH"
)
AUTH_OPERATOR_USERNAME_ENV = "EDGESENTINEL_AUTH_OPERATOR_USERNAME"
AUTH_OPERATOR_PASSWORD_HASH_ENV = (
    "EDGESENTINEL_AUTH_OPERATOR_PASSWORD_HASH"
)
AUTH_VIEWER_USERNAME_ENV = "EDGESENTINEL_AUTH_VIEWER_USERNAME"
AUTH_VIEWER_PASSWORD_HASH_ENV = (
    "EDGESENTINEL_AUTH_VIEWER_PASSWORD_HASH"
)

AUTH_COOKIE_NAME = "edgesentinel_session"
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 200000
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,31}$")
HASH_PATTERN = re.compile(
    r"^pbkdf2_sha256\$([0-9]{5,7})\$([0-9a-f]{32})\$([0-9a-f]{64})$"
)
SESSION_TOKEN_PATTERN = re.compile(
    r"^([0-9a-f]{48})\.([0-9]{10})\.([0-9a-f]{64})$"
)
ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


class AuthConfigurationError(ValueError):
    pass


class AuthenticationError(RuntimeError):
    def __init__(self, code, message, status_code=401):
        RuntimeError.__init__(self, str(message))
        self.code = str(code)
        self.status_code = int(status_code)


def hash_password(password, salt=None, iterations=PASSWORD_ITERATIONS):
    password = str(password or "")
    if len(password) < 12 or len(password) > 256:
        raise AuthConfigurationError(
            "password must contain between 12 and 256 characters"
        )
    iterations = int(iterations)
    if iterations < 100000 or iterations > 1000000:
        raise AuthConfigurationError(
            "password iterations are outside the safe bound"
        )
    salt_bytes = salt or secrets.token_bytes(16)
    if not isinstance(salt_bytes, bytes) or len(salt_bytes) != 16:
        raise AuthConfigurationError("password salt is invalid")
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        iterations,
    )
    return "{0}${1}${2}${3}".format(
        PASSWORD_SCHEME,
        iterations,
        salt_bytes.hex(),
        digest.hex(),
    )


def verify_password(password, encoded):
    match = HASH_PATTERN.match(str(encoded or ""))
    if match is None:
        return False
    iterations = int(match.group(1))
    if iterations < 100000 or iterations > 1000000:
        return False
    try:
        salt = bytes.fromhex(match.group(2))
        expected = bytes.fromhex(match.group(3))
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


class AuthService(object):
    def __init__(
        self,
        enabled=False,
        session_secret=None,
        users=None,
        session_ttl_seconds=1800,
        cookie_secure=False,
        audit_recorder=None,
        clock=None,
        maximum_sessions=200,
        maximum_failures=5,
        failure_window_seconds=300,
        lockout_seconds=300,
    ):
        self.enabled = bool(enabled)
        self.cookie_secure = bool(cookie_secure)
        self.session_ttl_seconds = max(
            300, min(int(session_ttl_seconds), 8 * 3600)
        )
        self.maximum_sessions = max(
            10, min(int(maximum_sessions), 1000)
        )
        self.maximum_failures = max(
            3, min(int(maximum_failures), 20)
        )
        self.failure_window_seconds = max(
            60, min(int(failure_window_seconds), 3600)
        )
        self.lockout_seconds = max(
            60, min(int(lockout_seconds), 3600)
        )
        self._clock = clock or time.time
        self._audit_recorder = audit_recorder
        self._lock = threading.RLock()
        self._sessions = {}
        self._failures = {}
        self._lockouts = {}
        self._users = self._validate_users(users or {})
        secret_text = str(session_secret or "").strip().lower()
        self.ready = bool(
            not self.enabled
            or (
                re.match(r"^[0-9a-f]{64}$", secret_text)
                and self._users
                and any(
                    user["role"] == "admin"
                    for user in self._users.values()
                )
            )
        )
        self._session_secret = (
            bytes.fromhex(secret_text)
            if re.match(r"^[0-9a-f]{64}$", secret_text)
            else b""
        )

    @classmethod
    def from_environment(
        cls, environ, audit_recorder=None, clock=None
    ):
        values = dict(environ or {})
        enabled = _boolean(
            values.get(AUTH_ENABLED_ENV), False
        )
        users = {}
        for role, username_env, hash_env in (
            (
                "admin",
                AUTH_ADMIN_USERNAME_ENV,
                AUTH_ADMIN_PASSWORD_HASH_ENV,
            ),
            (
                "operator",
                AUTH_OPERATOR_USERNAME_ENV,
                AUTH_OPERATOR_PASSWORD_HASH_ENV,
            ),
            (
                "viewer",
                AUTH_VIEWER_USERNAME_ENV,
                AUTH_VIEWER_PASSWORD_HASH_ENV,
            ),
        ):
            username = str(values.get(username_env, "")).strip()
            encoded = str(values.get(hash_env, "")).strip()
            if username or encoded:
                users[username] = {
                    "role": role,
                    "password_hash": encoded,
                }
        try:
            ttl = int(values.get(AUTH_SESSION_TTL_ENV, "1800"))
        except (TypeError, ValueError) as error:
            raise AuthConfigurationError(
                "authentication session TTL must be an integer"
            ) from error
        return cls(
            enabled=enabled,
            session_secret=values.get(AUTH_SESSION_SECRET_ENV),
            users=users,
            session_ttl_seconds=ttl,
            cookie_secure=_boolean(
                values.get(AUTH_COOKIE_SECURE_ENV), False
            ),
            audit_recorder=audit_recorder,
            clock=clock,
        )

    def summary(self):
        with self._lock:
            self._purge_sessions_locked(float(self._clock()))
            return {
                "schema_version": "1.0",
                "enabled": self.enabled,
                "ready": self.ready,
                "configured_roles": sorted(
                    set(
                        user["role"]
                        for user in self._users.values()
                    )
                ),
                "session_ttl_seconds": self.session_ttl_seconds,
                "active_sessions": len(self._sessions),
                "maximum_sessions": self.maximum_sessions,
                "maximum_failures": self.maximum_failures,
                "failure_window_seconds": (
                    self.failure_window_seconds
                ),
                "lockout_seconds": self.lockout_seconds,
                "cookie_http_only": True,
                "cookie_same_site": "strict",
                "cookie_secure": self.cookie_secure,
                "csrf_required": True,
                "password_scheme": PASSWORD_SCHEME,
                "password_iterations": PASSWORD_ITERATIONS,
                "credentials_exposed": False,
            }

    def login(self, username, password, client_id="unknown"):
        if not self.enabled or not self.ready:
            raise AuthenticationError(
                "AUTH_NOT_CONFIGURED",
                "authentication is not configured",
                status_code=503,
            )
        username = str(username or "").strip()
        password = str(password or "")
        client_id = str(client_id or "unknown")[:128]
        key = "{0}|{1}".format(client_id, username.lower())
        now = float(self._clock())
        with self._lock:
            locked_until = float(self._lockouts.get(key, 0))
            if locked_until > now:
                self._audit(
                    "LOGIN_RATE_LIMITED",
                    username=username,
                    result="DENIED",
                )
                raise AuthenticationError(
                    "AUTH_RATE_LIMITED",
                    "too many failed login attempts",
                    status_code=429,
                )
            user = self._users.get(username)
        encoded = (
            user["password_hash"]
            if user is not None
            else _DUMMY_PASSWORD_HASH
        )
        valid = verify_password(password, encoded)
        if not valid or user is None:
            self._record_failure(key, now)
            self._audit(
                "LOGIN_FAILED",
                username=username,
                result="DENIED",
            )
            raise AuthenticationError(
                "AUTH_INVALID_CREDENTIALS",
                "invalid username or password",
                status_code=401,
            )
        with self._lock:
            self._failures.pop(key, None)
            self._lockouts.pop(key, None)
            self._purge_sessions_locked(now)
            while len(self._sessions) >= self.maximum_sessions:
                oldest = min(
                    self._sessions,
                    key=lambda item: self._sessions[item]["created_at"],
                )
                del self._sessions[oldest]
            session_id = secrets.token_hex(24)
            expires = int(now + self.session_ttl_seconds)
            signature = self._sign(session_id, expires)
            token = "{0}.{1}.{2}".format(
                session_id, expires, signature
            )
            token_hash = self._token_hash(token)
            csrf_token = secrets.token_urlsafe(24)
            session = {
                "username": username,
                "role": user["role"],
                "created_at": now,
                "expires_at": expires,
                "csrf_token": csrf_token,
            }
            self._sessions[token_hash] = session
        self._audit(
            "LOGIN_SUCCEEDED",
            username=username,
            role=user["role"],
            result="ALLOWED",
        )
        return token, self._public_session(session)

    def authenticate(self, token):
        if not self.enabled:
            return {
                "username": "development",
                "role": "admin",
                "csrf_token": None,
                "expires_at": None,
            }
        if not self.ready:
            raise AuthenticationError(
                "AUTH_NOT_CONFIGURED",
                "authentication is not configured",
                status_code=503,
            )
        match = SESSION_TOKEN_PATTERN.match(str(token or ""))
        if match is None:
            raise AuthenticationError(
                "AUTH_REQUIRED", "authentication required"
            )
        session_id = match.group(1)
        expires = int(match.group(2))
        signature = match.group(3)
        if not hmac.compare_digest(
            signature, self._sign(session_id, expires)
        ):
            raise AuthenticationError(
                "AUTH_SESSION_INVALID", "session is invalid"
            )
        now = float(self._clock())
        if expires <= int(now):
            raise AuthenticationError(
                "AUTH_SESSION_EXPIRED", "session has expired"
            )
        token_hash = self._token_hash(str(token))
        with self._lock:
            self._purge_sessions_locked(now)
            session = self._sessions.get(token_hash)
            if session is None:
                raise AuthenticationError(
                    "AUTH_SESSION_INVALID", "session is invalid"
                )
            return dict(session)

    def verify_csrf(self, principal, csrf_token):
        expected = str((principal or {}).get("csrf_token") or "")
        actual = str(csrf_token or "")
        if not expected or not hmac.compare_digest(expected, actual):
            raise AuthenticationError(
                "AUTH_CSRF_INVALID",
                "CSRF token is missing or invalid",
                status_code=403,
            )

    def require_role(self, principal, minimum_role, action=None):
        role = str((principal or {}).get("role") or "")
        if (
            role not in ROLE_RANK
            or minimum_role not in ROLE_RANK
            or ROLE_RANK[role] < ROLE_RANK[minimum_role]
        ):
            self._audit(
                "AUTHORIZATION_DENIED",
                username=(principal or {}).get("username"),
                role=role or None,
                action=action,
                result="DENIED",
            )
            raise AuthenticationError(
                "AUTH_FORBIDDEN",
                "the authenticated role is not authorized",
                status_code=403,
            )
        return True

    def logout(self, token, principal=None):
        token_hash = self._token_hash(str(token or ""))
        with self._lock:
            removed = self._sessions.pop(token_hash, None)
        self._audit(
            "LOGOUT",
            username=(principal or removed or {}).get("username"),
            role=(principal or removed or {}).get("role"),
            result="ALLOWED",
        )
        return removed is not None

    def audit_authorized(self, principal, action, **fields):
        self._audit(
            "AUTHORIZATION_ALLOWED",
            username=(principal or {}).get("username"),
            role=(principal or {}).get("role"),
            action=action,
            result="ALLOWED",
            **fields
        )

    def _sign(self, session_id, expires):
        message = "{0}.{1}".format(session_id, int(expires))
        return hmac.new(
            self._session_secret,
            message.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _token_hash(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_session(session):
        return {
            "schema_version": "1.0",
            "authenticated": True,
            "username": session["username"],
            "role": session["role"],
            "expires_at": int(session["expires_at"]),
            "csrf_token": session["csrf_token"],
        }

    def _record_failure(self, key, now):
        with self._lock:
            recent = [
                timestamp
                for timestamp in self._failures.get(key, [])
                if timestamp >= now - self.failure_window_seconds
            ]
            recent.append(now)
            self._failures[key] = recent[-self.maximum_failures :]
            if len(recent) >= self.maximum_failures:
                self._lockouts[key] = now + self.lockout_seconds
            if len(self._failures) > 1000:
                oldest = min(
                    self._failures,
                    key=lambda item: self._failures[item][-1],
                )
                self._failures.pop(oldest, None)
                self._lockouts.pop(oldest, None)

    def _purge_sessions_locked(self, now):
        expired = [
            token_hash
            for token_hash, session in self._sessions.items()
            if float(session["expires_at"]) <= now
        ]
        for token_hash in expired:
            del self._sessions[token_hash]

    def _audit(self, event_type, **fields):
        if self._audit_recorder is None:
            return
        record = {
            "schema_version": "1.0",
            "timestamp": beijing_timestamp(),
            "record_type": "AUTH_AUDIT",
            "event_type": str(event_type),
        }
        for name in (
            "username",
            "role",
            "action",
            "result",
            "task_id",
            "tool_name",
            "risk",
        ):
            value = fields.get(name)
            if value is not None:
                record[name] = str(value)[:128]
        self._audit_recorder.append(record)

    @staticmethod
    def _validate_users(users):
        validated = {}
        for username, payload in dict(users).items():
            username = str(username or "").strip()
            if not USERNAME_PATTERN.match(username):
                raise AuthConfigurationError(
                    "authentication username is invalid"
                )
            if not isinstance(payload, dict):
                raise AuthConfigurationError(
                    "authentication user is invalid"
                )
            role = str(payload.get("role") or "")
            encoded = str(payload.get("password_hash") or "")
            if role not in ROLE_RANK or HASH_PATTERN.match(encoded) is None:
                raise AuthConfigurationError(
                    "authentication user credentials are invalid"
                )
            validated[username] = {
                "role": role,
                "password_hash": encoded,
            }
        return validated


def _boolean(value, default):
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    raise AuthConfigurationError("authentication boolean is invalid")


_DUMMY_PASSWORD_HASH = hash_password(
    "dummy-password-never-valid",
    salt=b"\x00" * 16,
)
