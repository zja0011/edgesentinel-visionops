#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/dist/releases"

cd "$PROJECT_DIR"
if [ "$#" -gt 1 ]; then
  echo "Usage: bash scripts/build_release_artifacts.sh [VERSION]" >&2
  exit 2
fi

if [ "$#" -eq 1 ]; then
  python3 -m apps.release_provenance build \
    --version "$1" \
    --output-dir "$OUTPUT_DIR"
else
  python3 -m apps.release_provenance build \
    --output-dir "$OUTPUT_DIR"
fi

echo
echo "Release artifacts prepared under: dist/releases"
echo "No credential, runtime data, evidence, or recovery backup was included."
echo "Next: bash scripts/check_release_integrity.sh"
