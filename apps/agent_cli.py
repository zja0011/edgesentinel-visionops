"""Run one bounded offline Agent Harness task."""

import argparse
import os
import sys

from packages.harness.agent_loop import AgentLoop, AgentResumeError
from packages.harness.checkpoint import JsonTaskCheckpointStore
from packages.harness.context import ContextEngine
from packages.harness.default_tools import build_default_registry
from packages.harness.hooks import build_default_hook_dispatcher
from packages.harness.model_runtime import (
    SwitchableModel,
    build_model_from_environment,
)
from packages.harness.skills import SkillRegistry
from packages.harness.trace import JsonlTraceRecorder
from packages.harness.tool_router import ToolSchemaRouter
from packages.harness.utf8 import (
    normalize_cli_text,
    print_json_utf8,
    write_json_atomic,
)


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run one EdgeSentinel Agent Loop task."
    )
    task_source = parser.add_mutually_exclusive_group(
        required=True
    )
    task_source.add_argument("--message")
    task_source.add_argument("--resume-task-id")
    parser.add_argument(
        "--database",
        default=os.path.join(
            PROJECT_DIR,
            "data",
            "events",
            "edgesentinel.db",
        ),
    )
    parser.add_argument(
        "--state",
        default=os.path.join(
            PROJECT_DIR,
            "data",
            "state",
            "current-vision.json",
        ),
    )
    parser.add_argument(
        "--audit-output",
        default=os.path.join(
            PROJECT_DIR,
            "data",
            "harness",
            "tool-calls.jsonl",
        ),
    )
    parser.add_argument(
        "--trace-output",
        default=os.path.join(
            PROJECT_DIR,
            "data",
            "harness",
            "agent-trace.jsonl",
        ),
    )
    parser.add_argument(
        "--checkpoint-dir",
        default=os.path.join(
            PROJECT_DIR,
            "data",
            "harness",
            "checkpoints",
        ),
    )
    parser.add_argument("--output", default="")
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--pause-after-step", type=int)
    parser.add_argument(
        "--confirm-pending-tool",
        action="store_true",
        help=(
            "confirm exactly the pending tool stored in the "
            "resumed task checkpoint"
        ),
    )
    return parser


def main():
    args = build_parser().parse_args()
    registry = build_default_registry(
        PROJECT_DIR,
        args.database,
        audit_path=args.audit_output,
        state_path=args.state,
    )
    skill_registry = SkillRegistry.load(
        os.path.join(PROJECT_DIR, "skills")
    )
    skill_registry.validate_tools(registry.schemas())
    context_engine = ContextEngine(
        database_path=args.database,
        state_path=args.state,
        include_tool_descriptions=False,
    )
    trace_recorder = JsonlTraceRecorder(args.trace_output)
    hook_dispatcher = build_default_hook_dispatcher(
        audit_recorder=JsonlTraceRecorder(
            os.path.join(
                os.path.dirname(args.trace_output),
                "agent-hooks.jsonl",
            )
        ),
        trace_recorder=trace_recorder,
    )
    configured_model = build_model_from_environment()
    agent = AgentLoop(
        model=SwitchableModel(configured_model),
        context_engine=context_engine,
        tool_registry=registry,
        trace_recorder=trace_recorder,
        checkpoint_store=JsonTaskCheckpointStore(
            args.checkpoint_dir
        ),
        skill_registry=skill_registry,
        hook_dispatcher=hook_dispatcher,
        tool_router=ToolSchemaRouter(max_tools=6),
        max_steps=args.max_steps,
    )
    if args.resume_task_id:
        if args.pause_after_step is not None:
            raise SystemExit(
                "--pause-after-step cannot be used with "
                "--resume-task-id"
            )
        try:
            result = agent.resume(
                args.resume_task_id,
                confirmation_granted=args.confirm_pending_tool,
            )
        except AgentResumeError as error:
            print("ERROR: {}".format(error), file=sys.stderr)
            return 2
    else:
        if args.confirm_pending_tool:
            raise SystemExit(
                "--confirm-pending-tool requires "
                "--resume-task-id"
            )
        result = agent.run(
            normalize_cli_text(args.message),
            pause_after_step=args.pause_after_step,
        )
    if args.output:
        write_json_atomic(args.output, result)
    print_json_utf8(result)
    return (
        0
        if result["status"] in (
            "COMPLETED",
            "PAUSED",
            "AWAITING_CONFIRMATION",
        )
        else 2
    )


if __name__ == "__main__":
    sys.exit(main())
