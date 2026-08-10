#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gate_source="$project_dir/scripts/recovery_export_ssh_gate.sh"
gate_target="/usr/local/libexec/edgesentinel-recovery-export-gate"
login_user="nvidia"
login_home="/home/nvidia"
authorized_keys="$login_home/.ssh/authorized_keys"
marker="edgesentinel-recovery-sync"
action="${1:-status}"
public_key_path="${2:-}"

require_gate_source() {
    bash -n "$gate_source"
    grep -Fq 'SSH_ORIGINAL_COMMAND' "$gate_source"
}

install_access() {
    if [[ -z "$public_key_path" || ! -f "$public_key_path" || -L "$public_key_path" ]]; then
        echo "Usage: bash scripts/install_recovery_sync_access.sh install PUBLIC_KEY_FILE" >&2
        exit 2
    fi
    require_gate_source
    public_key="$(tr -d '\r\n' < "$public_key_path")"
    if [[ ! "$public_key" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+\ edgesentinel-recovery-sync$ ]]; then
        echo "The recovery sync public key is invalid" >&2
        exit 2
    fi
    key_blob="$(printf '%s\n' "$public_key" | awk '{print $2}')"
    sudo install -d -o root -g root -m 0755 /usr/local/libexec
    sudo install -o root -g root -m 0755 "$gate_source" "$gate_target"
    sudo install -d -o "$login_user" -g "$login_user" -m 0700 "$login_home/.ssh"
    temporary="$(mktemp)"
    trap 'rm -f -- "$temporary"' EXIT
    if sudo test -f "$authorized_keys"; then
        sudo awk -v blob="$key_blob" -v gate="$gate_target" \
            'index($0, blob) == 0 && index($0, gate) == 0 { print }' \
            "$authorized_keys" > "$temporary"
    fi
    printf 'restrict,command="%s" ssh-ed25519 %s %s\n' \
        "$gate_target" "$key_blob" "$marker" >> "$temporary"
    sudo install -o "$login_user" -g "$login_user" -m 0600 \
        "$temporary" "$authorized_keys"
    echo "Restricted recovery synchronization access installed."
    echo "Login: $login_user"
    echo "Gate: $gate_target (root:root 0755)"
    echo "Shell access: denied"
    echo "Writes and forwarding: denied"
}

show_status() {
    installed=false
    if sudo test -f "$authorized_keys" && \
        sudo grep -Fq "command=\"$gate_target\"" "$authorized_keys" && \
        sudo test -x "$gate_target"; then
        installed=true
    fi
    echo "Restricted recovery synchronization access: $installed"
    if [[ "$installed" == true ]]; then
        gate_mode="$(sudo stat -c '%U:%G %a' "$gate_target")"
        key_mode="$(sudo stat -c '%U:%G %a' "$authorized_keys")"
        echo "Gate owner/mode: $gate_mode"
        echo "Authorized keys owner/mode: $key_mode"
        echo "Forced command: configured"
        echo "Port, agent, X11 and PTY forwarding: restricted"
    fi
}

remove_access() {
    echo "Type REMOVE_RECOVERY_SYNC_ACCESS to continue:"
    read -r confirmation
    if [[ "$confirmation" != "REMOVE_RECOVERY_SYNC_ACCESS" ]]; then
        echo "Recovery synchronization access removal cancelled." >&2
        exit 2
    fi
    temporary="$(mktemp)"
    trap 'rm -f -- "$temporary"' EXIT
    if sudo test -f "$authorized_keys"; then
        sudo awk -v gate="$gate_target" \
            'index($0, gate) == 0 { print }' "$authorized_keys" > "$temporary"
        sudo install -o "$login_user" -g "$login_user" -m 0600 \
            "$temporary" "$authorized_keys"
    fi
    sudo rm -f -- "$gate_target"
    echo "Restricted recovery synchronization access removed."
}

case "$action" in
    install) install_access ;;
    status) show_status ;;
    remove) remove_access ;;
    *)
        echo "Usage: bash scripts/install_recovery_sync_access.sh {install PUBLIC_KEY_FILE|status|remove}" >&2
        exit 2
        ;;
esac
