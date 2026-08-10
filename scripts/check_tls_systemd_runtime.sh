#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CONTAINER_NAME="edgesentinel-visionops"
HEALTH_FILE="$(mktemp)"
HTTPS_FILE="$(mktemp)"

cleanup() {
  rm -f -- "$HEALTH_FILE" "$HTTPS_FILE"
}
trap cleanup EXIT

if [ -f /.dockerenv ]; then
  echo "ERROR: run this check on the Jetson host." >&2
  exit 1
fi

cd "$PROJECT_DIR"
echo "Checking the systemd-managed HTTPS runtime..."
sudo -v
bash "$SCRIPT_DIR/configure_tls_boot.sh" status
bash "$SCRIPT_DIR/check_systemd_runtime.sh"

sudo docker exec "$CONTAINER_NAME" python3 -c \
  "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8000/health',timeout=5).read().decode('utf-8'))" \
  > "$HEALTH_FILE"
sudo docker exec "$CONTAINER_NAME" python3 -c \
  "import hashlib,http.client,json,ssl; from urllib.parse import urlsplit; from urllib.request import urlopen; h=json.load(urlopen('http://127.0.0.1:8000/health',timeout=5)); origin=h['transport_security']['public_origin']; parsed=urlsplit(origin); pem=open('/dev/shm/edgesentinel-tls/server.crt','r').read(); expected=hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).digest(); connection=http.client.HTTPSConnection(parsed.hostname,parsed.port,timeout=5,context=ssl._create_unverified_context()); connection.connect(); presented=connection.sock.getpeercert(binary_form=True); assert hashlib.sha256(presented).digest()==expected, 'TLS certificate pin mismatch'; connection.request('GET','/health'); response=connection.getresponse(); assert response.status==200; print(response.read().decode('utf-8')); connection.close()" \
  > "$HTTPS_FILE"

key_metadata="$(sudo docker exec "$CONTAINER_NAME" stat -c '%F|%a|%s' /dev/shm/edgesentinel-tls/server.key)"
certificate_metadata="$(sudo docker exec "$CONTAINER_NAME" stat -c '%F|%a|%s' /dev/shm/edgesentinel-tls/server.crt)"
container_environment="$(sudo docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER_NAME")"
if printf '%s\n' "$container_environment" | grep -q 'BEGIN.*PRIVATE KEY'; then
  echo "ERROR: TLS private key was persisted in Docker configuration." >&2
  exit 1
fi

python3 -c \
  "import json,sys; direct=json.load(open(sys.argv[1],encoding='utf-8')); secure=json.load(open(sys.argv[2],encoding='utf-8')); transport=direct['transport_security']; auth=direct['authentication']; assert direct['status']=='ok'; assert secure['status']=='ok'; assert transport['tls_enabled'] is True; assert transport['external_https_required'] is True; assert transport['public_origin'].startswith('https://'); assert transport['private_key_exposed'] is False; assert auth['cookie_secure'] is True; assert sys.argv[3].startswith('regular file|600|'); assert sys.argv[4].startswith('regular file|644|'); print(); print('TLS Systemd Runtime acceptance summary:'); print('Status: PASS'); print('Public origin:',transport['public_origin']); print('HTTPS health:',secure['status']); print('External HTTPS required:',transport['external_https_required']); print('Secure cookie:',auth['cookie_secure']); print('TLS private key:',sys.argv[3]); print('TLS certificate:',sys.argv[4]); print('Private key persisted in Docker: False'); print('Internal health transport: loopback HTTP only')" \
  "$HEALTH_FILE" "$HTTPS_FILE" "$key_metadata" "$certificate_metadata"

echo "TLS Systemd Runtime smoke test passed."
