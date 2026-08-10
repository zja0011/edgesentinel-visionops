"""Generate a root-owned authentication environment without echoing secrets."""

import argparse
import secrets
import sys

from packages.api.auth_service import (
    USERNAME_PATTERN,
    AuthConfigurationError,
    hash_password,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--session-ttl", type=int, default=1800)
    parser.add_argument("--cookie-secure", action="store_true")
    arguments = parser.parse_args(argv)
    username = str(arguments.username or "").strip()
    if USERNAME_PATTERN.match(username) is None:
        raise SystemExit("authentication username is invalid")
    if arguments.session_ttl < 300 or arguments.session_ttl > 28800:
        raise SystemExit("session TTL must be between 300 and 28800 seconds")
    password = sys.stdin.read()
    if password.endswith("\n"):
        password = password[:-1]
    try:
        encoded = hash_password(password)
    except AuthConfigurationError as error:
        raise SystemExit(str(error))
    lines = (
        "EDGESENTINEL_AUTH_ENABLED=1",
        "EDGESENTINEL_AUTH_SESSION_SECRET={0}".format(
            secrets.token_hex(32)
        ),
        "EDGESENTINEL_AUTH_SESSION_TTL_SECONDS={0}".format(
            arguments.session_ttl
        ),
        "EDGESENTINEL_AUTH_COOKIE_SECURE={0}".format(
            1 if arguments.cookie_secure else 0
        ),
        "EDGESENTINEL_AUTH_ADMIN_USERNAME={0}".format(username),
        "EDGESENTINEL_AUTH_ADMIN_PASSWORD_HASH={0}".format(encoded),
        "EDGESENTINEL_AUTH_CREDENTIAL_PERSISTED=1",
    )
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
