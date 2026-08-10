#!/usr/bin/env bash

set -eu

CREDENTIAL_DIR="/etc/edgesentinel-visionops"
CREDENTIAL_FILE="$CREDENTIAL_DIR/model-runtime.env"
DISABLED_FILE="$CREDENTIAL_DIR/model-runtime.env.disabled"
UNIT_NAME="edgesentinel-visionops.service"

show_help() {
  echo "Usage: bash scripts/configure_deepseek_boot.sh COMMAND"
  echo
  echo "Commands:"
  echo "  install  securely store a DeepSeek key for systemd boot"
  echo "  status   verify metadata without printing the key"
  echo "  offline  keep the key but select offline mode on next start"
  echo "  online   select DeepSeek mode again on next start"
  echo "  remove   remove the persisted model credential"
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
    echo "ERROR: model credential is missing or is not a regular file." >&2
    exit 1
  fi
  owner="$(sudo stat -c '%U:%G' "$candidate")"
  mode="$(sudo stat -c '%a' "$candidate")"
  [ "$owner" = "root:root" ]
  [ "$mode" = "600" ]
  sudo grep -Fqx "EDGESENTINEL_MODEL_MODE=remote" "$candidate"
  sudo grep -Fqx "EDGESENTINEL_MODEL_PROVIDER=deepseek" "$candidate"
  sudo grep -Fqx \
    "EDGESENTINEL_MODEL_CREDENTIAL_PERSISTED=1" \
    "$candidate"
  if ! sudo grep -Eq \
    '^EDGESENTINEL_MODEL_API_KEY=[A-Za-z0-9._-]{16,}$' \
    "$candidate"; then
    echo "ERROR: stored DeepSeek credential has an invalid format." >&2
    exit 1
  fi
}

install_key() {
  echo "Store the DeepSeek API key for automatic startup."
  echo "The file will be root:root 0600 and will not be stored in Docker."
  IFS= read -r -s -p "DeepSeek API Key: " MODEL_API_KEY
  echo
  if ! printf '%s' "$MODEL_API_KEY" |
    grep -Eq '^[A-Za-z0-9._-]{16,}$'; then
    unset MODEL_API_KEY
    echo "ERROR: key must be at least 16 characters and contain only" >&2
    echo "letters, digits, dot, underscore, or hyphen." >&2
    exit 1
  fi

  sudo install --directory \
    --owner root \
    --group root \
    --mode 0700 \
    "$CREDENTIAL_DIR"
  for candidate in "$CREDENTIAL_FILE" "$DISABLED_FILE"; do
    if sudo test -L "$candidate" ||
      { sudo test -e "$candidate" && ! sudo test -f "$candidate"; }; then
      unset MODEL_API_KEY
      echo "ERROR: refusing unsafe credential path: $candidate" >&2
      exit 1
    fi
  done
  {
    printf '%s\n' "EDGESENTINEL_MODEL_MODE=remote"
    printf '%s\n' "EDGESENTINEL_MODEL_PROVIDER=deepseek"
    printf '%s\n' "EDGESENTINEL_MODEL_API_KEY=$MODEL_API_KEY"
    printf '%s\n' "EDGESENTINEL_MODEL_TIMEOUT_SECONDS=30"
    printf '%s\n' "EDGESENTINEL_MODEL_MAX_TOKENS=512"
    printf '%s\n' "EDGESENTINEL_MODEL_CREDENTIAL_PERSISTED=1"
  } |
    sudo /bin/sh -c '
      set -eu
      target="$1"
      temporary="${target}.tmp.$$"
      trap "rm -f -- \"$temporary\"" EXIT
      umask 077
      cat > "$temporary"
      chown root:root "$temporary"
      chmod 0600 "$temporary"
      mv -f -- "$temporary" "$target"
      trap - EXIT
    ' sh "$CREDENTIAL_FILE"
  unset MODEL_API_KEY
  sudo rm -f -- "$DISABLED_FILE"
  verify_file "$CREDENTIAL_FILE"

  echo
  echo "Persistent DeepSeek configuration installed."
  echo "Credential: $CREDENTIAL_FILE"
  echo "Owner: root:root"
  echo "Mode: 600"
  echo "Current runtime was not restarted."
  echo "Next command: sudo systemctl restart $UNIT_NAME"
}

