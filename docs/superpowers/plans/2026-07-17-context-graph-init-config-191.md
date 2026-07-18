# #191 — context-graph project identity and repository bindings

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `bin/context-graph.py`'s initialization and configuration
boundary — `init`, `config status`, `config validate`, `config
add-repository`, `config update-repository`, `config remove-repository`,
`config set-default`, `config break-lock` — per issue #191 and
`docs/design/2026-07-17-context-graph-foundation.md` §4/§5/§6/§15.

**Architecture:** Three new library modules under `bin/context_graph/`
(`atomic_io.py` for shared atomic-write primitives, `lock.py` for the
project-scoped single-writer lock, `config.py` for identity/binding domain
logic) plus one thin CLI entry point (`bin/context-graph.py`, argparse only —
no independent logic, matching the existing `bin/context-evidence.py` /
`bin/map-entry-id.py` adapter pattern). `config.py` reuses
`context_graph.validation.validate_config` (already shipped by #180) for
project-id/alias/binding-id/default semantic checks and adds only the
config-file-specific checks that module cannot do (schema-version, unknown
fields, local-Git-origin disagreement) as a separate function, composed
together in `config.all_findings`.

**Tech Stack:** Python 3 standard library only (no new dependencies — #191's
own acceptance criteria). `unittest` for module tests (existing convention:
`python3 -m unittest discover -s bin/context_graph/tests -t .`, already run
by `bin/test-context-graph-schema.sh` and picks up new `test_*.py` files
automatically — no changes needed there). A new `bin/test-context-graph-cli.sh`
for CLI-process-level integration checks that unittest cannot express
(subprocess invocation, cross-directory execution, concurrent processes).

## Global Constraints

- Stdlib-only; no `pip install` anywhere in this plan (#191 acceptance
  criteria).
- Every atomic-replace write goes through `atomic_io.write_atomic` /
  `write_json_atomic` — no caller writes `config.json` bytes directly
  (design §5 "Which writes are append-only vs. atomic-replace").
- Every mutating config operation (`init`, `config add/update/remove-
  repository`, `config set-default`) acquires `context_graph.lock.ProjectLock`
  for its full read-modify-write and releases on any exception (design §15
  "Release ... inside the same try/finally"). `config validate`, `config
  status` never lock (design §4). `config break-lock` never acquires through
  the normal path — it removes `.lock` directly (design §15).
- Lock owner `operation` field is one of exactly `"init"`, `"config"`,
  `"confirm"`, `"apply"` (design §15) — `init` uses `"init"`, all four
  `config <verb>` mutations use `"config"`. `confirm`/`apply` are reserved
  for #184/#185, never produced here.
- Malformed or conflicting **existing** config is never silently mutated —
  every mutating function loads and validates existing config first and
  raises `ConfigInvalidError` (not a repair) if it fails validation (design
  "no command may silently replace a valid existing ID" / "Recovery must
  never silently select among competing identities").
- `project_id`/`binding_id` allocation is always `secrets.token_hex(16)`
  formatted through `context_graph.ids.format_project_id` /
  `format_repository_binding_id` — never re-derived by hand (matches
  `bin/map-entry-id.py`'s `allocate_id` precedent).
- File layout: `<notes-home>/projects/<project-slug>/.bindle/context/
  config.json` and `.../.bindle/context/.lock` (design §5, resolving the
  #182/#191 body ambiguity in favor of the notes-home project directory,
  never the Git checkout).
- **Scope boundary (explicit, non-obvious):** the design's §4 full command
  surface also lists `preview`, `candidates`, `propose`, `confirm`, `apply`,
  bare `validate`, and bare `status` — those belong to #183/#184/#185/#186
  and are **not** implemented by this plan. Only the `init` and `config *`
  verbs (including `break-lock`, which design §4 places under the `#191`
  heading even though #191's own issue body text omits it) are in scope.
- **Scope boundary (explicit, non-obvious):** `context_graph.validation.
  validate_config`'s `FINDING_CODES` enum is owned by #180 (shipped,
  cross-checked by `test_schema_conformance.py`'s "every finding code is
  classified" test). This plan does **not** add new codes to that enum —
  config-file-specific checks (schema version, unknown fields, malformed
  binding-id shape, local-Git-origin disagreement) live in a new
  `context_graph.config.structural_findings` / `local_origin_findings`
  pair with their own `E_CONFIG_*` codes, composed with `validate_config`'s
  output by `context_graph.config.all_findings` rather than folding into
  the shared bundle-validation module. This avoids the exact "schema-only
  amendment" blast-radius trap the #180 design review already caught once.

## Fixture coverage map (#191 issue body, "Fixture and pressure-test
requirements", items 1–29)

| # | Requirement | Covered by |
|---|---|---|
| 1 | init with no repository | Task 3, `test_config.py::test_init_project_creates_config_with_no_repositories` |
| 2 | project ID matches `project:<32-hex>` | Task 3, `test_config.py::test_allocate_project_id_matches_pattern` |
| 3 | repeat init preserves bytes, zero writes | Task 3, `test_config.py::test_init_project_rerun_is_byte_identical_zero_writes` |
| 4 | failed init leaves no partial config | Task 3, `test_config.py::test_init_project_failure_leaves_no_partial_file` |
| 5 | two concurrent inits persist exactly one ID | Task 3, `test_config.py::test_init_project_concurrent_threads_persist_one_id` |
| 6 | slug change preserves project ID | Task 3, `test_config.py::test_project_slug_is_independent_of_project_id` |
| 7 | notes-dir movement preserves ID after path resolution | Task 3, `test_config.py::test_init_project_at_new_notes_home_path_preserves_existing_config` |
| 8 | add one repository binding | Task 4, `test_config.py::test_add_repository_creates_binding` |
| 9 | add multiple repository bindings | Task 4, `test_config.py::test_add_multiple_repositories` |
| 10 | select exactly one default | Task 4, `test_config.py::test_add_repository_with_default_flag` |
| 11 | multiple defaults fail validation | Task 4, `test_config.py::test_two_defaults_rejected_by_validation` |
| 12 | no default leaves bare refs unresolved | Task 4 (documented — bare-reference *resolution* is #181/#183 territory; #191 only guarantees `default_for_bare_references` can be absent from every binding without failing validation), `test_config.py::test_zero_defaults_is_valid` |
| 13 | repo rename preserves project/binding IDs | Task 4, `test_config.py::test_update_repository_coordinates_preserves_binding_id` |
| 14 | repo transfer preserves IDs when explicitly updated | Task 4, `test_config.py::test_update_repository_coordinates_preserves_binding_id` (same path — transfer and rename are both a `coordinates` update) |
| 15 | local checkout movement preserves IDs | Task 4, `test_config.py::test_update_repository_local_checkout_path_preserves_binding_id` |
| 16 | local-origin disagreement reported, not adopted | Task 5, `test_config.py::test_local_origin_findings_reports_disagreement` |
| 17 | removing a repository doesn't change project identity | Task 4, `test_config.py::test_remove_repository_preserves_project_id` |
| 18 | same doc path in two repos -> distinct binding-qualified identities | Task 5, `test_config.py::test_document_ids_differ_by_binding` (uses `context_graph.ids.format_document_repository_id`, already shipped by #181 — this task only demonstrates config-produced binding IDs feed it correctly) |
| 19 | duplicate binding IDs are conflicts | Task 4, `test_config.py::test_duplicate_binding_id_rejected_by_validation` (via `validate_config`, already shipped) |
| 20 | duplicate aliases are conflicts | Task 4, `test_config.py::test_duplicate_alias_rejected_on_add` |
| 21 | malformed project ID reported, not repaired | Task 3, `test_config.py::test_init_on_existing_malformed_project_id_raises_without_writing` |
| 22 | repository-shaped project ID rejected | Task 3, `test_config.py::test_structural_and_shared_findings_reject_repo_shaped_project_id` |
| 23 | existing index with different project ID is a conflict | Out of scope for #191 (`index.json` is #185-owned); noted here per "no silent gap" — will be #185's fixture, not re-derived here. |
| 24 | invocation outside a Git repo succeeds with explicit paths | Task 9, `bin/test-context-graph-cli.sh` (`init` run from a `mktemp -d` outside any repo) |
| 25 | no command requires a skill/session | True by construction (plain argparse CLI, no skill import) — asserted in Task 9's CLI script as a static grep (`! grep -q "skills/" bin/context-graph.py`) |
| 26 | validation performs zero writes | Task 5, `test_config.py::test_config_validate_never_writes` |
| 27 | config mutations remain under the notes home | Task 3/4, `test_config.py::test_config_path_is_under_notes_home` |
| 28 | lock contention / stale-lock recovery follow policy | Task 2, `test_lock.py` (contention + `break_lock`) |
| 29 | `make check` and `make test` pass | Task 9 |

---

### Task 1: Atomic write primitives

**Files:**
- Create: `bin/context_graph/atomic_io.py`
- Test: `bin/context_graph/tests/test_atomic_io.py`

**Interfaces:**
- Consumes: nothing (foundation module).
- Produces: `write_atomic(path: str, data_bytes: bytes) -> None`,
  `write_json_atomic(path: str, obj: dict) -> None`, `read_json(path: str) ->
  dict` (raises `FileNotFoundError` if absent, `ValueError`/`json.
  JSONDecodeError` if malformed), `append_line_atomic(path: str, line_obj:
  dict) -> None`. Used by Tasks 3–5.

- [ ] **Step 1: Write the failing tests**

```python
# bin/context_graph/tests/test_atomic_io.py
import glob
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import atomic_io


class TestAtomicIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _path(self, *parts):
        return os.path.join(self.tmp, *parts)

    def test_write_json_atomic_creates_file_with_content(self):
        path = self._path("a", "b", "config.json")
        atomic_io.write_json_atomic(path, {"x": 1})
        self.assertEqual(atomic_io.read_json(path), {"x": 1})

    def test_write_json_atomic_creates_parent_directories(self):
        path = self._path("deep", "nested", "dir", "config.json")
        atomic_io.write_json_atomic(path, {"y": 2})
        self.assertTrue(os.path.isfile(path))

    def test_write_json_atomic_overwrites_and_leaves_no_temp_files(self):
        path = self._path("config.json")
        atomic_io.write_json_atomic(path, {"v": 1})
        atomic_io.write_json_atomic(path, {"v": 2})
        self.assertEqual(atomic_io.read_json(path), {"v": 2})
        leftovers = glob.glob(os.path.join(self.tmp, ".tmp-*"))
        self.assertEqual(leftovers, [])

    def test_read_json_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            atomic_io.read_json(self._path("nope.json"))

    def test_read_json_malformed_raises_value_error(self):
        path = self._path("bad.json")
        os.makedirs(self.tmp, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(ValueError):
            atomic_io.read_json(path)

    def test_append_line_atomic_appends_without_truncating(self):
        path = self._path("judgments.jsonl")
        atomic_io.append_line_atomic(path, {"a": 1})
        atomic_io.append_line_atomic(path, {"a": 2})
        with open(path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f.read().splitlines()]
        self.assertEqual(lines, [{"a": 1}, {"a": 2}])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from the repo root): `python3 -m unittest bin.context_graph.tests.test_atomic_io -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'context_graph.atomic_io'` (or `ImportError`).

- [ ] **Step 3: Write the implementation**

```python
# bin/context_graph/atomic_io.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest bin.context_graph.tests.test_atomic_io -v`
Expected: `OK` (6 tests).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/atomic_io.py bin/context_graph/tests/test_atomic_io.py
git commit -m "feat(#191): add shared atomic-write primitives"
```

---

### Task 2: Single-writer project lock

**Files:**
- Create: `bin/context_graph/lock.py`
- Test: `bin/context_graph/tests/test_lock.py`

**Interfaces:**
- Consumes: nothing (foundation module).
- Produces: `VALID_OPERATIONS = ("init", "config", "confirm", "apply")`,
  `lock_path(context_dir: str) -> str`, `read_owner(path: str) -> dict |
  None`, `pid_is_running(pid: int) -> bool | None`, `class ProjectLock
  (context_dir: str, operation: str, contention_timeout=10.0,
  backoff_start=0.1, backoff_cap=2.0)` (context manager), `class
  LockContention(Exception)` with `.path` and `.owner`, `break_lock
  (context_dir: str) -> dict | None`. Used by Task 3 (`init`) and Task 4
  (`config add/update/remove-repository`, `set-default`) and Task 8's CLI
  `break-lock`.

- [ ] **Step 1: Write the failing tests**

```python
# bin/context_graph/tests/test_lock.py
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import lock


class TestProjectLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_acquire_creates_lock_file_with_owner_metadata(self):
        with lock.ProjectLock(self.tmp, "init") as held:
            owner = lock.read_owner(held.path)
            self.assertEqual(owner["operation"], "init")
            self.assertEqual(owner["pid"], os.getpid())
            self.assertIn("hostname", owner)
            self.assertIn("acquired_at", owner)

    def test_release_removes_lock_file(self):
        with lock.ProjectLock(self.tmp, "config") as held:
            path = held.path
        self.assertFalse(os.path.exists(path))

    def test_lock_released_on_exception(self):
        path = lock.lock_path(self.tmp)
        with self.assertRaises(RuntimeError):
            with lock.ProjectLock(self.tmp, "config"):
                raise RuntimeError("boom")
        self.assertFalse(os.path.exists(path))

    def test_invalid_operation_rejected(self):
        with self.assertRaises(ValueError):
            with lock.ProjectLock(self.tmp, "bogus"):
                pass

    def test_contention_raises_after_timeout(self):
        path = lock.lock_path(self.tmp)
        os.makedirs(self.tmp, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"pid": 999999, "hostname": "elsewhere", '
                     '"operation": "init", "acquired_at": "x"}')
        with self.assertRaises(lock.LockContention) as ctx:
            with lock.ProjectLock(self.tmp, "config",
                                   contention_timeout=0.3, backoff_start=0.05,
                                   backoff_cap=0.1):
                pass
        self.assertEqual(ctx.exception.owner["hostname"], "elsewhere")

    def test_second_acquirer_succeeds_after_first_releases(self):
        order = []

        def first():
            with lock.ProjectLock(self.tmp, "init",
                                   contention_timeout=2.0, backoff_start=0.02):
                order.append("first-acquired")

        first()
        with lock.ProjectLock(self.tmp, "config",
                               contention_timeout=2.0, backoff_start=0.02):
            order.append("second-acquired")
        self.assertEqual(order, ["first-acquired", "second-acquired"])

    def test_break_lock_removes_existing_lock_and_returns_owner(self):
        with lock.ProjectLock(self.tmp, "init") as held:
            path = held.path
            owner_while_held = lock.read_owner(path)
        # re-create manually to simulate a stale lock left by a crash
        with open(path, "w", encoding="utf-8") as f:
            import json
            f.write(json.dumps(owner_while_held))
        returned = lock.break_lock(self.tmp)
        self.assertEqual(returned["operation"], "init")
        self.assertFalse(os.path.exists(path))

    def test_break_lock_on_missing_lock_returns_none(self):
        self.assertIsNone(lock.break_lock(self.tmp))

    def test_pid_is_running_true_for_self(self):
        self.assertTrue(lock.pid_is_running(os.getpid()))

    def test_pid_is_running_false_for_bogus_pid(self):
        # a pid extremely unlikely to exist
        self.assertFalse(lock.pid_is_running(2**30))

    def test_concurrent_threads_only_one_holds_lock_at_a_time(self):
        holder = {"count": 0, "max_concurrent": 0}
        lock_guard = threading.Lock()

        def worker():
            with lock.ProjectLock(self.tmp, "config",
                                   contention_timeout=5.0, backoff_start=0.01):
                with lock_guard:
                    holder["count"] += 1
                    holder["max_concurrent"] = max(
                        holder["max_concurrent"], holder["count"])
                with lock_guard:
                    holder["count"] -= 1

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(holder["max_concurrent"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest bin.context_graph.tests.test_lock -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'context_graph.lock'`.

- [ ] **Step 3: Write the implementation**

```python
# bin/context_graph/lock.py
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
    if operation not in VALID_OPERATIONS:
        raise ValueError("invalid lock operation %r" % (operation,))
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
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(owner, sort_keys=True))
        f.flush()
        os.fsync(f.fileno())
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest bin.context_graph.tests.test_lock -v`
Expected: `OK` (10 tests). Note: `test_contention_raises_after_timeout` takes
~0.3s wall-clock (uses the overridable `contention_timeout` param, not the
real 10s default) — if it hangs near 10s, the override isn't wired through.

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/lock.py bin/context_graph/tests/test_lock.py
git commit -m "feat(#191): add single-writer project lock"
```

---

### Task 3: Project identity — allocation, init lifecycle

**Files:**
- Create: `bin/context_graph/config.py`
- Test: `bin/context_graph/tests/test_config.py`

**Interfaces:**
- Consumes: `atomic_io.write_json_atomic`, `atomic_io.read_json` (Task 1);
  `lock.ProjectLock`, `lock.LockContention` (Task 2); `context_graph.ids.
  format_project_id`, `format_repository_binding_id`, `parse_typed_id`,
  `MalformedIdError` (shipped); `context_graph.validation.validate_config`
  (shipped).
- Produces: `SCHEMA_VERSION = 1`, `project_dir(notes_home, project_slug) ->
  str`, `context_dir(notes_home, project_slug) -> str`, `config_path
  (notes_home, project_slug) -> str`, `allocate_project_id() -> str`,
  `allocate_binding_id() -> str`, `load_config(path) -> dict | None`,
  `class ConfigError(Exception)` with `.findings`, `class
  ConfigMissingError(ConfigError)`, `class ConfigInvalidError(ConfigError)`,
  `init_project(notes_home, project_slug, display_name=None) -> (dict,
  bool)`. Consumed by Task 4 (binding CRUD, same module), Task 5
  (structural/local-origin checks, same module), Task 6 (CLI `init`/`config
  status`/`config validate`).

- [ ] **Step 1: Write the failing tests**

```python
# bin/context_graph/tests/test_config.py
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import config
from context_graph import lock


class TestProjectIdentity(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()

    def test_allocate_project_id_matches_pattern(self):
        pid = config.allocate_project_id()
        self.assertRegex(pid, r"^project:[0-9a-f]{32}$")

    def test_init_project_creates_config_with_no_repositories(self):
        cfg, created = config.init_project(self.notes_home, "myproj")
        self.assertTrue(created)
        self.assertEqual(cfg["repositories"], [])
        self.assertEqual(cfg["project_slug"], "myproj")
        self.assertRegex(cfg["project_id"], r"^project:[0-9a-f]{32}$")

    def test_init_project_rerun_is_byte_identical_zero_writes(self):
        config.init_project(self.notes_home, "myproj")
        path = config.config_path(self.notes_home, "myproj")
        before = open(path, "rb").read()
        before_mtime = os.stat(path).st_mtime_ns
        cfg2, created2 = config.init_project(self.notes_home, "myproj")
        after = open(path, "rb").read()
        after_mtime = os.stat(path).st_mtime_ns
        self.assertFalse(created2)
        self.assertEqual(before, after)
        self.assertEqual(before_mtime, after_mtime)

    def test_init_project_failure_leaves_no_partial_file(self):
        path = config.config_path(self.notes_home, "myproj")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        with self.assertRaises(config.ConfigInvalidError):
            config.init_project(self.notes_home, "myproj")
        # the malformed original is untouched, not replaced or emptied
        with open(path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "{not valid json")

    def test_init_project_concurrent_threads_persist_one_id(self):
        results = []
        errors = []

        def worker():
            try:
                cfg, created = config.init_project(self.notes_home, "raceproj")
                results.append((cfg["project_id"], created))
            except Exception as e:  # noqa: BLE001 - captured for assertion
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 4)
        self.assertEqual(len({r[0] for r in results}), 1)
        self.assertEqual([r[1] for r in results].count(True), 1)

    def test_project_slug_is_independent_of_project_id(self):
        cfg, _ = config.init_project(self.notes_home, "old-slug")
        original_id = cfg["project_id"]
        # simulate a slug rename: same notes_home, config lives at the
        # project-slug directory, so re-reading under the OLD slug still
        # returns the same id (identity is not derived from the slug path).
        reread = config.load_config(config.config_path(self.notes_home, "old-slug"))
        self.assertEqual(reread["project_id"], original_id)

    def test_init_project_at_new_notes_home_path_preserves_existing_config(self):
        cfg, _ = config.init_project(self.notes_home, "movable")
        original_id = cfg["project_id"]
        # "notes-directory movement" = re-resolving the same tree at a new
        # path (e.g. after a mv); config.py never depends on notes_home's
        # own identity, only on what's on disk at the resolved path.
        moved = tempfile.mkdtemp()
        os.rename(self.notes_home, os.path.join(moved, "moved-tree"))
        moved_home = os.path.join(moved, "moved-tree")
        reread, created = config.init_project(moved_home, "movable")
        self.assertFalse(created)
        self.assertEqual(reread["project_id"], original_id)

    def test_init_on_existing_malformed_project_id_raises_without_writing(self):
        path = config.config_path(self.notes_home, "badid")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bad_cfg = {"schema_version": 1, "project_id": "project:not-hex",
                   "project_slug": "badid", "repositories": []}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bad_cfg, f)
        before = open(path, "r", encoding="utf-8").read()
        with self.assertRaises(config.ConfigInvalidError) as ctx:
            config.init_project(self.notes_home, "badid")
        codes = {f["code"] for f in ctx.exception.findings}
        self.assertIn("E_CONFIG_MALFORMED_PROJECT_ID", codes)
        after = open(path, "r", encoding="utf-8").read()
        self.assertEqual(before, after)

    def test_structural_and_shared_findings_reject_repo_shaped_project_id(self):
        cfg = {"schema_version": 1, "project_id": "project:thomas-estep/bindle",
               "project_slug": "x", "repositories": []}
        findings = config.all_findings(cfg)
        codes = {f["code"] for f in findings}
        self.assertIn("E_CONFIG_PROJECT_ID_REPO_SHAPED", codes)

    def test_config_path_is_under_notes_home(self):
        path = config.config_path(self.notes_home, "myproj")
        self.assertTrue(path.startswith(self.notes_home + os.sep))
        self.assertIn(os.path.join(".bindle", "context"), path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest bin.context_graph.tests.test_config -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named
'context_graph.config'`.

- [ ] **Step 3: Write the implementation**

```python
# bin/context_graph/config.py
"""context_graph.config — project identity and repository-binding
configuration (issue #191, epic #140). Owns config.json's authoritative
lifecycle: allocation, atomic persistence, and repository-binding CRUD.

Read-only semantic checks (project-id shape, duplicate alias/binding-id,
multiple-default) are context_graph.validation.validate_config (shipped by
#180); this module adds config-file-specific structural and local-origin
checks that validate_config cannot do because they need filesystem/git
access outside its pure-object contract. context_graph.config.all_findings
composes both, deliberately NOT adding new codes to validation.FINDING_CODES
(that enum is #180-owned and cross-checked by test_schema_conformance.py).

Every mutating function acquires context_graph.lock.ProjectLock for the
duration of its read-modify-write and releases it (including on exception)
before returning or raising. An existing config that fails validation is
never mutated further — mutation always raises ConfigInvalidError rather
than repairing or replacing it.
"""
import os
import secrets
import subprocess

from context_graph import atomic_io
from context_graph import ids
from context_graph import lock
from context_graph import validation

SCHEMA_VERSION = 1
CONTEXT_SUBDIR = os.path.join(".bindle", "context")
CONFIG_FILENAME = "config.json"

_KNOWN_TOP_LEVEL_FIELDS = frozenset(
    ["schema_version", "project_id", "project_slug", "display_name", "repositories"]
)
_KNOWN_REPOSITORY_FIELDS = frozenset(
    ["alias", "binding_id", "provider", "coordinates", "local_checkout_path",
     "default_for_bare_references"]
)


def _finding(code, message, **extra):
    d = {"code": code, "message": message}
    d.update(extra)
    return d


class ConfigError(Exception):
    """Base class for config domain errors. `.findings` is always a
    non-empty list of {"code", "message", ...} dicts — the same shape
    context_graph.validation produces, so CLI rendering is uniform."""

    def __init__(self, findings):
        self.findings = findings
        super().__init__("; ".join(f["message"] for f in findings))


class ConfigMissingError(ConfigError):
    def __init__(self, path):
        super().__init__([_finding(
            "E_CONFIG_MISSING", "no configuration found at %r" % (path,))])
        self.path = path


class ConfigInvalidError(ConfigError):
    """Existing or about-to-be-written config fails validation."""


class BindingNotFoundError(ConfigError):
    def __init__(self, binding_id):
        super().__init__([_finding(
            "E_CONFIG_BINDING_NOT_FOUND",
            "no repository binding %r in configuration" % (binding_id,))])
        self.binding_id = binding_id


def project_dir(notes_home, project_slug):
    return os.path.join(notes_home, "projects", project_slug)


def context_dir(notes_home, project_slug):
    return os.path.join(project_dir(notes_home, project_slug), CONTEXT_SUBDIR)


def config_path(notes_home, project_slug):
    return os.path.join(context_dir(notes_home, project_slug), CONFIG_FILENAME)


def allocate_project_id():
    return ids.format_project_id(secrets.token_hex(16))


def allocate_binding_id():
    return ids.format_repository_binding_id(secrets.token_hex(16))


def load_config(path):
    """Return the parsed config dict, or None if no file exists at path.
    Raises ConfigInvalidError (E_CONFIG_UNREADABLE) for a present file that
    is not valid JSON — never silently treated as missing."""
    try:
        return atomic_io.read_json(path)
    except FileNotFoundError:
        return None
    except ValueError as e:
        raise ConfigInvalidError([_finding(
            "E_CONFIG_UNREADABLE", "config at %r is not valid JSON: %s" % (path, e))])


def structural_findings(cfg):
    """Config-file-specific structural checks beyond validate_config's
    semantic checks: unsupported schema_version, unknown top-level/
    repository fields, malformed binding_id shape. Pure, no filesystem
    access."""
    findings = []
    version = cfg.get("schema_version")
    if version != SCHEMA_VERSION:
        findings.append(_finding(
            "E_CONFIG_SCHEMA_VERSION_UNSUPPORTED",
            "unsupported schema_version %r (expected %d)" % (version, SCHEMA_VERSION),
            field="schema_version"))
    for key in cfg:
        if key not in _KNOWN_TOP_LEVEL_FIELDS:
            findings.append(_finding(
                "E_CONFIG_UNKNOWN_FIELD", "unknown top-level field %r" % (key,), field=key))
    for i, repo in enumerate(cfg.get("repositories", [])):
        for key in repo:
            if key not in _KNOWN_REPOSITORY_FIELDS:
                findings.append(_finding(
                    "E_CONFIG_UNKNOWN_FIELD",
                    "unknown repository field %r at index %d" % (key, i),
                    index=i, field=key))
        binding_id = repo.get("binding_id", "")
        try:
            parsed = ids.parse_typed_id(binding_id)
            if parsed["type"] != "repository_binding":
                raise ids.MalformedIdError(binding_id, "not a repository-binding id")
        except ids.MalformedIdError:
            findings.append(_finding(
                "E_CONFIG_MALFORMED_BINDING_ID",
                "malformed binding_id %r at index %d" % (binding_id, i),
                index=i, field="binding_id"))
    return findings


def _coordinates_from_git_url(url):
    """'git@github.com:owner/repo.git' or 'https://github.com/owner/repo.git'
    -> 'owner/repo'. Returns None for a URL shape this cannot parse rather
    than guessing."""
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@"):
        _, _, tail = url.partition(":")
    elif "://" in url:
        _, _, tail = url.partition("://")
        _, _, tail = tail.partition("/")
    else:
        return None
    parts = tail.strip("/").split("/")
    if len(parts) < 2:
        return None
    return "%s/%s" % (parts[-2], parts[-1])


def local_origin_findings(cfg):
    """For each binding with both coordinates and a local_checkout_path
    that exists and is a Git repository, compare its `origin` remote to
    the configured coordinates. A disagreement is reported, never silently
    adopted (issue's Validation section; design fixture 16)."""
    findings = []
    for i, repo in enumerate(cfg.get("repositories", [])):
        coordinates = repo.get("coordinates")
        checkout = repo.get("local_checkout_path")
        if not coordinates or not checkout:
            continue
        if not os.path.isdir(os.path.join(checkout, ".git")):
            continue
        try:
            out = subprocess.run(
                ["git", "-C", checkout, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.returncode != 0:
            continue
        origin_coordinates = _coordinates_from_git_url(out.stdout.strip())
        if origin_coordinates and origin_coordinates != coordinates:
            findings.append(_finding(
                "E_CONFIG_LOCAL_ORIGIN_DISAGREEMENT",
                "local checkout %r origin %r disagrees with configured "
                "coordinates %r at index %d" % (checkout, origin_coordinates,
                                                 coordinates, i),
                index=i, field="local_checkout_path"))
    return findings


def all_findings(cfg):
    """The union `config validate` reports: shared semantic checks
    (validate_config) plus this module's structural and local-origin
    checks."""
    return (validation.validate_config(cfg)
            + structural_findings(cfg)
            + local_origin_findings(cfg))


def init_project(notes_home, project_slug, display_name=None):
    """Idempotent: an existing valid config is preserved byte-for-byte
    (zero writes) and returned with created=False. A missing config is
    created with a freshly allocated project_id. An existing malformed/
    conflicting config raises ConfigInvalidError rather than being
    repaired or replaced. Returns (config_dict, created: bool)."""
    cdir = context_dir(notes_home, project_slug)
    path = os.path.join(cdir, CONFIG_FILENAME)
    with lock.ProjectLock(cdir, "init"):
        existing = load_config(path)
        if existing is not None:
            findings = all_findings(existing)
            if findings:
                raise ConfigInvalidError(findings)
            return existing, False
        cfg = {
            "schema_version": SCHEMA_VERSION,
            "project_id": allocate_project_id(),
            "project_slug": project_slug,
            "repositories": [],
        }
        if display_name:
            cfg["display_name"] = display_name
        findings = all_findings(cfg)
        if findings:
            raise ConfigInvalidError(findings)
        atomic_io.write_json_atomic(path, cfg)
        return cfg, True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest bin.context_graph.tests.test_config -v`
Expected: `OK` (10 tests).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/config.py bin/context_graph/tests/test_config.py
git commit -m "feat(#191): add project identity allocation and init lifecycle"
```

---

### Task 4: Repository binding CRUD

**Files:**
- Modify: `bin/context_graph/config.py` (append)
- Modify: `bin/context_graph/tests/test_config.py` (append)

**Interfaces:**
- Consumes: everything from Task 3 in the same module.
- Produces: `add_repository(notes_home, project_slug, alias, provider,
  coordinates=None, local_checkout_path=None, is_default=False) -> (dict,
  dict)`, `update_repository(notes_home, project_slug, binding_id,
  alias=None, coordinates=None, local_checkout_path=None, default=None) ->
  (dict, dict)`, `remove_repository(notes_home, project_slug, binding_id)
  -> (dict, dict)`, `set_default(notes_home, project_slug, binding_id) ->
  (dict, dict)`. Consumed by Task 6/7 CLI commands.

- [ ] **Step 1: Append the failing tests**

```python
# appended to bin/context_graph/tests/test_config.py

class TestRepositoryBindingCrud(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        config.init_project(self.notes_home, "proj")

    def test_add_repository_creates_binding(self):
        cfg, entry = config.add_repository(
            self.notes_home, "proj", alias="main", provider="github",
            coordinates="thomas-estep/bindle")
        self.assertEqual(len(cfg["repositories"]), 1)
        self.assertRegex(entry["binding_id"], r"^repository-binding:[0-9a-f]{32}$")
        self.assertEqual(entry["alias"], "main")

    def test_add_multiple_repositories(self):
        config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        cfg, _ = config.add_repository(self.notes_home, "proj", alias="b", provider="github")
        self.assertEqual([r["alias"] for r in cfg["repositories"]], ["a", "b"])

    def test_add_repository_with_default_flag(self):
        cfg, entry = config.add_repository(
            self.notes_home, "proj", alias="a", provider="github", is_default=True)
        self.assertTrue(entry["default_for_bare_references"])
        defaults = [r for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(len(defaults), 1)

    def test_second_default_via_add_unsets_first(self):
        config.add_repository(self.notes_home, "proj", alias="a", provider="github", is_default=True)
        cfg, _ = config.add_repository(
            self.notes_home, "proj", alias="b", provider="github", is_default=True)
        defaults = [r["alias"] for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(defaults, ["b"])

    def test_two_defaults_rejected_by_validation(self):
        cfg = {
            "schema_version": 1, "project_id": config.allocate_project_id(),
            "project_slug": "x", "repositories": [
                {"alias": "a", "binding_id": config.allocate_binding_id(),
                 "provider": "github", "default_for_bare_references": True},
                {"alias": "b", "binding_id": config.allocate_binding_id(),
                 "provider": "github", "default_for_bare_references": True},
            ]}
        codes = {f["code"] for f in config.all_findings(cfg)}
        self.assertIn("E_CONFIG_MULTIPLE_DEFAULT", codes)

    def test_zero_defaults_is_valid(self):
        cfg, _ = config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        self.assertEqual(config.all_findings(cfg), [])

    def test_update_repository_coordinates_preserves_binding_id(self):
        _, entry = config.add_repository(
            self.notes_home, "proj", alias="a", provider="github",
            coordinates="old-owner/old-repo")
        binding_id = entry["binding_id"]
        cfg, updated = config.update_repository(
            self.notes_home, "proj", binding_id, coordinates="new-owner/new-repo")
        self.assertEqual(updated["binding_id"], binding_id)
        self.assertEqual(updated["coordinates"], "new-owner/new-repo")

    def test_update_repository_local_checkout_path_preserves_binding_id(self):
        _, entry = config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        binding_id = entry["binding_id"]
        cfg, updated = config.update_repository(
            self.notes_home, "proj", binding_id, local_checkout_path="/new/path")
        self.assertEqual(updated["binding_id"], binding_id)
        self.assertEqual(updated["local_checkout_path"], "/new/path")

    def test_update_repository_default_true_unsets_others(self):
        _, a = config.add_repository(self.notes_home, "proj", alias="a", provider="github",
                                      is_default=True)
        _, b = config.add_repository(self.notes_home, "proj", alias="b", provider="github")
        cfg, _ = config.update_repository(self.notes_home, "proj", b["binding_id"], default=True)
        defaults = [r["alias"] for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(defaults, ["b"])

    def test_update_repository_default_false_unsets_only_that_one(self):
        _, a = config.add_repository(self.notes_home, "proj", alias="a", provider="github",
                                      is_default=True)
        cfg, _ = config.update_repository(self.notes_home, "proj", a["binding_id"], default=False)
        defaults = [r for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(defaults, [])

    def test_update_repository_unknown_binding_raises(self):
        with self.assertRaises(config.BindingNotFoundError):
            config.update_repository(self.notes_home, "proj",
                                      "repository-binding:" + "0" * 32, alias="x")

    def test_remove_repository_preserves_project_id(self):
        before = config.load_config(config.config_path(self.notes_home, "proj"))
        _, entry = config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        cfg, removed = config.remove_repository(self.notes_home, "proj", entry["binding_id"])
        self.assertEqual(cfg["project_id"], before["project_id"])
        self.assertEqual(cfg["repositories"], [])
        self.assertEqual(removed["binding_id"], entry["binding_id"])

    def test_remove_repository_unknown_binding_raises(self):
        with self.assertRaises(config.BindingNotFoundError):
            config.remove_repository(self.notes_home, "proj", "repository-binding:" + "1" * 32)

    def test_set_default_sets_unique_default(self):
        _, a = config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        cfg, _ = config.set_default(self.notes_home, "proj", a["binding_id"])
        defaults = [r["alias"] for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(defaults, ["a"])

    def test_duplicate_alias_rejected_on_add(self):
        config.add_repository(self.notes_home, "proj", alias="dup", provider="github")
        with self.assertRaises(config.ConfigInvalidError) as ctx:
            config.add_repository(self.notes_home, "proj", alias="dup", provider="github")
        codes = {f["code"] for f in ctx.exception.findings}
        self.assertIn("E_CONFIG_DUPLICATE_ALIAS", codes)

    def test_duplicate_binding_id_rejected_by_validation(self):
        dup = config.allocate_binding_id()
        cfg = {
            "schema_version": 1, "project_id": config.allocate_project_id(),
            "project_slug": "x", "repositories": [
                {"alias": "a", "binding_id": dup, "provider": "github"},
                {"alias": "b", "binding_id": dup, "provider": "github"},
            ]}
        codes = {f["code"] for f in config.all_findings(cfg)}
        self.assertIn("E_CONFIG_DUPLICATE_BINDING_ID", codes)

    def test_mutating_on_invalid_existing_config_raises_without_mutating(self):
        path = config.config_path(self.notes_home, "proj")
        cfg = config.load_config(path)
        cfg["project_id"] = "project:not-hex"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        before = open(path, "r", encoding="utf-8").read()
        with self.assertRaises(config.ConfigInvalidError):
            config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        after = open(path, "r", encoding="utf-8").read()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest bin.context_graph.tests.test_config -v`
Expected: FAIL / ERROR — `AttributeError: module 'context_graph.config' has
no attribute 'add_repository'`.

- [ ] **Step 3: Append the implementation**

```python
# appended to bin/context_graph/config.py

def _load_valid_or_raise(notes_home, project_slug, cdir):
    path = os.path.join(cdir, CONFIG_FILENAME)
    cfg = load_config(path)
    if cfg is None:
        raise ConfigMissingError(path)
    findings = all_findings(cfg)
    if findings:
        raise ConfigInvalidError(findings)
    return path, cfg


def _find_repository(repositories, binding_id):
    for i, repo in enumerate(repositories):
        if repo.get("binding_id") == binding_id:
            return i
    return None


def add_repository(notes_home, project_slug, alias, provider, coordinates=None,
                    local_checkout_path=None, is_default=False):
    cdir = context_dir(notes_home, project_slug)
    with lock.ProjectLock(cdir, "config"):
        path, cfg = _load_valid_or_raise(notes_home, project_slug, cdir)
        entry = {"alias": alias, "binding_id": allocate_binding_id(), "provider": provider}
        if coordinates:
            entry["coordinates"] = coordinates
        if local_checkout_path:
            entry["local_checkout_path"] = local_checkout_path
        repositories = list(cfg["repositories"])
        if is_default:
            repositories = [dict(r, default_for_bare_references=False) for r in repositories]
            entry["default_for_bare_references"] = True
        repositories.append(entry)
        new_cfg = dict(cfg, repositories=repositories)
        findings = all_findings(new_cfg)
        if findings:
            raise ConfigInvalidError(findings)
        atomic_io.write_json_atomic(path, new_cfg)
        return new_cfg, entry


def update_repository(notes_home, project_slug, binding_id, alias=None,
                       coordinates=None, local_checkout_path=None, default=None):
    """`default=True` sets this binding default (unsetting any other);
    `default=False` explicitly unsets it; `default=None` leaves it
    unchanged. Only supplied (non-None) fields change."""
    cdir = context_dir(notes_home, project_slug)
    with lock.ProjectLock(cdir, "config"):
        path, cfg = _load_valid_or_raise(notes_home, project_slug, cdir)
        repositories = [dict(r) for r in cfg["repositories"]]
        idx = _find_repository(repositories, binding_id)
        if idx is None:
            raise BindingNotFoundError(binding_id)
        if alias is not None:
            repositories[idx]["alias"] = alias
        if coordinates is not None:
            repositories[idx]["coordinates"] = coordinates
        if local_checkout_path is not None:
            repositories[idx]["local_checkout_path"] = local_checkout_path
        if default is True:
            for i, r in enumerate(repositories):
                r["default_for_bare_references"] = (i == idx)
        elif default is False:
            repositories[idx]["default_for_bare_references"] = False
        new_cfg = dict(cfg, repositories=repositories)
        findings = all_findings(new_cfg)
        if findings:
            raise ConfigInvalidError(findings)
        atomic_io.write_json_atomic(path, new_cfg)
        return new_cfg, repositories[idx]


def remove_repository(notes_home, project_slug, binding_id):
    cdir = context_dir(notes_home, project_slug)
    with lock.ProjectLock(cdir, "config"):
        path, cfg = _load_valid_or_raise(notes_home, project_slug, cdir)
        repositories = list(cfg["repositories"])
        idx = _find_repository(repositories, binding_id)
        if idx is None:
            raise BindingNotFoundError(binding_id)
        removed = repositories.pop(idx)
        new_cfg = dict(cfg, repositories=repositories)
        findings = all_findings(new_cfg)
        if findings:
            raise ConfigInvalidError(findings)
        atomic_io.write_json_atomic(path, new_cfg)
        return new_cfg, removed


def set_default(notes_home, project_slug, binding_id):
    return update_repository(notes_home, project_slug, binding_id, default=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest bin.context_graph.tests.test_config -v`
Expected: `OK` (26 tests total across both test classes).

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/config.py bin/context_graph/tests/test_config.py
git commit -m "feat(#191): add repository binding CRUD"
```

---

### Task 5: Structural checks, local-origin disagreement, evidence-id demo

**Files:**
- Modify: `bin/context_graph/tests/test_config.py` (append) — structural
  checks and `local_origin_findings` are already implemented in Task 3's
  `config.py` (they had to exist for `all_findings` to compile); this task
  is test-only, closing the coverage gap those functions were written
  without dedicated tests for.

**Interfaces:**
- Consumes: `config.structural_findings`, `config.local_origin_findings`,
  `config.all_findings` (Task 3); `context_graph.ids.
  format_document_repository_id` (shipped, #181).
- Produces: nothing new — verification only.

- [ ] **Step 1: Append the failing tests**

```python
# appended to bin/context_graph/tests/test_config.py
from context_graph import ids as _ids


class TestStructuralAndOriginChecks(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()

    def test_unsupported_schema_version_reported(self):
        cfg = {"schema_version": 2, "project_id": config.allocate_project_id(),
               "project_slug": "x", "repositories": []}
        codes = {f["code"] for f in config.structural_findings(cfg)}
        self.assertIn("E_CONFIG_SCHEMA_VERSION_UNSUPPORTED", codes)

    def test_unknown_top_level_field_reported(self):
        cfg = {"schema_version": 1, "project_id": config.allocate_project_id(),
               "project_slug": "x", "repositories": [], "mystery": True}
        codes = {f["code"] for f in config.structural_findings(cfg)}
        self.assertIn("E_CONFIG_UNKNOWN_FIELD", codes)

    def test_malformed_binding_id_reported(self):
        cfg = {"schema_version": 1, "project_id": config.allocate_project_id(),
               "project_slug": "x", "repositories": [
                   {"alias": "a", "binding_id": "repository-binding:not-hex",
                    "provider": "github"}]}
        codes = {f["code"] for f in config.structural_findings(cfg)}
        self.assertIn("E_CONFIG_MALFORMED_BINDING_ID", codes)

    def test_local_origin_findings_reports_disagreement(self):
        import subprocess
        checkout = tempfile.mkdtemp()
        subprocess.run(["git", "-C", checkout, "init", "-q"], check=True)
        subprocess.run(["git", "-C", checkout, "remote", "add", "origin",
                         "git@github.com:actual-owner/actual-repo.git"], check=True)
        cfg = {"schema_version": 1, "project_id": config.allocate_project_id(),
               "project_slug": "x", "repositories": [
                   {"alias": "a", "binding_id": config.allocate_binding_id(),
                    "provider": "github", "coordinates": "configured-owner/configured-repo",
                    "local_checkout_path": checkout}]}
        codes = {f["code"] for f in config.local_origin_findings(cfg)}
        self.assertIn("E_CONFIG_LOCAL_ORIGIN_DISAGREEMENT", codes)

    def test_local_origin_findings_silent_when_agreeing(self):
        import subprocess
        checkout = tempfile.mkdtemp()
        subprocess.run(["git", "-C", checkout, "init", "-q"], check=True)
        subprocess.run(["git", "-C", checkout, "remote", "add", "origin",
                         "git@github.com:same-owner/same-repo.git"], check=True)
        cfg = {"schema_version": 1, "project_id": config.allocate_project_id(),
               "project_slug": "x", "repositories": [
                   {"alias": "a", "binding_id": config.allocate_binding_id(),
                    "provider": "github", "coordinates": "same-owner/same-repo",
                    "local_checkout_path": checkout}]}
        self.assertEqual(config.local_origin_findings(cfg), [])

    def test_local_origin_findings_silent_when_no_local_checkout(self):
        cfg = {"schema_version": 1, "project_id": config.allocate_project_id(),
               "project_slug": "x", "repositories": [
                   {"alias": "a", "binding_id": config.allocate_binding_id(),
                    "provider": "github", "coordinates": "owner/repo"}]}
        self.assertEqual(config.local_origin_findings(cfg), [])

    def test_document_ids_differ_by_binding(self):
        binding_a = config.allocate_binding_id()
        binding_b = config.allocate_binding_id()
        pid = config.allocate_project_id()
        id_a = _ids.format_document_repository_id(pid, binding_a, "README.md")
        id_b = _ids.format_document_repository_id(pid, binding_b, "README.md")
        self.assertNotEqual(id_a, id_b)

    def test_config_validate_never_writes(self):
        config.init_project(self.notes_home, "proj")
        path = config.config_path(self.notes_home, "proj")
        before_mtime = os.stat(path).st_mtime_ns
        cfg = config.load_config(path)
        config.all_findings(cfg)
        after_mtime = os.stat(path).st_mtime_ns
        self.assertEqual(before_mtime, after_mtime)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `python3 -m unittest bin.context_graph.tests.test_config -v`
Expected: this task adds test-only coverage of functions Task 3 already
implemented, so these should already `PASS`. If any fail, the discrepancy
means Task 3's `structural_findings`/`local_origin_findings` need a fix —
treat a failure here as a real bug in Task 3's code, not an expected RED
step.

- [ ] **Step 3: (no implementation step — see Step 1 note)**

- [ ] **Step 4: Run full module suite**

Run: `python3 -m unittest discover -s bin/context_graph/tests -t . -v`
Expected: `OK`, all tests across `test_atomic_io`, `test_lock`,
`test_config`, plus every pre-existing `test_ids`/`test_evidence`/
`test_relationships`/`test_validation`/`test_canonical`/
`test_schema_conformance` module.

- [ ] **Step 5: Commit**

```bash
git add bin/context_graph/tests/test_config.py
git commit -m "test(#191): cover structural and local-origin config checks"
```

---

### Task 6: CLI — `init`, `config status`, `config validate`

**Files:**
- Create: `bin/context-graph.py`

**Interfaces:**
- Consumes: `context_graph.config.*` (Tasks 3–5), `context_graph.lock.*`
  (Task 2).
- Produces: the `init`, `config status`, `config validate` subcommands.
  Extended by Task 7 (repository CRUD subcommands) and Task 8
  (`break-lock`) in the same file.

- [ ] **Step 1: Write the implementation** (no pre-existing test to fail
  against — this is a new CLI entry point; Task 9 adds process-level
  integration tests once all subcommands exist)

```python
#!/usr/bin/env python3
# bin/context-graph.py
"""context-graph.py — CLI entry point for Bindle's context graph (issue
#191, epic #140). Thin per the #180 adapter pattern: argument parsing, JSON
rendering, dispatch into context_graph.config / context_graph.lock. No
independent domain logic lives here.

This issue (#191) implements exactly: `init`, `config status`, `config
validate`, `config add-repository`, `config update-repository`, `config
remove-repository`, `config set-default`, `config break-lock` — the
initialization and configuration boundary frozen by
docs/design/2026-07-17-context-graph-foundation.md section 4. The remaining
verbs shown there (`preview`, `candidates`, `propose`, `confirm`, `apply`,
bare `validate`/`status`) belong to #183/#184/#185/#186 and are not defined
here.
"""
import argparse
import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(__file__))

from context_graph import config
from context_graph import lock


def _emit(obj, fmt):
    if fmt == "text":
        _emit_text(obj)
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))


def _emit_text(obj):
    findings = obj.get("findings")
    if findings:
        for f in findings:
            loc = ""
            if f.get("index") is not None:
                loc += " index=%d" % f["index"]
            if f.get("field"):
                loc += " field=%s" % f["field"]
            print("%s:%s %s" % (f["code"], loc, f["message"]))
    elif findings == []:
        print("ok: no findings")
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))


def _error_findings(code, message):
    return [{"code": code, "message": message}]


def _add_common_args(p):
    p.add_argument("--notes-home", required=True, metavar="PATH")
    p.add_argument("--project", required=True, metavar="SLUG")
    p.add_argument("--format", choices=["json", "text"], default="json")


def cmd_init(args):
    try:
        cfg, created = config.init_project(args.notes_home, args.project, args.display_name)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e))}, args.format)
        return 1
    _emit({"created": created, "config": cfg}, args.format)
    return 0


def cmd_config_status(args):
    path = config.config_path(args.notes_home, args.project)
    cfg = config.load_config(path)
    cdir = config.context_dir(args.notes_home, args.project)
    owner = lock.read_owner(lock.lock_path(cdir))
    owner_live = None
    if isinstance(owner, dict) and "pid" in owner and owner.get("hostname") == socket.gethostname():
        owner_live = lock.pid_is_running(owner["pid"])
    _emit({"config": cfg, "lock": owner, "lock_owner_live": owner_live}, args.format)
    return 0


def cmd_config_validate(args):
    path = config.config_path(args.notes_home, args.project)
    cfg = config.load_config(path)
    if cfg is None:
        findings = _error_findings("E_CONFIG_MISSING", "no configuration found at %r" % (path,))
    else:
        findings = config.all_findings(cfg)
    _emit({"findings": findings}, args.format)
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="allocate project identity, create config.json")
    _add_common_args(p_init)
    p_init.add_argument("--display-name", default=None)
    p_init.set_defaults(func=cmd_init)

    p_config = sub.add_parser("config", help="read or mutate project configuration")
    config_sub = p_config.add_subparsers(dest="config_command", required=True)

    p_status = config_sub.add_parser("status", help="read-only config + lock status")
    _add_common_args(p_status)
    p_status.set_defaults(func=cmd_config_status)

    p_validate = config_sub.add_parser("validate", help="read-only config validation")
    _add_common_args(p_validate)
    p_validate.set_defaults(func=cmd_config_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Manually verify**

```bash
NH=$(mktemp -d)
python3 bin/context-graph.py init --notes-home "$NH" --project demo
python3 bin/context-graph.py config status --notes-home "$NH" --project demo
python3 bin/context-graph.py config validate --notes-home "$NH" --project demo
```

Expected: `init` prints `{"created": true, "config": {...}}`; `status` shows
the same config plus `"lock": null`; `validate` prints `{"findings": []}`
and exits 0 (`echo $?`).

- [ ] **Step 3: Commit**

```bash
git add bin/context-graph.py
git commit -m "feat(#191): add context-graph.py CLI with init and config status/validate"
```

---

### Task 7: CLI — `config add/update/remove-repository`, `set-default`

**Files:**
- Modify: `bin/context-graph.py` (append subcommands)

**Interfaces:**
- Consumes: `context_graph.config.add_repository/update_repository/
  remove_repository/set_default` (Task 4).
- Produces: the four repository-mutation subcommands.

- [ ] **Step 1: Append the implementation**

```python
# in bin/context-graph.py, add these cmd_ functions above main():

def cmd_config_add_repository(args):
    try:
        cfg, entry = config.add_repository(
            args.notes_home, args.project, args.alias, args.provider,
            coordinates=args.coordinates, local_checkout_path=args.local_checkout_path,
            is_default=args.default)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e))}, args.format)
        return 1
    _emit({"repository": entry, "config": cfg}, args.format)
    return 0


def cmd_config_update_repository(args):
    default = True if args.default else (False if args.no_default else None)
    try:
        cfg, entry = config.update_repository(
            args.notes_home, args.project, args.binding_id, alias=args.alias,
            coordinates=args.coordinates, local_checkout_path=args.local_checkout_path,
            default=default)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e))}, args.format)
        return 1
    _emit({"repository": entry, "config": cfg}, args.format)
    return 0


def cmd_config_remove_repository(args):
    try:
        cfg, removed = config.remove_repository(args.notes_home, args.project, args.binding_id)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e))}, args.format)
        return 1
    _emit({"removed": removed, "config": cfg}, args.format)
    return 0


def cmd_config_set_default(args):
    try:
        cfg, entry = config.set_default(args.notes_home, args.project, args.binding_id)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e))}, args.format)
        return 1
    _emit({"repository": entry, "config": cfg}, args.format)
    return 0
```

```python
# in main(), inside config_sub, before "args = parser.parse_args(argv)":

    p_add = config_sub.add_parser("add-repository", help="add one repository binding")
    _add_common_args(p_add)
    p_add.add_argument("--alias", required=True)
    p_add.add_argument("--provider", required=True)
    p_add.add_argument("--coordinates", default=None)
    p_add.add_argument("--local-checkout-path", default=None)
    p_add.add_argument("--default", action="store_true")
    p_add.set_defaults(func=cmd_config_add_repository)

    p_update = config_sub.add_parser("update-repository", help="update one repository binding")
    _add_common_args(p_update)
    p_update.add_argument("--binding-id", required=True)
    p_update.add_argument("--alias", default=None)
    p_update.add_argument("--coordinates", default=None)
    p_update.add_argument("--local-checkout-path", default=None)
    default_group = p_update.add_mutually_exclusive_group()
    default_group.add_argument("--default", action="store_true")
    default_group.add_argument("--no-default", action="store_true")
    p_update.set_defaults(func=cmd_config_update_repository)

    p_remove = config_sub.add_parser("remove-repository", help="remove one repository binding")
    _add_common_args(p_remove)
    p_remove.add_argument("--binding-id", required=True)
    p_remove.set_defaults(func=cmd_config_remove_repository)

    p_default = config_sub.add_parser("set-default", help="set the unique default repository")
    _add_common_args(p_default)
    p_default.add_argument("--binding-id", required=True)
    p_default.set_defaults(func=cmd_config_set_default)
```

- [ ] **Step 2: Manually verify**

```bash
NH=$(mktemp -d)
python3 bin/context-graph.py init --notes-home "$NH" --project demo
python3 bin/context-graph.py config add-repository --notes-home "$NH" --project demo \
  --alias main --provider github --coordinates thomas-estep/bindle --default
BID=$(python3 bin/context-graph.py config status --notes-home "$NH" --project demo \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['config']['repositories'][0]['binding_id'])")
python3 bin/context-graph.py config update-repository --notes-home "$NH" --project demo \
  --binding-id "$BID" --alias renamed
python3 bin/context-graph.py config set-default --notes-home "$NH" --project demo --binding-id "$BID"
python3 bin/context-graph.py config remove-repository --notes-home "$NH" --project demo --binding-id "$BID"
```

Expected: each command exits 0 and prints the updated config; the final
`config status` shows `"repositories": []`.

- [ ] **Step 3: Commit**

```bash
git add bin/context-graph.py
git commit -m "feat(#191): add config repository-binding CLI subcommands"
```

---

### Task 8: CLI — `config break-lock`

**Files:**
- Modify: `bin/context-graph.py` (append)

**Interfaces:**
- Consumes: `context_graph.lock.break_lock` (Task 2).
- Produces: the `config break-lock` subcommand.

- [ ] **Step 1: Append the implementation**

```python
# in bin/context-graph.py, add above main():

def cmd_config_break_lock(args):
    if not args.force:
        _emit({"findings": _error_findings(
            "E_LOCK_BREAK_NOT_CONFIRMED",
            "config break-lock requires --force to confirm")}, args.format)
        return 1
    cdir = config.context_dir(args.notes_home, args.project)
    owner = lock.break_lock(cdir)
    _emit({"removed_owner": owner}, args.format)
    return 0
```

```python
# in main(), inside config_sub, alongside the others:

    p_break = config_sub.add_parser("break-lock", help="remove an existing .lock directly")
    _add_common_args(p_break)
    p_break.add_argument("--force", action="store_true")
    p_break.set_defaults(func=cmd_config_break_lock)
```

- [ ] **Step 2: Manually verify**

```bash
NH=$(mktemp -d)
python3 bin/context-graph.py init --notes-home "$NH" --project demo
touch "$NH/projects/demo/.bindle/context/.lock"
python3 bin/context-graph.py config break-lock --notes-home "$NH" --project demo
echo "exit=$?"   # expect 1, requires --force
python3 bin/context-graph.py config break-lock --notes-home "$NH" --project demo --force
echo "exit=$?"   # expect 0
test -f "$NH/projects/demo/.bindle/context/.lock" && echo STILL_THERE || echo REMOVED
```

Expected: first call exits 1 with `E_LOCK_BREAK_NOT_CONFIRMED`; second with
`--force` exits 0 and prints `REMOVED`.

- [ ] **Step 3: Commit**

```bash
git add bin/context-graph.py
git commit -m "feat(#191): add config break-lock CLI subcommand"
```

---

### Task 9: CLI integration tests, docs amendments, capability inventory, gates

**Files:**
- Create: `bin/test-context-graph-cli.sh`
- Modify: `Makefile` (add the new test to the `test:` target)
- Modify: `docs/notes-home.md` (layout diagram)
- Modify: `docs/session-notes-format.md` (layout diagram, "Stable contract"
  section)
- Modify: `capabilities.json` (one new `type: script` row for
  `bin/context-graph.py`; `not_a_capability` ledger rows for
  `bin/context_graph/atomic_io.py`, `bin/context_graph/lock.py`,
  `bin/context_graph/config.py`, and their three `tests/test_*.py` files —
  `bin/test-context-graph-cli.sh` is auto-excluded, no entry needed)

**Interfaces:**
- Consumes: the finished CLI (Tasks 6–8).
- Produces: nothing new for later tasks — this is the closing task.

- [ ] **Step 1: Write `bin/test-context-graph-cli.sh`**

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2016
#
# test-context-graph-cli.sh — CLI-process-level integration checks for
# bin/context-graph.py (issue #191, epic #140) that unittest cannot express:
# subprocess invocation, cross-directory execution, concurrent processes,
# and end-to-end command sequences. Module-level logic (context_graph.config
# / .lock / .atomic_io) is already exercised by
# `python3 -m unittest discover -s bin/context_graph/tests -t .`, which
# bin/test-context-graph-schema.sh already runs and which auto-discovers
# this task's new test_atomic_io.py / test_lock.py / test_config.py files —
# not repeated here.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
CLI="$REPO_ROOT/bin/context-graph.py"

pass=0
fail=0
check() {
  local desc="$1"
  shift
  if "$@"; then
    printf '  \xe2\x9c\x93 %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  \xe2\x9c\x97 %s\n' "$desc"
    fail=$((fail + 1))
  fi
}

echo "== fixture 24: invocation outside a Git repo with explicit paths =="
OUTSIDE_DIR="$(mktemp -d)"
NH="$(mktemp -d)"
(cd "$OUTSIDE_DIR" && "$PY" "$CLI" init --notes-home "$NH" --project outsiderepo) >/tmp/cg-init.out 2>&1
check "init succeeds from a directory outside any Git repo" test $? -eq 0

echo "== fixture 5: two concurrent init processes persist exactly one ID =="
NH2="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH2" --project racer >/tmp/cg-race-a.json 2>&1 &
PID_A=$!
"$PY" "$CLI" init --notes-home "$NH2" --project racer >/tmp/cg-race-b.json 2>&1 &
PID_B=$!
wait "$PID_A"
wait "$PID_B"
ID_A=$("$PY" -c "import json;print(json.load(open('/tmp/cg-race-a.json'))['config']['project_id'])")
ID_B=$("$PY" -c "import json;print(json.load(open('/tmp/cg-race-b.json'))['config']['project_id'])")
check "concurrent init processes agree on one project_id" bash -c "test '$ID_A' = '$ID_B'"

echo "== fixture 3: repeated init is byte-identical =="
NH3="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH3" --project stable >/dev/null
CFG="$NH3/projects/stable/.bindle/context/config.json"
SUM1=$(shasum -a 256 "$CFG" | awk '{print $1}')
"$PY" "$CLI" init --notes-home "$NH3" --project stable >/dev/null
SUM2=$(shasum -a 256 "$CFG" | awk '{print $1}')
check "repeated init leaves config.json byte-identical" bash -c "test '$SUM1' = '$SUM2'"

echo "== end-to-end command sequence =="
NH4="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH4" --project e2e >/dev/null
check "config validate on a fresh project reports no findings" bash -c \
  "\"$PY\" \"$CLI\" config validate --notes-home \"$NH4\" --project e2e | \"$PY\" -c 'import json,sys; d=json.load(sys.stdin); exit(0 if d[\"findings\"]==[] else 1)'"
"$PY" "$CLI" config add-repository --notes-home "$NH4" --project e2e \
  --alias main --provider github --coordinates thomas-estep/bindle --default >/dev/null
check "config add-repository succeeds" test $? -eq 0
BID=$("$PY" "$CLI" config status --notes-home "$NH4" --project e2e | \
  "$PY" -c "import json,sys; print(json.load(sys.stdin)['config']['repositories'][0]['binding_id'])")
"$PY" "$CLI" config remove-repository --notes-home "$NH4" --project e2e --binding-id "$BID" >/dev/null
check "config remove-repository succeeds" test $? -eq 0

echo "== fixture 25: no command requires a skill or session (static check) =="
check "context-graph.py never imports skill machinery" bash -c \
  "! grep -q 'skills/' '$CLI'"

echo "== fixture 28: lock contention surfaces owner metadata, break-lock clears it =="
NH5="$(mktemp -d)"
"$PY" "$CLI" init --notes-home "$NH5" --project locked >/dev/null
LOCKDIR="$NH5/projects/locked/.bindle/context"
"$PY" -c "import json,os; open(os.path.join('$LOCKDIR','.lock'),'w').write(json.dumps({'pid':999999,'hostname':'nowhere','operation':'init','acquired_at':'x'}))"
"$PY" "$CLI" config break-lock --notes-home "$NH5" --project locked >/dev/null 2>&1
check "break-lock without --force is refused" test $? -ne 0
"$PY" "$CLI" config break-lock --notes-home "$NH5" --project locked --force >/dev/null
check "break-lock --force removes the lock" bash -c "test ! -f '$LOCKDIR/.lock'"

echo
echo "test-context-graph-cli: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
```

- [ ] **Step 2: Make it executable and run it**

```bash
chmod +x bin/test-context-graph-cli.sh
bin/test-context-graph-cli.sh
```

Expected: all checks print `✓`, script exits 0.

- [ ] **Step 3: Wire it into `make test`**

Edit `Makefile`'s `test:` target, adding a line after
`bin/test-context-evidence.sh` (or the last context-graph-related test):

```makefile
	bin/test-context-graph-cli.sh
```

- [ ] **Step 4: Amend the notes-home layout docs**

In `docs/notes-home.md`, extend the fenced layout block:

```
~/.bindle/
  private-denylist.txt
  projects/<project>/
    profile.md
    sessions/YYYY-MM-DD-<slug>.md
    handoffs/YYYY-MM-DD-<slug>.md
    context.md                      # NEW — regenerable projection, #185 apply
    .bindle/context/
      config.json                   # NEW — authoritative, #191
      judgments.jsonl                # NEW — append-only ledger, #184
      index.json                     # NEW — rebuildable materialized graph, #185
      .lock                          # NEW — single-writer lock
```

In `docs/session-notes-format.md`, extend the matching "Stable contract"
layout block the same way (same six new lines, same indentation as its
existing `profile.md`/`sessions/`/`handoffs/` entries).

- [ ] **Step 5: Add capability inventory entries**

In `capabilities.json`, add a `type: script` capability row for
`bin/context-graph.py` (place it alphabetically near `map-entry-id`/
`context-evidence`):

```json
{
  "name": "context-graph",
  "type": "script",
  "path": "bin/context-graph.py",
  "description": "Initialize and configure a project's context-graph identity (issue #191, epic #140): `init` allocates one opaque project:<32-lowercase-hex> id via command-owned cryptographic entropy and persists it atomically; `config status`/`config validate` are read-only; `config add-repository`/`update-repository`/`remove-repository`/`set-default` maintain zero-or-more repository-binding:<32-lowercase-hex> bindings independent of mutable owner/repo coordinates, with at-most-one unique default for bare Issue/PR reference resolution; `config break-lock` removes a stale single-writer .lock after printing its owner metadata and requiring --force. Every mutation acquires the project-scoped lock shared with #184 confirm and #185 apply; malformed or conflicting existing configuration is never silently repaired. Consumes context_graph.validation.validate_config (issue #180) for shared semantic checks and adds its own structural/local-Git-origin checks. Writes only under the configured notes home, never into a project's Git checkout.",
  "provider": {
    "claude": "manual",
    "codex": "manual"
  },
  "maturity": "tested",
  "mutation": [
    "disk"
  ],
  "version_introduced": "0.7.0"
}
```

Add four `not_a_capability` ledger rows (near the existing
`bin/context_graph/*.py` entries):

```json
{
  "path": "bin/context_graph/atomic_io.py",
  "reason": "library module for atomic file writes in the context_graph contract; foundation module consumed by context_graph.config, not a standalone capability."
},
{
  "path": "bin/context_graph/lock.py",
  "reason": "library module for the single-writer project lock in the context_graph contract; consumed by context_graph.config (this issue) and reserved for #184/#185, not a standalone capability."
},
{
  "path": "bin/context_graph/config.py",
  "reason": "library module implementing project identity and repository-binding configuration; consumed by bin/context-graph.py (the capability row), not a standalone capability itself."
},
{
  "path": "bin/context_graph/tests/test_atomic_io.py",
  "reason": "unit tests for context_graph.atomic_io; test infrastructure, not a capability an agent invokes."
},
{
  "path": "bin/context_graph/tests/test_lock.py",
  "reason": "unit tests for context_graph.lock; test infrastructure, not a capability an agent invokes."
},
{
  "path": "bin/context_graph/tests/test_config.py",
  "reason": "unit tests for context_graph.config; test infrastructure, not a capability an agent invokes."
}
```

- [ ] **Step 6: Regenerate the manifest and generated docs, run full gates**

```bash
make manifest
make docs
make check
make test
```

Expected: both regeneration commands report a write (or no diff if already
current); `make check` and `make test` both `All checks passed` / all
green — the issue's own acceptance criterion #29.

- [ ] **Step 7: Commit**

```bash
git add bin/test-context-graph-cli.sh Makefile docs/notes-home.md \
  docs/session-notes-format.md capabilities.json install-manifest.tsv \
  README.md docs/provider-interop.md
git commit -m "feat(#191): add CLI integration tests, notes-home docs, capability inventory"
```

(The last two files in that `git add` are only touched if `make docs`
changed their generated tables — `git status` first and drop any that
`make docs`/`make manifest` left unchanged.)

---

## After all tasks

1. Confirm `gh issue view 191 --repo thomas-estep/bindle` acceptance
   criteria against the fixture coverage map above — every item is either
   a real test (Tasks 1–9) or explicitly marked out-of-scope for #191
   (item 23, owned by #185).
2. Open the PR: branch `feature/191-context-graph-init` (already checked
   out in this worktree) → `main`, title referencing #191, body
   summarizing the command surface shipped and the two explicit scope
   boundaries from Global Constraints.
3. Do not implement `preview`/`candidates`/`propose`/`confirm`/`apply`/bare
   `validate`/bare `status` — those are #183/#184/#185/#186.
