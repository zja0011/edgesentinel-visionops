#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

DURATION_SECONDS="${1:-60}"
INTERVAL_SECONDS="${2:-5}"
STAMP="$(
  python3 -c "
import datetime
zone = datetime.timezone(datetime.timedelta(hours=8))
print(datetime.datetime.now(zone).strftime('%Y%m%dT%H%M%S+0800'))
"
)"
OUTPUT="$PROJECT_DIR/data/benchmarks/runtime-benchmark-$STAMP.json"

echo "Running a bounded local EdgeSentinel runtime benchmark..."
echo "Duration: $DURATION_SECONDS seconds"
echo "Interval: $INTERVAL_SECONDS seconds"
echo "Keep the camera and managed service running."

python3 -m apps.runtime_benchmark \
  --duration-seconds "$DURATION_SECONDS" \
  --interval-seconds "$INTERVAL_SECONDS" \
  --output "$OUTPUT"
