#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
PROJECT_PARENT="$(dirname -- "$PROJECT_DIR")"
INFERENCE_DIR="${EDGESENTINEL_INFERENCE_DIR:-$PROJECT_PARENT/jetson-inference}"
CONTAINER_NAME="${EDGESENTINEL_CONTAINER_NAME:-edgesentinel-visionops}"
CONTAINER_IMAGE="${EDGESENTINEL_CONTAINER_IMAGE:-dustynv/jetson-inference:r32.7.1}"
MANAGED_LABEL="com.edgesentinel.managed"
MODEL_FILE="/tmp/edgesentinel_nv_jetson_model"

show_help() {
  echo "Usage: bash scripts/host_edgesentinel.sh COMMAND"
  echo
  echo "Commands:"
  echo "  start   create/start the detached container and live runtime"
  echo "  start-deepseek  temporary DeepSeek start; key stays in memory"
  echo "  boot-start  non-interactive read-only start for systemd"
  echo "  stop    stop the live runtime and then the container"
  echo "  status  show container and live runtime status"
  echo "  logs    show the latest live runtime log"
  echo "  shell   open an interactive shell in the running container"
}

docker_cmd() {
  sudo docker "$@"
}

container_exists() {
  docker_cmd inspect "$CONTAINER_NAME" >/dev/null 2>&1
}

container_running() {
  [ "$(docker_cmd inspect \
    --format '{{.State.Running}}' \
    "$CONTAINER_NAME")" = "true" ]
}

prepare_model_file() {
  if [ -L "$MODEL_FILE" ]; then
    echo "ERROR: NVIDIA model mount path must not be a symbolic link:" >&2
    echo "  $MODEL_FILE" >&2
    exit 1
  fi
  if [ -d "$MODEL_FILE" ]; then
    sudo rm -f -- "$MODEL_FILE/model"
    if ! sudo rmdir -- "$MODEL_FILE"; then
      echo "ERROR: NVIDIA model mount directory contains unexpected data:" >&2
      echo "  $MODEL_FILE" >&2
      exit 1
    fi
  fi
  if [ -e "$MODEL_FILE" ] && [ ! -f "$MODEL_FILE" ]; then
    echo "ERROR: NVIDIA model mount path is not a regular file:" >&2
    echo "  $MODEL_FILE" >&2
    exit 1
  fi
  if [ -r /proc/device-tree/model ]; then
    sudo cp /proc/device-tree/model "$MODEL_FILE"
  else
    sudo touch "$MODEL_FILE"
  fi
}

