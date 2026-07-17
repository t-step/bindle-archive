"""context_graph.lock — single-writer project lock (design doc section 15).

Shared by init/config mutation (#191), confirm (#184), and apply (#185).
`propose` never acquires this lock. Acquisition is O_CREAT|O_EXCL|O_WRONLY
(atomic create-exclusive); contention retries with bounded exponential
backoff; only `config break-lock` removes an existing lock file directly,
never through normal acquisition.
"""
import json
import os
import socket
import time

from . import atomic_io

VALID_OPERATIONS = ("init", "config", "confirm", "apply")

LOCK_FILENAME = ".lock"

_BACKOFF_START = 0.1
_BACKOFF_CAP = 2.0
_CONTENTION_TIMEOUT = 10.0


class LockContention(Exception):
    """Raised when the lock could not be acquired within the bounded
    contention window. `.owner` carries the current owner metadata dict
    (or None if it could not be read)."""

    def __init__(self, path, owner):
        super().__init__(
            "could not acquire lock %r: owner=%r" % (path, owner)
        )
        self.path = path
        self.owner = owner


def lock_path(context_dir):
    return os.path.join(context_dir, LOCK_FILENAME)


def read_owner(path):
    """Read a present lock file's owner metadata. Returns None if the lock
    file does not exist. Returns {"raw": <text>} if it exists but is not
    valid JSON (a torn or foreign write) rather than raising."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text}


def pid_is_running(pid):
    """Best-effort local-host liveness check. Only meaningful once the
    caller has confirmed the owner's hostname matches the local host."""
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _try_acquire(path, operation):
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    owner = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "operation": operation,
        "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(owner, sort_keys=True))
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        # If metadata write fails, remove the just-created lock file to avoid
        # orphaning it, then re-raise the original exception.
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    # Fsync the containing directory for durability (following atomic_io pattern).
    atomic_io._fsync_dir(os.path.dirname(path) or ".")
    return True


class ProjectLock:
    """Context manager: acquire on __enter__ (bounded retry), release
    (delete the lock file) on __exit__ including on exception, per the
    design's try/finally requirement."""

    def __init__(self, context_dir, operation,
                 contention_timeout=_CONTENTION_TIMEOUT,
                 backoff_start=_BACKOFF_START, backoff_cap=_BACKOFF_CAP):
        if operation not in VALID_OPERATIONS:
            raise ValueError("invalid lock operation %r" % (operation,))
        self.path = lock_path(context_dir)
        self.operation = operation
        self._contention_timeout = contention_timeout
        self._backoff_start = backoff_start
        self._backoff_cap = backoff_cap
        self._held = False

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        deadline = time.monotonic() + self._contention_timeout
        delay = self._backoff_start
        while True:
            if _try_acquire(self.path, self.operation):
                self._held = True
                return self
            if time.monotonic() >= deadline:
                raise LockContention(self.path, read_owner(self.path))
            time.sleep(min(delay, self._backoff_cap))
            delay = min(delay * 2, self._backoff_cap)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._held:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            self._held = False
        return False


def break_lock(context_dir):
    """Remove an existing lock file directly (no acquisition). Returns the
    owner metadata that was present, or None if there was no lock."""
    path = lock_path(context_dir)
    owner = read_owner(path)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    return owner
