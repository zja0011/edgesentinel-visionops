#!/usr/bin/env bash

set -eu
set -o pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CONFIG_DIR="/etc/edgesentinel-visionops"
TLS_DIR="$CONFIG_DIR/tls"
ENV_FILE="$CONFIG_DIR/tls-runtime.env"
CERTIFICATE="$TLS_DIR/server.crt"
PRIVATE_KEY="$TLS_DIR/server.key"
PUBLIC_EXPORT="$PROJECT_DIR/data/runtime/tls/edgesentinel-server.crt"
UNIT_NAME="edgesentinel-visionops.service"
TEMPORARY_DIR=""
CALLER_UID="${SUDO_UID:-$(id -u)}"
CALLER_GID="${SUDO_GID:-$(id -g)}"

cleanup() {
  if [ -n "$TEMPORARY_DIR" ] && [ -d "$TEMPORARY_DIR" ]; then
    rm -rf -- "$TEMPORARY_DIR"
  fi
}
trap cleanup EXIT

show_help() {
  echo "Usage: bash scripts/configure_tls_boot.sh COMMAND"
  echo
  echo "Commands:"
  echo "  install  generate a root-owned self-signed TLS certificate"
  echo "  status   validate TLS files without printing private material"
  echo "  remove   remove TLS configuration and private key"
}

require_host() {
  if [ -f /.dockerenv ]; then
    echo "ERROR: run this command on the Jetson host, not inside Docker." >&2
    exit 1
  fi
  command -v openssl >/dev/null 2>&1 || {
    echo "ERROR: openssl is required." >&2
    exit 1
  }
  sudo -v
}

validate_ip() {
  python3 -c 'import ipaddress,sys; ipaddress.ip_address(sys.argv[1])' "$1"
}

validate_dns() {
  printf '%s' "$1" |
    grep -Eq '^[A-Za-z0-9]([A-Za-z0-9.-]{0,61}[A-Za-z0-9])?$'
}

verify_tls() {
  if sudo test -L "$TLS_DIR" || sudo test -L "$PRIVATE_KEY" || \
    sudo test -L "$CERTIFICATE" || sudo test -L "$ENV_FILE"; then
    echo "ERROR: TLS configuration contains a symbolic link." >&2
    exit 1
  fi
  sudo test -f "$PRIVATE_KEY"
  sudo test -f "$CERTIFICATE"
  sudo test -f "$ENV_FILE"
  [ "$(sudo stat -c '%U:%G' "$PRIVATE_KEY")" = "root:root" ]
  [ "$(sudo stat -c '%a' "$PRIVATE_KEY")" = "600" ]
  [ "$(sudo stat -c '%U:%G' "$CERTIFICATE")" = "root:root" ]
  [ "$(sudo stat -c '%a' "$CERTIFICATE")" = "644" ]
  [ "$(sudo stat -c '%U:%G' "$ENV_FILE")" = "root:root" ]
  [ "$(sudo stat -c '%a' "$ENV_FILE")" = "600" ]
  sudo openssl x509 -in "$CERTIFICATE" -noout -checkend 86400
  sudo openssl rsa -in "$PRIVATE_KEY" -check -noout >/dev/null 2>&1
  certificate_key_hash="$(
    sudo openssl x509 -in "$CERTIFICATE" -pubkey -noout |
      openssl pkey -pubin -outform DER 2>/dev/null |
      sha256sum | cut -d' ' -f1
  )"
  private_key_hash="$(
    sudo openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER 2>/dev/null |
      sha256sum | cut -d' ' -f1
  )"
  [ "$certificate_key_hash" = "$private_key_hash" ]
  sudo grep -Fqx "EDGESENTINEL_TLS_ENABLED=1" "$ENV_FILE"
  sudo grep -Fqx "EDGESENTINEL_AUTH_COOKIE_SECURE=1" "$ENV_FILE"
  sudo grep -Eq '^EDGESENTINEL_TLS_PUBLIC_ORIGIN=https://[^/]+:8443$' "$ENV_FILE"
  sudo grep -Fqx "EDGESENTINEL_TLS_CREDENTIAL_PERSISTED=1" "$ENV_FILE"
}