validate_managed_container() {
  label="$(docker_cmd inspect \
    --format "{{index .Config.Labels \"$MANAGED_LABEL\"}}" \
    "$CONTAINER_NAME")"
  if [ "$label" != "true" ]; then
    echo "ERROR: container '$CONTAINER_NAME' is not managed by EdgeSentinel." >&2
    echo "Refusing to modify or replace it." >&2
    exit 1
  fi

  configured_image="$(docker_cmd inspect \
    --format '{{.Config.Image}}' \
    "$CONTAINER_NAME")"
  if [ "$configured_image" != "$CONTAINER_IMAGE" ]; then
    echo "ERROR: managed container image does not match." >&2
    echo "Expected: $CONTAINER_IMAGE" >&2
    echo "Actual:   $configured_image" >&2
    exit 1
  fi

  network_mode="$(docker_cmd inspect \
    --format '{{.HostConfig.NetworkMode}}' \
    "$CONTAINER_NAME")"
  if [ "$network_mode" != "host" ]; then
    echo "ERROR: managed container is not using host networking." >&2
    exit 1
  fi

  mounted_project="$(docker_cmd inspect \
    --format '{{range .Mounts}}{{if eq .Destination "/workspace/edgesentinel"}}{{.Source}}{{end}}{{end}}' \
    "$CONTAINER_NAME")"
  if [ "$mounted_project" != "$PROJECT_DIR" ]; then
    echo "ERROR: managed container uses a different project mount." >&2
    echo "Expected: $PROJECT_DIR" >&2
    echo "Actual:   $mounted_project" >&2
    exit 1
  fi
}

create_container() {
  if [ ! -c /dev/video0 ]; then
    echo "ERROR: /dev/video0 is not available on the Jetson host." >&2
    exit 1
  fi
  if [ ! -d "$INFERENCE_DIR/data" ]; then
    echo "ERROR: jetson-inference data directory does not exist:" >&2
    echo "  $INFERENCE_DIR/data" >&2
    exit 1
  fi
  if ! docker_cmd image inspect "$CONTAINER_IMAGE" >/dev/null 2>&1; then
    echo "ERROR: required local image is missing: $CONTAINER_IMAGE" >&2
    exit 1
  fi

  prepare_model_file

  run_args=(
    run
    -d
    --name "$CONTAINER_NAME"
    --label "$MANAGED_LABEL=true"
    --init
    --runtime nvidia
    --network host
    --device /dev/video0
    --volume "$INFERENCE_DIR/data:/jetson-inference/data"
    --volume "$PROJECT_DIR:/workspace/edgesentinel"
    --volume "/etc/nv_tegra_release:/etc/nv_tegra_release:ro"
    --volume "$MODEL_FILE:/tmp/nv_jetson_model:ro"
    --workdir /workspace/edgesentinel
  )
  if [ -e /tmp/argus_socket ]; then
    run_args+=(--volume /tmp/argus_socket:/tmp/argus_socket)
  fi
  if [ -f /etc/enctune.conf ]; then
    run_args+=(--volume /etc/enctune.conf:/etc/enctune.conf:ro)
  fi

  docker_cmd "${run_args[@]}" \
    "$CONTAINER_IMAGE" \
    sleep infinity >/dev/null
}

ensure_container() {
  if container_exists; then
    validate_managed_container
    if ! container_running; then
      prepare_model_file
      docker_cmd start "$CONTAINER_NAME" >/dev/null
    fi
  else
    create_container
  fi

  if ! docker_cmd exec "$CONTAINER_NAME" \
    test -c /dev/video0; then
    echo "ERROR: /dev/video0 is not available inside the container." >&2
    exit 1
  fi
}

start_service() {
  ensure_container
  echo "Create a temporary Dashboard configuration token."
  echo "Use at least 16 ASCII characters; input is hidden."
  IFS= read -r -s -p "Zone administrator token: " ADMIN_TOKEN
  echo
  if [ "${#ADMIN_TOKEN}" -lt 16 ]; then
    unset ADMIN_TOKEN
    echo "ERROR: token must contain at least 16 characters." >&2
    exit 1
  fi

  printf '%s\n' "$ADMIN_TOKEN" |
    docker_cmd exec -i "$CONTAINER_NAME" \
      python3 -m apps.service_manager start --token-stdin
  unset ADMIN_TOKEN
  echo "Detached container: $CONTAINER_NAME"
}

start_deepseek_service() {
  ensure_container
  echo "Start a temporary read-only DeepSeek runtime."
  echo "The API key is hidden and is not written to disk."
  IFS= read -r -s -p "DeepSeek API Key: " MODEL_API_KEY
  echo
  if [ "${#MODEL_API_KEY}" -lt 16 ]; then
    unset MODEL_API_KEY
    echo "ERROR: DeepSeek API key must contain at least 16 characters." >&2
    exit 1
  fi

  printf '%s\n' "$MODEL_API_KEY" |
    docker_cmd exec -i "$CONTAINER_NAME" \
      python3 -m apps.service_manager start \
        --read-only \
        --deepseek-key-stdin
  unset MODEL_API_KEY
  echo "Detached container: $CONTAINER_NAME"
  echo "Model mode: temporary DeepSeek (memory only)"
}

boot_start_service() {
  ensure_container
  docker_cmd exec "$CONTAINER_NAME" \
    python3 -m apps.service_manager start --read-only
  echo "Detached container: $CONTAINER_NAME"
  echo "Boot mode: read-only zone configuration"
}

stop_service() {
  if ! container_exists; then
    echo "EdgeSentinel managed container does not exist."
    return
  fi
  validate_managed_container
  if container_running; then
    docker_cmd exec "$CONTAINER_NAME" \
      bash scripts/edgesentinel_service.sh stop
    docker_cmd stop --time 10 "$CONTAINER_NAME" >/dev/null
  fi
  echo "EdgeSentinel runtime and container stopped."
}

show_status() {
  if ! container_exists; then
    echo "Container status: NOT_CREATED"
    return
  fi
  validate_managed_container
  if ! container_running; then
    echo "Container status: STOPPED"
    return
  fi
  echo "Container status: RUNNING"
  echo "Container name: $CONTAINER_NAME"
  echo "Container image: $CONTAINER_IMAGE"
  docker_cmd exec "$CONTAINER_NAME" \
    bash scripts/edgesentinel_service.sh status
}

show_logs() {
  if ! container_exists; then
    echo "ERROR: managed container does not exist." >&2
    exit 1
  fi
  validate_managed_container
  if ! container_running; then
    echo "ERROR: managed container is stopped." >&2
    exit 1
  fi
  docker_cmd exec "$CONTAINER_NAME" \
    bash scripts/edgesentinel_service.sh logs 80
}

open_shell() {
  if ! container_exists; then
    echo "ERROR: managed container does not exist." >&2
    exit 1
  fi
  validate_managed_container
  if ! container_running; then
    echo "ERROR: managed container is stopped." >&2
    exit 1
  fi
  docker_cmd exec -it "$CONTAINER_NAME" \
    bash -lc "cd /workspace/edgesentinel && exec bash"
}

if [ "$#" -ne 1 ]; then
  show_help
  exit 1
fi

case "$1" in
  start|start-deepseek|boot-start|stop|status|logs|shell)
    ;;
  -h|--help|help)
    show_help
    exit 0
    ;;
  *)
    show_help
    exit 1
    ;;
esac

if [ -f /.dockerenv ]; then
  echo "ERROR: this command must run on the Jetson host, not inside Docker." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed on this host." >&2
  exit 1
fi

sudo -v

case "$1" in
  start)
    start_service
    ;;
  start-deepseek)
    start_deepseek_service
    ;;
  boot-start)
    boot_start_service
    ;;
  stop)
    stop_service
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  shell)
    open_shell
    ;;
esac