show_status() {
  if sudo test -e "$CREDENTIAL_FILE" ||
    sudo test -L "$CREDENTIAL_FILE"; then
    verify_file "$CREDENTIAL_FILE"
    echo "Persistent DeepSeek configuration: installed"
    echo "Boot model: deepseek (enabled)"
    echo "Credential: $CREDENTIAL_FILE"
  elif sudo test -e "$DISABLED_FILE" ||
    sudo test -L "$DISABLED_FILE"; then
    verify_file "$DISABLED_FILE"
    echo "Persistent DeepSeek configuration: installed"
    echo "Boot model: offline-rule-mock (DeepSeek disabled)"
    echo "Credential: $DISABLED_FILE"
  else
    echo "Persistent DeepSeek configuration: not installed"
    echo "Boot model fallback: offline-rule-mock"
    return
  fi
  echo "Owner: root:root"
  echo "Mode: 600"
  echo "Provider: deepseek"
  echo "API key: hidden"
}

select_offline() {
  if sudo test -e "$DISABLED_FILE" ||
    sudo test -L "$DISABLED_FILE"; then
    verify_file "$DISABLED_FILE"
    echo "Offline mode is already selected."
  elif sudo test -e "$CREDENTIAL_FILE" ||
    sudo test -L "$CREDENTIAL_FILE"; then
    verify_file "$CREDENTIAL_FILE"
    sudo mv -- "$CREDENTIAL_FILE" "$DISABLED_FILE"
    verify_file "$DISABLED_FILE"
    echo "Offline mode selected; the root-only DeepSeek key was retained."
  else
    echo "Offline mode selected; no DeepSeek credential is installed."
  fi
  echo "Current runtime was not restarted."
  echo "Next command: sudo systemctl restart $UNIT_NAME"
}

select_online() {
  if sudo test -e "$CREDENTIAL_FILE" ||
    sudo test -L "$CREDENTIAL_FILE"; then
    verify_file "$CREDENTIAL_FILE"
    echo "DeepSeek mode is already selected."
  elif sudo test -e "$DISABLED_FILE" ||
    sudo test -L "$DISABLED_FILE"; then
    verify_file "$DISABLED_FILE"
    sudo mv -- "$DISABLED_FILE" "$CREDENTIAL_FILE"
    verify_file "$CREDENTIAL_FILE"
    echo "DeepSeek mode selected for the next service start."
  else
    echo "ERROR: no stored DeepSeek key exists." >&2
    echo "Run: bash scripts/configure_deepseek_boot.sh install" >&2
    exit 1
  fi
  echo "Current runtime was not restarted."
  echo "Next command: sudo systemctl restart $UNIT_NAME"
}

remove_key() {
  if sudo test -e "$CREDENTIAL_FILE" ||
    sudo test -L "$CREDENTIAL_FILE"; then
    sudo rm -f -- "$CREDENTIAL_FILE"
  fi
  if sudo test -e "$DISABLED_FILE" ||
    sudo test -L "$DISABLED_FILE"; then
    sudo rm -f -- "$DISABLED_FILE"
  fi
  echo "Persistent DeepSeek configuration removed."
  echo "The next service start will use offline-rule-mock."
  echo "Current runtime was not restarted."
}

if [ "$#" -ne 1 ]; then
  show_help
  exit 1
fi

require_host
case "$1" in
  install)
    install_key
    ;;
  status)
    show_status
    ;;
  offline)
    select_offline
    ;;
  online)
    select_online
    ;;
  remove)
    remove_key
    ;;
  -h|--help|help)
    show_help
    ;;
  *)
    show_help
    exit 1
    ;;
esac
