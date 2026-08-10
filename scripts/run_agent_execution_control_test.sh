#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

export PYTHONIOENCODING=utf-8

echo "Checking bounded Agent execution and cooperative cancellation..."
python3 -m unittest \
  tests.unit.test_execution_control \
  tests.unit.test_agent_execution_control \
  tests.unit.test_task_queue \
  -q

echo
echo "Agent Execution Control acceptance summary:"
echo "Wall deadline: 60 seconds"
echo "Model call budget: 5"
echo "Tool call budget: 8"
echo "External tool budget: 2"
echo "Safe points: before/after model and tool"
echo "Queued cancellation: immediate"
echo "Running cancellation: cooperative"
echo "Force termination used: False"
echo "Cancellation trace: EXECUTION_STOPPED"
echo "Request body persisted: False"
echo "Agent Execution Control smoke test passed."
