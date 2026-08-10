#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

export PYTHONIOENCODING=utf-8

echo "Checking deterministic bounded Agent tool routing..."
python3 -m unittest \
  tests.unit.test_tool_router \
  tests.unit.test_agent_tool_routing \
  tests.unit.test_model_gateway \
  tests.unit.test_harness_context \
  tests.unit.test_agent_trace_query \
  -q

echo
echo "Agent Tool Routing acceptance summary:"
echo "Router: deterministic local pre-model selection"
echo "Catalog fallback: disabled"
echo "Maximum visible tools: 6"
echo "General no-match request: zero tool schemas"
echo "L1/L2 tools: explicit intent or pinned Skill only"
echo "Skill tools: version-pinned and bounded"
echo "Hidden registered tool: TOOL_ROUTE_NOT_ALLOWED"
echo "Unknown tool: registry default deny"
echo "Context descriptions: not duplicated in API model context"
echo "Checkpoint: route retained and revalidated"
echo "Trace: TOOL_ROUTE, model content absent"
echo "Agent Tool Routing smoke test passed."
