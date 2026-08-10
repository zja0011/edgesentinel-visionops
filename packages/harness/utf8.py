"""UTF-8 helpers for old Python runtimes with non-UTF-8 locales."""

import json
import os
import sys
import tempfile
import time


def normalize_cli_text(value):
    """Recover UTF-8 argv bytes decoded with surrogateescape."""
    value = str(value)
    try:
        return value.encode(
            sys.getfilesystemencoding() or "utf-8",
            "surrogateescape",
        ).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def print_json_utf8(payload):
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    output_buffer = getattr(sys.stdout, "buffer", None)
    if output_buffer is not None:
        output_buffer.write(rendered.encode("utf-8"))
        output_buffer.flush()
    else:
        sys.stdout.write(rendered)


def write_json_atomic(path, payload):
    path = os.path.abspath(path)
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".json-",
        suffix=".tmp",
        dir=parent,
    )
    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                payload,
                output_file,
                ensure_ascii=False,
                indent=2,
            )
            output_file.write("\n")
        for attempt in range(10):
            try:
                os.replace(temporary_path, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.01)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
