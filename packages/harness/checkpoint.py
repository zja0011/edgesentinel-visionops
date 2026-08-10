"""Atomic per-task checkpoint persistence for the Agent Loop."""

import json
import os
import re

from packages.harness.utf8 import write_json_atomic


TASK_ID_PATTERN = re.compile(r"^task_[0-9a-f]{32}$")


class CheckpointNotFound(LookupError):
    pass


def task_result_from_checkpoint(checkpoint):
    """Return the bounded public task contract from an internal checkpoint."""
    result = {
        "schema_version": checkpoint.get("schema_version", "1.0"),
        "task_id": checkpoint["task_id"],
        "status": checkpoint["status"],
        "model": checkpoint["model"],
        "started_at": checkpoint["started_at"],
        "completed_at": checkpoint.get("completed_at"),
        "steps": int(checkpoint.get("step", 0)),
        "answer": checkpoint.get("answer") or "",
        "tool_results": list(checkpoint.get("tool_results") or []),
    }
    optional_fields = {
        "error": "error",
        "pending_confirmation": "pending_confirmation",
        "active_skill": "skill",
        "execution": "execution",
        "tool_route": "tool_route",
        "model_resilience": "model_resilience",
    }
    for checkpoint_field, result_field in optional_fields.items():
        if checkpoint.get(checkpoint_field):
            result[result_field] = checkpoint[checkpoint_field]
    return result


class JsonTaskCheckpointStore(object):
    def __init__(self, directory):
        self.directory = os.path.abspath(directory)

    def save(self, checkpoint):
        checkpoint = dict(checkpoint)
        task_id = self._validate_task_id(
            checkpoint.get("task_id")
        )
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)
        path = self._path(task_id)
        write_json_atomic(path, checkpoint)
        return path

    def load(self, task_id):
        task_id = self._validate_task_id(task_id)
        path = self._path(task_id)
        if not os.path.isfile(path):
            raise CheckpointNotFound(
                "task checkpoint does not exist"
            )
        try:
            with open(path, "r", encoding="utf-8") as input_file:
                checkpoint = json.load(input_file)
        except (OSError, ValueError) as error:
            raise CheckpointNotFound(
                "task checkpoint is unavailable"
            ) from error
        if checkpoint.get("task_id") != task_id:
            raise CheckpointNotFound(
                "task checkpoint id does not match"
            )
        return checkpoint

    def _path(self, task_id):
        return os.path.join(self.directory, task_id + ".json")

    @staticmethod
    def _validate_task_id(task_id):
        task_id = str(task_id or "")
        if not TASK_ID_PATTERN.match(task_id):
            raise CheckpointNotFound("invalid task id")
        return task_id
