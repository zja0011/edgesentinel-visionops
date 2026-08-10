#!/usr/bin/env bash

set -eu

CONFIG_DIR="/etc/edgesentinel-visionops"
CONFIG_FILE="$CONFIG_DIR/weather-runtime.env"
UNIT_NAME="edgesentinel-visionops.service"

show_help() {
  echo "Usage: bash scripts/configure_weather_boot.sh COMMAND"
  echo
  echo "Commands:"
  echo "  install  set the default city used by weather questions"
  echo "  status   show whether a default city is configured"
  echo "  remove   remove the default weather city"
}

require_host() {
  if [ -f /.dockerenv ]; then
    echo "ERROR: run this command on the Jetson host, not inside Docker." >&2
    exit 1
  fi
  sudo -v
}

verify_file() {
  if sudo test -L "$CONFIG_FILE" ||
    ! sudo test -f "$CONFIG_FILE"; then
    echo "ERROR: weather configuration is missing or unsafe." >&2
    exit 1
  fi
  [ "$(sudo stat -c '%U:%G' "$CONFIG_FILE")" = "root:root" ]
  [ "$(sudo stat -c '%a' "$CONFIG_FILE")" = "600" ]
  sudo grep -Eq \
    '^EDGESENTINEL_WEATHER_DEFAULT_LOCATION=[^=[:cntrl:]]{2,80}$' \
    "$CONFIG_FILE"
}

install_location() {
  printf '%s' "Default weather city (for example Shenzhen or 深圳): "
  IFS= read -r WEATHER_LOCATION
  if ! printf '%s' "$WEATHER_LOCATION" |
    grep -Eq '^[^=[:cntrl:]]{2,80}$'; then
    unset WEATHER_LOCATION
    echo "ERROR: city must contain 2-80 characters and no '='." >&2
    exit 1
  fi

  sudo install --directory \
    --owner root \
    --group root \
    --mode 0700 \
    "$CONFIG_DIR"
  if sudo test -L "$CONFIG_FILE" ||
    { sudo test -e "$CONFIG_FILE" && ! sudo test -f "$CONFIG_FILE"; }; then
    unset WEATHER_LOCATION
    echo "ERROR: refusing unsafe weather configuration path." >&2
    exit 1
  fi
  printf '%s\n' \
    "EDGESENTINEL_WEATHER_DEFAULT_LOCATION=$WEATHER_LOCATION" |
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
    ' sh "$CONFIG_FILE"
  unset WEATHER_LOCATION
  verify_file

  echo
  echo "Default weather city installed."
  echo "Configuration: $CONFIG_FILE"
  echo "Owner: root:root"
  echo "Mode: 600"
  echo "Current runtime was not restarted."
  echo "Next command: sudo systemctl restart $UNIT_NAME"
}

show_status() {
  if ! sudo test -e "$CONFIG_FILE"; then
    echo "Default weather city: not configured"
    return
  fi
  verify_file
  location="$(
    sudo sed -n \
      's/^EDGESENTINEL_WEATHER_DEFAULT_LOCATION=//p' \
      "$CONFIG_FILE"
  )"
  echo "Default weather city: $location"
  echo "Configuration: $CONFIG_FILE"
  echo "Owner: root:root"
  echo "Mode: 600"
}

remove_location() {
  if sudo test -L "$CONFIG_FILE"; then
    echo "ERROR: refusing symlinked weather configuration." >&2
    exit 1
  fi
  sudo rm -f -- "$CONFIG_FILE"
  echo "Default weather city removed."
  echo "Weather questions must now include a city."
  echo "Current runtime was not restarted."
}

if [ "$#" -ne 1 ]; then
  show_help
  exit 1
fi

require_host
case "$1" in
  install)
    install_location
    ;;
  status)
    show_status
    ;;
  remove)
    remove_location
    ;;
  -h|--help|help)
    show_help
    ;;
  *)
    show_help
    exit 1
    ;;
esac
