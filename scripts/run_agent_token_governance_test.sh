#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

export PYTHONIOENCODING=utf-8

echo "Checking Agent token budgets and optional cost estimates..."
python3 -m unittest \
  tests.unit.test_execution_control \
  tests.unit.test_agent_execution_control \
  tests.unit.test_model_gateway \
  tests.unit.test_task_queue \
  tests.unit.test_agent_trace_query \
  -q

echo
echo "Agent Token Governance acceptance summary:"
echo "Provider usage: normalized and bounded"
echo "Task token budget: 16384"
echo "Missing provider usage: explicit, never treated as measured zero"
echo "Cost estimate: optional operator rate card"
echo "Unconfigured cost: unavailable, never fabricated"
echo "Token stop: MODEL_TOKEN_BUDGET_EXCEEDED"
echo "Cost stop: MODEL_COST_BUDGET_EXCEEDED"
echo "Trace: MODEL_USAGE, model content absent"
echo "Checkpoint: cumulative usage retained"
echo "Agent Token Governance smoke test passed."
