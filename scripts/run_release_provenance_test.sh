#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
TEMPORARY_DIR="$(mktemp -d)"

cleanup() {
  if [ -n "$TEMPORARY_DIR" ] && [ -d "$TEMPORARY_DIR" ]; then
    rm -rf -- "$TEMPORARY_DIR"
  fi
}
trap cleanup EXIT

cd "$PROJECT_DIR"
echo "Checking deterministic release provenance and CycloneDX SBOM..."
python3 -m unittest tests.unit.test_release_provenance -q
python3 -m apps.release_provenance build \
  --output-dir "$TEMPORARY_DIR" \
  > "$TEMPORARY_DIR/build-result.json"

MANIFEST="$(python3 - "$TEMPORARY_DIR" <<'PY'
import json
import os
import sys

root = os.path.abspath(sys.argv[1])
with open(
    os.path.join(root, "build-result.json"),
    "r",
    encoding="utf-8",
) as input_file:
    payload = json.load(input_file)
relative = str(payload["manifest"]).replace("/", os.sep)
candidate = os.path.abspath(os.path.join(root, relative))
if os.path.commonpath([candidate, root]) != root:
    raise SystemExit("manifest path escaped the acceptance directory")
print(candidate)
PY
)"

python3 -m apps.release_provenance verify \
  --manifest "$MANIFEST" \
  > "$TEMPORARY_DIR/verify-result.json"

python3 - \
  "$TEMPORARY_DIR/build-result.json" \
  "$TEMPORARY_DIR/verify-result.json" <<'PY'
import json
import re
import sys

with open(sys.argv[1], "r", encoding="utf-8") as input_file:
    created = json.load(input_file)
with open(sys.argv[2], "r", encoding="utf-8") as input_file:
    verified = json.load(input_file)
assert created["status"] == "CREATED"
assert re.match(r"^esv_[A-Za-z0-9_]+_[0-9a-f]{16}$", created["release_id"])
assert re.match(r"^[0-9a-f]{64}$", created["manifest_sha256"])
assert re.match(r"^[0-9a-f]{64}$", created["sbom_sha256"])
assert created["credentials_included"] is False
assert created["absolute_paths_included"] is False
assert verified["status"] == "PASS"
assert verified["source_integrity"] == "MATCH"
assert verified["sbom_verified"] is True
assert verified["issue_count"] == 0
print()
print("Release Provenance acceptance summary:")
print("Status:", verified["status"])
print("Release ID:", created["release_id"])
print("Version:", created["version"])
print("Files:", created["file_count"])
print("Source bytes:", created["total_bytes"])
print("Manifest SHA-256:", created["manifest_sha256"])
print("SBOM: CycloneDX 1.7 VERIFIED")
print("Source integrity:", verified["source_integrity"])
print("Credentials included:", created["credentials_included"])
print("Absolute paths included:", created["absolute_paths_included"])
PY

echo "Release Provenance smoke test passed."
