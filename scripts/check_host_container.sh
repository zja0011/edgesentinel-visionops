#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CONTAINER_NAME="${EDGESENTINEL_CONTAINER_NAME:-edgesentinel-visionops}"
CONTAINER_IMAGE="${EDGESENTINEL_CONTAINER_IMAGE:-dustynv/jetson-inference:r32.7.1}"
MANAGED_LABEL="com.edgesentinel.managed"

docker_cmd() {
  sudo docker "$@"
}

if [ -f /.dockerenv ]; then
  echo "ERROR: this check must run on the Jetson host, not inside Docker." >&2
  exit 1
fi

echo "Checking the detached EdgeSentinel container..."
sudo -v

running="$(docker_cmd inspect \
  --format '{{.State.Running}}' \
  "$CONTAINER_NAME")"
label="$(docker_cmd inspect \
  --format "{{index .Config.Labels \"$MANAGED_LABEL\"}}" \
  "$CONTAINER_NAME")"
image="$(docker_cmd inspect \
  --format '{{.Config.Image}}' \
  "$CONTAINER_NAME")"
network="$(docker_cmd inspect \
  --format '{{.HostConfig.NetworkMode}}' \
  "$CONTAINER_NAME")"
restart_policy="$(docker_cmd inspect \
  --format '{{.HostConfig.RestartPolicy.Name}}' \
  "$CONTAINER_NAME")"
project_mount="$(docker_cmd inspect \
  --format '{{range .Mounts}}{{if eq .Destination "/workspace/edgesentinel"}}{{.Source}}{{end}}{{end}}' \
  "$CONTAINER_NAME")"
container_environment="$(docker_cmd inspect \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  "$CONTAINER_NAME")"

[ "$running" = "true" ]
[ "$label" = "true" ]
[ "$image" = "$CONTAINER_IMAGE" ]
[ "$network" = "host" ]
[ "$restart_policy" = "no" ]
[ "$project_mount" = "$PROJECT_DIR" ]
if printf '%s\n' "$container_environment" |
  grep -q '^EDGESENTINEL_CONFIG_TOKEN='; then
  echo "ERROR: configuration token was persisted in Docker." >&2
  exit 1
fi
docker_cmd exec "$CONTAINER_NAME" test -c /dev/video0

docker_cmd exec "$CONTAINER_NAME" \
  bash scripts/check_service_manager.sh

echo
echo "Host Container acceptance summary:"
echo "Container: $CONTAINER_NAME"
echo "Running: $running"
echo "Managed label: $label"
echo "Image: $image"
echo "Network: $network"
echo "Project mount: $project_mount"
echo "Camera device: available"
echo "Restart policy: $restart_policy"
echo "Token persisted in Docker: False"
echo "Host Container smoke test passed."
