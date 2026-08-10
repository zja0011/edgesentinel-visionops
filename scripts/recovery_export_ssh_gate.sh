#!/usr/bin/env bash
set -euo pipefail

export PATH=/usr/bin:/bin
export LC_ALL=C
umask 077

readonly export_directory="/home/nvidia/edgesentinel-recovery-exports/encrypted"
readonly original_command="${SSH_ORIGINAL_COMMAND:-}"

deny() {
    echo "restricted recovery export command denied" >&2
    exit 126
}

case "$original_command" in
    list)
        find "$export_directory" -maxdepth 1 -type f \
            -name 'dr_*.esdr.json' -printf '%f\n' | sort
        ;;
    read\ *)
        name="${original_command#read }"
        if [[ ! "$name" =~ ^dr_[0-9a-f]{32}\.esdr(\.json)?$ ]]; then
            deny
        fi
        path="$export_directory/$name"
        if [[ ! -f "$path" || -L "$path" ]]; then
            deny
        fi
        exec base64 -w 0 -- "$path"
        ;;
    *)
        deny
        ;;
esac
