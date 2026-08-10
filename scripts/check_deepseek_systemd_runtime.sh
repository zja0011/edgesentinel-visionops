#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CREDENTIAL_FILE="/etc/edgesentinel-visionops/model-runtime.env"
UNIT_NAME="edgesentinel-visionops.service"
CONTAINER_NAME="edgesentinel-visionops"
STATUS_FILE="$(mktemp)"
HEALTH_FILE="$(mktemp)"

cleanup() {
  rm -f -- "$STATUS_FILE" "$HEALTH_FILE"
}
trap cleanup EXIT

if [ -f /.dockerenv ]; then
  echo "ERROR: run this check on the Jetson host." >&2
  exit 1
fi

echo "Checking the persistent DeepSeek systemd runtime..."
sudo -v
bash "$SCRIPT_DIR/configure_deepseek_boot.sh" status

[ "$(sudo systemctl is-enabled "$UNIT_NAME")" = "enabled" ]
[ "$(sudo systemctl is-active "$UNIT_NAME")" = "active" ]

container_environment="$(sudo docker inspect \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  "$CONTAINER_NAME")"
if printf '%s\n' "$container_environment" |
  grep -q '^EDGESENTINEL_MODEL_API_KEY='; then
  echo "ERROR: DeepSeek API key was persisted in Docker config." >&2
  exit 1
fi

sudo docker exec "$CONTAINER_NAME" \
  python3 -m apps.service_manager status --json > "$STATUS_FILE"
sudo docker exec "$CONTAINER_NAME" \
  python3 -c \
    "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8000/health',timeout=3).read().decode('utf-8'))" \
    > "$HEALTH_FILE"

PYTHONPATH="$PROJECT_DIR/vendor/python${PYTHONPATH:+:$PYTHONPATH}" \
python3 - "$STATUS_FILE" "$HEALTH_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    status = json.load(stream)
with open(sys.argv[2], encoding="utf-8") as stream:
    health = json.load(stream)

model = health.get("agent_model") or {}
assert status["status"] == "running"
assert status["process"]["verified"] is True
assert status["model_mode"] == "remote"
assert status["model_credential_persisted"] is True
assert model.get("mode") == "remote"
assert model.get("provider") == "deepseek"
assert model.get("model") == "deepseek-v4-flash"
assert model.get("external_requests_enabled") is True
assert model.get("credential_source") == "environment"
raw = json.dumps([status, health]).lower()
assert "api_key" not in raw
assert "sk-" not in raw

print()
print("Persistent DeepSeek Runtime acceptance summary:")
print("Service:", status["status"])
print("Model mode:", model["mode"])
print("Provider:", model["provider"])
print("Model:", model["model"])
print("External requests enabled:", model["external_requests_enabled"])
print("Credential file: root:root 600")
print("Credential persisted:", status["model_credential_persisted"])
print("API key exposed:", False)
print("Persistent DeepSeek Runtime smoke test passed.")
PY
