"""Append-only JSONL task tracing for the Agent Loop."""

import json
import os
import threading


class JsonlTraceRecorder(object):
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
            with open(self.path, "a", encoding="utf-8") as trace_file:
                trace_file.write(line + "\n")
