#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CREDENTIAL_DIR="/etc/edgesentinel-visionops"
CREDENTIAL_FILE="$CREDENTIAL_DIR/auth-runtime.env"
UNIT_NAME="edgesentinel-visionops.service"

show_help() {
  echo "Usage: bash scripts/configure_auth_boot.sh COMMAND"
  echo
  echo "Commands:"
  echo "  install  create or replace the root-only Dashboard admin credential"
  echo "  status   verify metadata without printing credentials"
  echo "  remove   remove the persisted authentication credential"
}

require_host() {
  if [ -f /.dockerenv ]; then
    echo "ERROR: run this command on the Jetson host, not inside Docker." >&2
    exit 1
  fi
  sudo -v
}

verify_file() {
  candidate="$1"
  if sudo test -L "$candidate" || ! sudo test -f "$candidate"; then
    echo "ERROR: authentication credential is missing or unsafe." >&2
    exit 1
  fi
  owner="$(sudo stat -c '%U:%G' "$candidate")"
  mode="$(sudo stat -c '%a' "$candidate")"
  [ "$owner" = "root:root" ]
  [ "$mode" = "600" ]
  sudo grep -Fqx "EDGESENTINEL_AUTH_ENABLED=1" "$candidate"
  sudo grep -Fqx "EDGESENTINEL_AUTH_CREDENTIAL_PERSISTED=1" "$candidate"
  sudo grep -Eq '^EDGESENTINEL_AUTH_SESSION_SECRET=[0-9a-f]{64}$' "$candidate"
  sudo grep -Eq '^EDGESENTINEL_AUTH_ADMIN_USERNAME=[A-Za-z][A-Za-z0-9_.-]{2,31}$' "$candidate"
  sudo grep -Eq '^EDGESENTINEL_AUTH_ADMIN_PASSWORD_HASH=pbkdf2_sha256\$[0-9]{5,7}\$[0-9a-f]{32}\$[0-9a-f]{64}$' "$candidate"
}

install_credential() {
  printf '%s\n' "Create the persistent Dashboard administrator account."
  printf '%s\n' "Only a PBKDF2 hash and signing key are stored as root:root 0600."
  printf '%s' "Administrator username [admin]: "
  IFS= read -r AUTH_USERNAME
  AUTH_USERNAME="${AUTH_USERNAME:-admin}"
  IFS= read -r -s -p "Administrator password (12+ characters): " AUTH_PASSWORD
  echo
  IFS= read -r -s -p "Confirm administrator password: " AUTH_CONFIRM
  echo
  if [ "$AUTH_PASSWORD" != "$AUTH_CONFIRM" ]; then
    unset AUTH_PASSWORD AUTH_CONFIRM
    echo "ERROR: passwords do not match." >&2
    echo "Authentication was not installed. Do not restart the service." >&2
    exit 1
  fi
  if [ "${#AUTH_PASSWORD}" -lt 12 ] || [ "${#AUTH_PASSWORD}" -gt 256 ]; then
    unset AUTH_PASSWORD AUTH_CONFIRM
    echo "ERROR: password must contain between 12 and 256 characters." >&2
    echo "Authentication was not installed. Do not restart the service." >&2
    exit 1
  fi

  temporary="$(mktemp)"
  trap 'rm -f -- "$temporary"' EXIT
  if ! printf '%s' "$AUTH_PASSWORD" |
    PYTHONDONTWRITEBYTECODE=1 python3 -m apps.auth_credential \
      --username "$AUTH_USERNAME" > "$temporary"; then
    unset AUTH_PASSWORD AUTH_CONFIRM
    echo "Authentication was not installed. Do not restart the service." >&2
    exit 1
  fi
  unset AUTH_PASSWORD AUTH_CONFIRM
  sudo install --directory --owner root --group root --mode 0700 \
    "$CREDENTIAL_DIR"
  if sudo test -L "$CREDENTIAL_FILE" || \
    { sudo test -e "$CREDENTIAL_FILE" && ! sudo test -f "$CREDENTIAL_FILE"; }; then
    echo "ERROR: refusing unsafe credential path: $CREDENTIAL_FILE" >&2
    exit 1
  fi
  sudo install --owner root --group root --mode 0600 \
    "$temporary" "$CREDENTIAL_FILE"
  verify_file "$CREDENTIAL_FILE"
  echo
  echo "Persistent Dashboard authentication installed."
  echo "Credential: $CREDENTIAL_FILE"
  echo "Owner: root:root"
  echo "Mode: 600"
  echo "Password stored in plaintext: False"
  echo "Current runtime was not restarted."
  echo "Next command: sudo systemctl restart $UNIT_NAME"
}

show_status() {
  if ! sudo test -e "$CREDENTIAL_FILE" && ! sudo test -L "$CREDENTIAL_FILE"; then
    echo "Persistent Dashboard authentication: not installed"
    return
  fi
  verify_file "$CREDENTIAL_FILE"
  echo "Persistent Dashboard authentication: installed"
  echo "Credential: $CREDENTIAL_FILE"
  echo "Owner: root:root"
  echo "Mode: 600"
  echo "Password stored in plaintext: False"
}

remove_credential() {
  if sudo test -e "$CREDENTIAL_FILE" || sudo test -L "$CREDENTIAL_FILE"; then
    sudo rm -f -- "$CREDENTIAL_FILE"
  fi
  echo "Persistent Dashboard authentication removed."
  echo "Protected APIs will fail closed when the systemd default is enabled."
  echo "Current runtime was not restarted."
}

if [ "$#" -ne 1 ]; then
  show_help
  exit 1
fi
require_host
cd "$PROJECT_DIR"
case "$1" in
  install) install_credential ;;
  status) show_status ;;
  remove) remove_credential ;;
  -h|--help|help) show_help ;;
  *) show_help; exit 1 ;;
esac
