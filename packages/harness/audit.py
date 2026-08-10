"""Append-only JSONL audit records for Harness tool calls."""

import json
import os
import threading


class JsonlToolAuditRecorder(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()

    def append(self, record):
        parent = os.path.dirname(self.path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        line = json.dumps(
            record,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as audit_file:
                audit_file.write(line + "\n")
