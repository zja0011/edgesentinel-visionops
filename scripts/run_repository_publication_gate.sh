#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
echo "Checking the fail-closed GitHub publication boundary..."
python3 -m unittest \
  tests.unit.test_repository_publication \
  tests.unit.test_github_repository_assets \
  -q
python3 -m apps.repository_publication_gate
echo "Repository Publication Gate passed."
