"""context_graph.atomic_io — shared atomic-write primitives for
context-graph state files (design doc section 5, "Which writes are
append-only vs. atomic-replace"). Every atomic-replace file (config.json,
index.json, context.md, map.md marker writes) goes through write_atomic /
write_json_atomic; every append-only file (judgments.jsonl) goes through
append_line_atomic. No caller writes bytes to a state file directly.
"""
import json
import os
import tempfile


def write_atomic(path, data_bytes):
    """Write data_bytes to path via temp-file-in-the-same-directory +
    fsync + os.replace. Atomic on POSIX and Windows; on any failure the
    temp file is removed and the original target (if any) is left
    untouched — never a partially-written target."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    _fsync_dir(directory)


def _fsync_dir(directory):
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass  # platform doesn't support directory fsync
    finally:
        os.close(dir_fd)


def write_json_atomic(path, obj):
    data = (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_atomic(path, data)


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def append_line_atomic(path, line_obj):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    line = json.dumps(line_obj, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
