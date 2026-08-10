#!/usr/bin/env bash

set -eu

CONFIG_DIR="/etc/edgesentinel-visionops"
CONFIG_FILE="$CONFIG_DIR/model-cost-runtime.env"
UNIT_NAME="edgesentinel-visionops.service"

show_help() {
  echo "Usage: bash scripts/configure_model_cost_boot.sh COMMAND"
  echo
  echo "Commands:"
  echo "  install  store an operator-supplied USD rate card and task cap"
  echo "  status   show the non-secret configured rate card"
  echo "  remove   remove cost estimation and retain token limits"
}

require_host() {
  if [ -f /.dockerenv ]; then
    echo "ERROR: run this command on the Jetson host, not inside Docker." >&2
    exit 1
  fi
  sudo -v
}

valid_number() {
  value="$1"
  allow_zero="$2"
  if ! printf '%s' "$value" |
    grep -Eq '^(10000|0|[1-9][0-9]{0,3})(\.[0-9]{1,6})?$'; then
    return 1
  fi
  awk -v value="$value" -v allow_zero="$allow_zero" '
    BEGIN {
      if (value > 10000) exit 1
      if (allow_zero == "no" && value <= 0) exit 1
      exit 0
    }
  '
}

verify_file() {
  if sudo test -L "$CONFIG_FILE" || ! sudo test -f "$CONFIG_FILE"; then
    echo "ERROR: model cost configuration is unavailable or unsafe." >&2
    exit 1
  fi
  [ "$(sudo stat -c '%U:%G' "$CONFIG_FILE")" = "root:root" ]
  [ "$(sudo stat -c '%a' "$CONFIG_FILE")" = "600" ]
  sudo grep -Eq \
    '^EDGESENTINEL_MODEL_RATE_CARD_ID=[A-Za-z0-9._:-]{1,64}$' \
    "$CONFIG_FILE"
  for name in \
    EDGESENTINEL_MODEL_INPUT_USD_PER_MILLION \
    EDGESENTINEL_MODEL_OUTPUT_USD_PER_MILLION \
    EDGESENTINEL_MODEL_MAX_ESTIMATED_COST_USD; do
    sudo grep -Eq "^${name}=(10000|0|[1-9][0-9]{0,3})(\\.[0-9]{1,6})?$" \
      "$CONFIG_FILE"
  done
}

install_rate_card() {
  printf '%s' "Rate card ID (letters, digits, . _ : -): "
  IFS= read -r RATE_CARD_ID
  printf '%s' "Input USD per million tokens: "
  IFS= read -r INPUT_RATE
  printf '%s' "Output USD per million tokens: "
  IFS= read -r OUTPUT_RATE
  printf '%s' "Maximum estimated USD per Agent task: "
  IFS= read -r MAXIMUM_COST

  if ! printf '%s' "$RATE_CARD_ID" |
    grep -Eq '^[A-Za-z0-9._:-]{1,64}$'; then
    echo "ERROR: rate card ID is invalid." >&2
    exit 1
  fi
  valid_number "$INPUT_RATE" yes || {
    echo "ERROR: input rate must be between 0 and 10000." >&2
    exit 1
  }
  valid_number "$OUTPUT_RATE" yes || {
    echo "ERROR: output rate must be between 0 and 10000." >&2
    exit 1
  }
  valid_number "$MAXIMUM_COST" no || {
    echo "ERROR: task cost cap must be greater than 0 and at most 10000." >&2
    exit 1
  }

  sudo install --directory --owner root --group root --mode 0700 \
    "$CONFIG_DIR"
  if sudo test -L "$CONFIG_FILE" || {
    sudo test -e "$CONFIG_FILE" && ! sudo test -f "$CONFIG_FILE"
  }; then
    echo "ERROR: refusing unsafe configuration path." >&2
    exit 1
  fi
  {
    printf '%s\n' "EDGESENTINEL_MODEL_RATE_CARD_ID=$RATE_CARD_ID"
    printf '%s\n' "EDGESENTINEL_MODEL_INPUT_USD_PER_MILLION=$INPUT_RATE"
    printf '%s\n' "EDGESENTINEL_MODEL_OUTPUT_USD_PER_MILLION=$OUTPUT_RATE"
    printf '%s\n' "EDGESENTINEL_MODEL_MAX_ESTIMATED_COST_USD=$MAXIMUM_COST"
  } | sudo /bin/sh -c '
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
  ' sh "$CONFIG_FILE"
  verify_file
  echo
  echo "Model cost rate card installed."
  echo "Configuration: $CONFIG_FILE"
  echo "Owner: root:root"
  echo "Mode: 600"
  echo "This is an estimate policy, not a provider invoice."
  echo "Next command: sudo systemctl restart $UNIT_NAME"
}

show_status() {
  if ! sudo test -e "$CONFIG_FILE" && ! sudo test -L "$CONFIG_FILE"; then
    echo "Model cost estimation: not configured"
    echo "Token budget remains active."
    return
  fi
  verify_file
  echo "Model cost estimation: configured"
  sudo grep -E \
    '^EDGESENTINEL_MODEL_(RATE_CARD_ID|INPUT_USD_PER_MILLION|OUTPUT_USD_PER_MILLION|MAX_ESTIMATED_COST_USD)=' \
    "$CONFIG_FILE"
}

remove_rate_card() {
  if sudo test -L "$CONFIG_FILE"; then
    echo "ERROR: refusing symbolic-link configuration path." >&2
    exit 1
  fi
  sudo rm -f -- "$CONFIG_FILE"
  echo "Model cost estimation removed; token budget remains active."
  echo "Next command: sudo systemctl restart $UNIT_NAME"
}

if [ "$#" -ne 1 ]; then
  show_help
  exit 1
fi

require_host
case "$1" in
  install) install_rate_card ;;
  status) show_status ;;
  remove) remove_rate_card ;;
  -h|--help|help) show_help ;;
  *) show_help; exit 1 ;;
esac
