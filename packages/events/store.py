"""Append-only JSON Lines event persistence."""

import json
import os


class JsonlEventStore(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        parent = os.path.dirname(self.path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        self._file = open(self.path, "a", encoding="utf-8")

    def append(self, event):
        line = json.dumps(
            event.to_dict(), ensure_ascii=False, separators=(",", ":")
        )
        self._file.write(line + "\n")
        self._file.flush()

    def close(self):
        if not self._file.closed:
            self._file.close()
