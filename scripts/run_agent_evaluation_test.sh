#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

export PYTHONIOENCODING=utf-8

echo "Running the isolated Agent Harness evaluation..."
python3 -m apps.run_agent_evaluation \
  --dataset "$PROJECT_DIR/evals/agent-routing-v1.json" \
  --output-directory "$PROJECT_DIR/data/evaluations"
