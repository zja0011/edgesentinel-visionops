#!/usr/bin/env bash
set -euo pipefail

credential_dir="/etc/edgesentinel-visionops"
credential_path="$credential_dir/recovery-export.key"
action="${1:-status}"

if [ "$(id -u)" -ne 0 ]; then
  exec sudo bash "$0" "$@"
fi

case "$action" in
  install)
    echo "Configure the off-device recovery export passphrase."
    echo "Record the same passphrase in an independent password manager."
    if [ -e "$credential_path" ]; then
      echo "ERROR: a recovery export credential already exists." >&2
      echo "Key rotation is intentionally not an implicit v1 operation." >&2
      exit 1
    fi
    read -r -s -p "Recovery export passphrase (16+ characters): " first
    echo
    read -r -s -p "Confirm recovery export passphrase: " second
    echo
    if [ "$first" != "$second" ]; then
      echo "ERROR: passphrases do not match." >&2
      exit 2
    fi
    if [ "${#first}" -lt 16 ] || [ "${#first}" -gt 256 ]; then
      echo "ERROR: passphrase must contain between 16 and 256 characters." >&2
      exit 2
    fi
    mkdir -p -- "$credential_dir"
    chmod 700 -- "$credential_dir"
    temporary="$(mktemp "$credential_dir/.recovery-export.key.XXXXXX")"
    trap 'rm -f -- "${temporary:-}"' EXIT
    umask 077
    printf '%s\n' "$first" > "$temporary"
    chown root:root -- "$temporary"
    chmod 600 -- "$temporary"
    mv -f -- "$temporary" "$credential_path"
    trap - EXIT
    unset first second
    echo
    echo "Encrypted recovery export credential installed."
    echo "Credential: $credential_path"
    echo "Owner: root:root"
    echo "Mode: 600"
    echo "Passphrase exposed: False"
    ;;
  status)
    if [ ! -f "$credential_path" ] || [ -L "$credential_path" ]; then
      echo "Encrypted recovery export credential: not installed"
      exit 1
    fi
    identity="$(stat -c '%U:%G %a' "$credential_path")"
    if [ "$identity" != "root:root 600" ]; then
      echo "ERROR: invalid recovery export credential ownership or mode: $identity" >&2
      exit 1
    fi
    echo "Encrypted recovery export credential: installed"
    echo "Credential: $credential_path"
    echo "Owner/mode: $identity"
    echo "Passphrase exposed: False"
    ;;
  *)
    echo "Usage: bash scripts/configure_recovery_export_key.sh {install|status}" >&2
    exit 2
    ;;
esac
