#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/dist/releases"
POINTER="$OUTPUT_DIR/current-release.json"

cd "$PROJECT_DIR"
if [ "$#" -gt 1 ]; then
  echo "Usage: bash scripts/check_release_integrity.sh [MANIFEST]" >&2
  exit 2
fi

if [ "$#" -eq 1 ]; then
  MANIFEST="$1"
else
  if [ ! -f "$POINTER" ] || [ -L "$POINTER" ]; then
    echo "ERROR: build the release artifacts first." >&2
    exit 1
  fi
  MANIFEST_RELATIVE="$(python3 - "$POINTER" <<'PY'
import json
import re
import sys

with open(sys.argv[1], "r", encoding="utf-8") as input_file:
    payload = json.load(input_file)
relative = str(payload.get("manifest") or "").replace("\\", "/")
if (
    not re.match(
        r"^esv_[A-Za-z0-9_]+_[0-9a-f]{16}/release-manifest\.json$",
        relative,
    )
    or ".." in relative.split("/")
):
    raise SystemExit("current release pointer is invalid")
print(relative)
PY
)"
  MANIFEST="$OUTPUT_DIR/$MANIFEST_RELATIVE"
fi

python3 -m apps.release_provenance verify --manifest "$MANIFEST"
