#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Checking bounded, confirmation-gated long-term Agent memory..."
python3 -m unittest tests.unit.test_long_term_memory -q

python3 - <<'PY'
import os
import tempfile

from packages.harness.default_tools import build_default_registry
from packages.harness.long_term_memory import LongTermMemoryStore
from packages.harness.registry import ToolInvocationError


with tempfile.TemporaryDirectory() as directory:
    store = LongTermMemoryStore(os.path.join(directory, "memory"))
    registry = build_default_registry(
        directory,
        os.path.join(directory, "events.db"),
        long_term_memory_store=store,
    )
    arguments = {
        "kind": "PREFERENCE",
        "key": "preferred language",
        "value": "Chinese",
    }
    denied = None
    try:
        registry.invoke("memory.remember", arguments)
    except ToolInvocationError as error:
        denied = error.code
    created = registry.invoke(
        "memory.remember",
        arguments,
        confirmation_granted=True,
    )["result"]
    found = registry.invoke(
        "memory.search",
        {"query": "language", "limit": 5},
    )["result"]
    forgotten = registry.invoke(
        "memory.forget",
        {"memory_id": created["memory_id"]},
        confirmation_granted=True,
    )["result"]
    schemas = {item["name"]: item for item in registry.schemas()}
    assert denied == "POLICY_DENIED"
    assert found["count"] == 1
    assert forgotten["status"] == "FORGOTTEN"
    assert schemas["memory.search"]["annotations"]["riskLevel"] == "L0"
    assert schemas["memory.remember"]["annotations"]["riskLevel"] == "L1"
    assert schemas["memory.forget"]["annotations"]["riskLevel"] == "L1"
    assert len(
        [
            item
            for item in schemas.values()
            if item["annotations"].get("riskLevel") == "L0"
            and item["annotations"].get("readOnlyHint")
        ]
    ) == 25

print()
print("Agent Long-Term Memory acceptance summary:")
print("Store: bounded atomic local JSON")
print("Kinds: FACT, PREFERENCE")
print("Search: memory.search L0 read-only")
print("Remember: memory.remember L1 confirmation required")
print("Forget: memory.forget L1 confirmation required")
print("Unconfirmed write: POLICY_DENIED")
print("Revision and provenance: retained")
print("Credentials and evidence paths: rejected")
print("Raw tool results stored: False")
print("Images stored: False")
print("MCP read-only tools: 25")
print("Agent Long-Term Memory smoke test passed.")
PY
