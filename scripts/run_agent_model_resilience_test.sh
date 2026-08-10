#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

export PYTHONIOENCODING=utf-8

echo "Checking bounded model retry, circuit breaking, and fallback..."
python3 -m unittest \
  tests.unit.test_model_gateway \
  tests.unit.test_model_runtime \
  tests.unit.test_agent_model_resilience \
  tests.unit.test_agent_execution_control \
  tests.unit.test_agent_trace_query \
  -q

echo
echo "Agent Model Resilience acceptance summary:"
echo "Retry classification: HTTP 408/429/5xx and network failures"
echo "Retry maximum attempts: 2"
echo "Retry backoff: bounded"
echo "Circuit failure threshold: 3 logical requests"
echo "Circuit cooldown: 60 seconds"
echo "Half-open probes: one"
echo "Offline fallback: enabled"
echo "Tool calls replayed by retry: False"
echo "Fallback response: explicitly labeled"
echo "Checkpoint: resilience counters retained and validated"
echo "Trace: MODEL_RESILIENCE, error body and model content absent"
echo "Agent Model Resilience smoke test passed."
