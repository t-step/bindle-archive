"""context_graph.lock — single-writer project lock (design doc section 15,
widened to project scope by #228).

Shared by init/config mutation (#191), confirm (#184), and apply (#185), and
— since #228 — by the architecture surface. `propose` never acquires this
lock. Acquisition is O_CREAT|O_EXCL|O_WRONLY (atomic create-exclusive);
contention retries with bounded exponential backoff; only `config break-lock`
removes an existing lock file directly, never through normal acquisition.

SCOPE (#228, PT28): the lock lives at `<project_dir>/.bindle/.lock`, the
parent of both `.bindle/context` and `.bindle/architecture`, so a context
apply and an architecture apply are serialized rather than interleaved. The
foundation design froze it at `.bindle/context/.lock`; #228 supersedes that
line deliberately. The module still lives in `context_graph` because #228
scoped this as an in-place edit to lock.py — `architecture` imports it the
same way it already imports `config.project_dir`.

The lock file sits under the hidden `.bindle/` root rather than beside
`profile.md`, so it never appears in the user's (possibly Obsidian-synced)
notes tree. That is why the path is not simply `<project_dir>/.lock`.
"""
import json
import os
import socket
import threading
import time

from . import atomic_io

VALID_OPERATIONS = (
    # context-graph surface (#140/#191/#184/#185)
    "init", "config", "confirm", "apply",
    # architecture surface (#228); distinct strings so a lock file's owner
    # metadata says which surface holds it.
    "arch_init", "arch_config", "arch_confirm", "arch_apply",
)

BINDLE_SUBDIR = ".bindle"

LOCK_FILENAME = ".lock"

# Pre-#228 lock location. Read and reported so a lock file orphaned by a
# crashed older run is visible rather than silently stranded; never removed
# except by the explicit `config break-lock --force` path.
LEGACY_LOCK_SUBDIR = os.path.join(".bindle", "context")

_BACKOFF_START = 0.1
_BACKOFF_CAP = 2.0
_CONTENTION_TIMEOUT = 10.0

# Re-entrancy bookkeeping: path -> depth, THREAD-LOCAL by design. An
# architecture orchestrator that holds the project lock and calls into
# context_graph.apply (which acquires it again) must not deadlock against
# itself; a genuinely concurrent thread or process must still contend. A
# process-global registry would satisfy the first and break the second.
_local = threading.local()


def _held_depths():
    depths = getattr(_local, "depths", None)
    if depths is None:
        depths = {}
        _local.depths = depths
    return depths


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


def lock_path(project_dir):
    """The one project-scoped lock, covering every surface under
    `<project_dir>/.bindle/`."""
    return os.path.join(project_dir, BINDLE_SUBDIR, LOCK_FILENAME)


def legacy_lock_path(project_dir):
    """Where a pre-#228 run would have left its lock file."""
    return os.path.join(project_dir, LEGACY_LOCK_SUBDIR, LOCK_FILENAME)


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

    def __init__(self, project_dir, operation,
                 contention_timeout=_CONTENTION_TIMEOUT,
                 backoff_start=_BACKOFF_START, backoff_cap=_BACKOFF_CAP):
        if operation not in VALID_OPERATIONS:
            raise ValueError("invalid lock operation %r" % (operation,))
        self.path = lock_path(project_dir)
        self.operation = operation
        self._contention_timeout = contention_timeout
        self._backoff_start = backoff_start
        self._backoff_cap = backoff_cap
        self._held = False

    def __enter__(self):
        depths = _held_depths()
        if self.path in depths:
            # This thread already holds this project's lock. Nesting is a
            # no-op: the owner metadata stays that of the outermost holder,
            # and only the outermost release removes the file.
            depths[self.path] += 1
            self._held = True
            return self
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        deadline = time.monotonic() + self._contention_timeout
        delay = self._backoff_start
        while True:
            if _try_acquire(self.path, self.operation):
                depths[self.path] = 1
                self._held = True
                return self
            if time.monotonic() >= deadline:
                raise LockContention(self.path, read_owner(self.path))
            time.sleep(min(delay, self._backoff_cap))
            delay = min(delay * 2, self._backoff_cap)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._held:
            depths = _held_depths()
            depth = depths.get(self.path, 1)
            if depth > 1:
                depths[self.path] = depth - 1
            else:
                depths.pop(self.path, None)
                try:
                    os.unlink(self.path)
                except FileNotFoundError:
                    pass
            self._held = False
        return False


def _break(path):
    owner = read_owner(path)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    return owner


def break_lock(project_dir):
    """Remove an existing lock file directly (no acquisition). Returns the
    owner metadata that was present, or None if there was no lock. Does not
    touch a legacy lock — see break_legacy_lock."""
    return _break(lock_path(project_dir))


def break_legacy_lock(project_dir):
    """Remove a pre-#228 `.bindle/context/.lock` left behind by a crashed
    older run. Separate from break_lock so the two are reported
    independently; nothing else ever removes it."""
    return _break(legacy_lock_path(project_dir))