install_tls() {
  default_ip="192.168.1.101"
  default_dns="$(hostname)"
  printf 'Jetson LAN IP [%s]: ' "$default_ip"
  IFS= read -r lan_ip
  lan_ip="${lan_ip:-$default_ip}"
  printf 'Jetson DNS name [%s]: ' "$default_dns"
  IFS= read -r dns_name
  dns_name="${dns_name:-$default_dns}"
  if ! validate_ip "$lan_ip"; then
    echo "ERROR: invalid IP address." >&2
    exit 1
  fi
  if ! validate_dns "$dns_name"; then
    echo "ERROR: invalid DNS name." >&2
    exit 1
  fi

  TEMPORARY_DIR="$(mktemp -d)"
  chmod 0700 "$TEMPORARY_DIR"
  request_config="$TEMPORARY_DIR/openssl.cnf"
  temporary_key="$TEMPORARY_DIR/server.key"
  temporary_cert="$TEMPORARY_DIR/server.crt"
  cat > "$request_config" <<EOF
[req]
prompt = no
distinguished_name = subject
x509_extensions = extensions
[subject]
CN = $dns_name
O = EdgeSentinel VisionOps
[extensions]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @names
[names]
IP.1 = $lan_ip
DNS.1 = $dns_name
EOF
  umask 077
  openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
    -days 825 -config "$request_config" \
    -keyout "$temporary_key" -out "$temporary_cert" >/dev/null 2>&1
  openssl x509 -in "$temporary_cert" -noout -checkend 86400
  openssl rsa -in "$temporary_key" -check -noout >/dev/null 2>&1
  temporary_certificate_hash="$(
    openssl x509 -in "$temporary_cert" -pubkey -noout |
      openssl pkey -pubin -outform DER 2>/dev/null |
      sha256sum | cut -d' ' -f1
  )"
  temporary_private_hash="$(
    openssl pkey -in "$temporary_key" -pubout -outform DER 2>/dev/null |
      sha256sum | cut -d' ' -f1
  )"
  [ "$temporary_certificate_hash" = "$temporary_private_hash" ]

  sudo install --directory --owner root --group root --mode 0700 \
    "$CONFIG_DIR" "$TLS_DIR"
  sudo install --owner root --group root --mode 0600 \
    "$temporary_key" "$PRIVATE_KEY"
  sudo install --owner root --group root --mode 0644 \
    "$temporary_cert" "$CERTIFICATE"
  {
    printf '%s\n' "EDGESENTINEL_TLS_ENABLED=1"
    printf '%s\n' "EDGESENTINEL_TLS_PORT=8443"
    printf '%s\n' "EDGESENTINEL_TLS_CERTIFICATE=/dev/shm/edgesentinel-tls/server.crt"
    printf '%s\n' "EDGESENTINEL_TLS_PRIVATE_KEY=/dev/shm/edgesentinel-tls/server.key"
    printf '%s\n' "EDGESENTINEL_TLS_PUBLIC_ORIGIN=https://$lan_ip:8443"
    printf '%s\n' "EDGESENTINEL_AUTH_COOKIE_SECURE=1"
    printf '%s\n' "EDGESENTINEL_TLS_CREDENTIAL_PERSISTED=1"
  } > "$TEMPORARY_DIR/tls-runtime.env"
  sudo install --directory --owner "$CALLER_UID" --group "$CALLER_GID" \
    --mode 0755 "$(dirname -- "$PUBLIC_EXPORT")"
  sudo install --owner "$CALLER_UID" --group "$CALLER_GID" --mode 0644 \
    "$temporary_cert" "$PUBLIC_EXPORT"
  sudo install --owner root --group root --mode 0600 \
    "$TEMPORARY_DIR/tls-runtime.env" "$ENV_FILE"
  verify_tls
  fingerprint="$(sudo openssl x509 -in "$CERTIFICATE" -noout -fingerprint -sha256 | cut -d= -f2-)"

  echo
  echo "Persistent TLS configuration installed."
  echo "Public origin: https://$lan_ip:8443"
  echo "Certificate: $CERTIFICATE (root:root 644)"
  echo "Private key: $PRIVATE_KEY (root:root 600)"
  echo "Public certificate export: $PUBLIC_EXPORT"
  echo "SHA-256 fingerprint: $fingerprint"
  echo "Private key persisted in Docker: False"
  echo "Current runtime was not restarted."
  echo "Next command: sudo systemctl restart $UNIT_NAME"
}

show_status() {
  if ! sudo test -e "$ENV_FILE"; then
    echo "Persistent TLS configuration: not installed"
    return
  fi
  verify_tls
  origin="$(sudo sed -n 's/^EDGESENTINEL_TLS_PUBLIC_ORIGIN=//p' "$ENV_FILE")"
  fingerprint="$(sudo openssl x509 -in "$CERTIFICATE" -noout -fingerprint -sha256 | cut -d= -f2-)"
  echo "Persistent TLS configuration: installed"
  echo "Public origin: $origin"
  echo "Certificate valid beyond 24 hours: True"
  echo "Private key owner/mode: root:root 600"
  echo "SHA-256 fingerprint: $fingerprint"
  echo "Private key exposed: False"
}

remove_tls() {
  if sudo test -e "$ENV_FILE" || sudo test -L "$ENV_FILE"; then
    sudo rm -f -- "$ENV_FILE"
  fi
  if sudo test -e "$TLS_DIR" || sudo test -L "$TLS_DIR"; then
    sudo rm -f -- "$PRIVATE_KEY" "$CERTIFICATE"
    sudo rmdir -- "$TLS_DIR"
  fi
  rm -f -- "$PUBLIC_EXPORT"
  echo "Persistent TLS configuration removed."
  echo "Current runtime was not restarted."
}

if [ "$#" -ne 1 ]; then
  show_help
  exit 1
fi
require_host
cd "$PROJECT_DIR"
case "$1" in
  install) install_tls ;;
  status) show_status ;;
  remove) remove_tls ;;
  -h|--help|help) show_help ;;
  *) show_help; exit 1 ;;
esac
