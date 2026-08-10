#!/usr/bin/env bash
set -euo pipefail

readonly manager="/usr/local/libexec/edgesentinel-recovery-capacity-manager"
keep_count="${1:-4}"
maximum_bytes="${2:-536870912}"

if [[ -f /.dockerenv ]]; then
    echo "ERROR: run the recovery capacity preview on the Jetson host." >&2
    exit 1
fi
if ! sudo test -f "$manager" || sudo test -L "$manager" ||
    [[ "$(sudo stat -c '%U:%G %a' "$manager")" != "root:root 755" ]]; then
    echo "ERROR: reinstall the root-owned scheduled recovery assets first." >&2
    exit 1
fi
exec sudo "$manager" preview \
    --keep-count "$keep_count" \
    --maximum-bytes "$maximum_bytes"
