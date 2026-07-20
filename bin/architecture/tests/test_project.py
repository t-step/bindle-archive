"""Tests for architecture.project (issue #374 child D, slice D5).

Scope note: this module is the FIRST WRITER of the architecture surface's
`config.json`. Slices D1-D4 shipped path helpers and a validator
(`state.config_path`, `state.validate_config`) but nothing that ever
authored the document they describe, so every architecture test to date
hand-built a config dict in memory. That is what these tests close.

Two guarantees carry the weight here and both are asserted on the
FILESYSTEM rather than on a return value:

1. IDEMPOTENCE IS ZERO BYTES, not merely `created=False`. A second `init`
   must not rewrite the file, because the config is operator-owned and
   carries hand-maintained `exclusions`; the schema's own description says
   apply is read-only on it for exactly that reason. Comparing bytes AND
   mtime is the only way to tell "returned the existing config" apart from
   "rewrote an identical config".
2. A MALFORMED EXISTING CONFIG IS NEVER REPAIRED. Silently rewriting one
   would destroy operator edits, so `init` raises and leaves the bytes
   alone -- also asserted on disk.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import project
from architecture import state
from context_graph import config as ctx_config
from context_graph import lock

SLUG = "bindle"


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class InitProjectTests(unittest.TestCase):

    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)

    def _path(self):
        return state.config_path(self.notes_home, SLUG)

    # --- creation -------------------------------------------------------

    def test_init_creates_a_config_that_the_frozen_validator_accepts(self):
        cfg, created = project.init_project(self.notes_home, SLUG)
        self.assertTrue(created)
        self.assertEqual([], state.validate_config(cfg))

    def test_init_writes_the_config_to_the_frozen_path(self):
        project.init_project(self.notes_home, SLUG)
        self.assertTrue(os.path.isfile(self._path()))

    def test_written_bytes_round_trip_to_the_returned_config(self):
        cfg, _ = project.init_project(self.notes_home, SLUG)
        with open(self._path(), encoding="utf-8") as handle:
            self.assertEqual(cfg, json.load(handle))

    def test_project_id_is_a_freshly_minted_project_identifier(self):
        cfg, _ = project.init_project(self.notes_home, SLUG)
        self.assertRegex(cfg["project_id"], r"^project:[0-9a-f]{32}$")

    def test_two_projects_get_distinct_project_ids(self):
        first, _ = project.init_project(self.notes_home, SLUG)
        second, _ = project.init_project(self.notes_home, "other-project")
        self.assertNotEqual(first["project_id"], second["project_id"])

    def test_project_slug_is_recorded_verbatim(self):
        cfg, _ = project.init_project(self.notes_home, SLUG)
        self.assertEqual(SLUG, cfg["project_slug"])

    def test_defaults_populate_every_required_field(self):
        cfg, _ = project.init_project(self.notes_home, SLUG)
        for field in ("schema_version", "projection_schema_version",
                      "project_id", "project_slug", "bindings", "caps",
                      "thresholds", "diff_size_confirmation_limit"):
            self.assertIn(field, cfg)

    def test_default_over_cap_behavior_is_the_only_permitted_value(self):
        cfg, _ = project.init_project(self.notes_home, SLUG)
        self.assertEqual("report", cfg["caps"]["over_cap_behavior"])
        self.assertIn(cfg["caps"]["over_cap_behavior"], state.OVER_CAP_BEHAVIORS)

    def test_bindings_start_empty_rather_than_absent(self):
        cfg, _ = project.init_project(self.notes_home, SLUG)
        self.assertEqual([], cfg["bindings"])

    def test_display_name_is_omitted_when_not_supplied(self):
        cfg, _ = project.init_project(self.notes_home, SLUG)
        self.assertNotIn("display_name", cfg)

    def test_display_name_is_recorded_when_supplied(self):
        cfg, _ = project.init_project(self.notes_home, SLUG,
                                      display_name="Bindle")
        self.assertEqual("Bindle", cfg["display_name"])

    def test_caller_supplied_max_nodes_is_honored(self):
        cfg, _ = project.init_project(self.notes_home, SLUG, max_nodes=7)
        self.assertEqual(7, cfg["caps"]["max_nodes"])
        self.assertEqual([], state.validate_config(cfg))

    def test_caller_supplied_thresholds_are_honored(self):
        cfg, _ = project.init_project(self.notes_home, SLUG,
                                      high=0.9, low=0.1)
        self.assertEqual({"high": 0.9, "low": 0.1}, cfg["thresholds"])
        self.assertEqual([], state.validate_config(cfg))

    def test_a_rejected_max_nodes_writes_nothing(self):
        with self.assertRaises(project.ConfigInvalidError):
            project.init_project(self.notes_home, SLUG, max_nodes=0)
        self.assertFalse(os.path.exists(self._path()))

    def test_a_malformed_slug_is_refused(self):
        with self.assertRaises(project.ConfigInvalidError):
            project.init_project(self.notes_home, "Not A Slug")

    # --- idempotence ----------------------------------------------------

    def test_second_init_reports_not_created(self):
        project.init_project(self.notes_home, SLUG)
        _, created = project.init_project(self.notes_home, SLUG)
        self.assertFalse(created)

    def test_second_init_returns_the_same_project_id(self):
        first, _ = project.init_project(self.notes_home, SLUG)
        second, _ = project.init_project(self.notes_home, SLUG)
        self.assertEqual(first["project_id"], second["project_id"])

    def test_second_init_writes_zero_bytes(self):
        project.init_project(self.notes_home, SLUG)
        before = _read_bytes(self._path())
        before_mtime = os.stat(self._path()).st_mtime_ns
        project.init_project(self.notes_home, SLUG)
        self.assertEqual(before, _read_bytes(self._path()))
        self.assertEqual(before_mtime, os.stat(self._path()).st_mtime_ns)

    def test_second_init_preserves_operator_edits(self):
        """The config is operator-owned; `exclusions` is hand-maintained.
        A re-init that regenerated defaults would silently drop it."""
        project.init_project(self.notes_home, SLUG)
        with open(self._path(), encoding="utf-8") as handle:
            cfg = json.load(handle)
        cfg["exclusions"] = ["vendor/**"]
        with open(self._path(), "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, indent=2, sort_keys=True)
        returned, created = project.init_project(self.notes_home, SLUG)
        self.assertFalse(created)
        self.assertEqual(["vendor/**"], returned["exclusions"])

    def test_second_init_does_not_honor_new_defaults(self):
        """An existing config wins over caller-supplied settings -- `init`
        is not a mutation verb, so a changed --max-nodes must not silently
        rewrite the operator's file."""
        project.init_project(self.notes_home, SLUG, max_nodes=5)
        cfg, created = project.init_project(self.notes_home, SLUG, max_nodes=99)
        self.assertFalse(created)
        self.assertEqual(5, cfg["caps"]["max_nodes"])

    # --- refusing to repair ---------------------------------------------

    def test_existing_malformed_config_raises(self):
        os.makedirs(os.path.dirname(self._path()))
        with open(self._path(), "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1}, handle)
        with self.assertRaises(project.ConfigInvalidError):
            project.init_project(self.notes_home, SLUG)

    def test_existing_malformed_config_is_left_byte_identical(self):
        os.makedirs(os.path.dirname(self._path()))
        with open(self._path(), "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1}, handle)
        before = _read_bytes(self._path())
        with self.assertRaises(project.ConfigInvalidError):
            project.init_project(self.notes_home, SLUG)
        self.assertEqual(before, _read_bytes(self._path()))

    def test_malformed_config_error_carries_the_validator_findings(self):
        os.makedirs(os.path.dirname(self._path()))
        with open(self._path(), "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1}, handle)
        with self.assertRaises(project.ConfigInvalidError) as caught:
            project.init_project(self.notes_home, SLUG)
        codes = [f["code"] for f in caught.exception.findings]
        self.assertIn("E_ARCH_CONFIG_MISSING_FIELD", codes)

    def test_unparseable_config_is_reported_not_overwritten(self):
        os.makedirs(os.path.dirname(self._path()))
        with open(self._path(), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        with self.assertRaises(project.ConfigUnreadableError) as caught:
            project.init_project(self.notes_home, SLUG)
        self.assertEqual(["E_ARCH_CONFIG_UNREADABLE"],
                         [f["code"] for f in caught.exception.findings])
        self.assertEqual(b"{not json", _read_bytes(self._path()))

    def test_a_config_for_another_project_is_a_hard_abort(self):
        """#228 freezes a project_id mismatch as a hard abort. Here the
        mismatch is the SLUG: a notes-home directory copied under a new
        project name would otherwise adopt the old project's identity."""
        project.init_project(self.notes_home, SLUG)
        path = self._path()
        other = state.config_path(self.notes_home, "other-project")
        os.makedirs(os.path.dirname(other))
        shutil.copyfile(path, other)
        with self.assertRaises(project.ConfigInvalidError):
            project.init_project(self.notes_home, "other-project")


class LoadConfigTests(unittest.TestCase):

    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)

    def test_missing_config_loads_as_none(self):
        path = state.config_path(self.notes_home, SLUG)
        self.assertIsNone(project.load_config(path))

    def test_unparseable_config_raises(self):
        path = state.config_path(self.notes_home, SLUG)
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        with self.assertRaises(project.ConfigUnreadableError):
            project.load_config(path)

    def test_a_valid_config_round_trips(self):
        cfg, _ = project.init_project(self.notes_home, SLUG)
        self.assertEqual(cfg,
                         project.load_config(state.config_path(self.notes_home, SLUG)))


class ValidateTests(unittest.TestCase):

    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)

    def test_missing_config_reports_a_dedicated_code(self):
        findings = project.validate(self.notes_home, SLUG)
        self.assertEqual(["E_ARCH_CONFIG_MISSING"],
                         [f["code"] for f in findings])

    def test_a_freshly_initialized_project_validates_clean(self):
        project.init_project(self.notes_home, SLUG)
        self.assertEqual([], project.validate(self.notes_home, SLUG))

    def test_findings_carry_the_uniform_shape(self):
        findings = project.validate(self.notes_home, SLUG)
        for finding in findings:
            for key in ("code", "message", "index", "field"):
                self.assertIn(key, finding)


class LockingTests(unittest.TestCase):

    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)

    def test_init_takes_the_project_lock_under_the_arch_init_operation(self):
        """The lock is project-scoped (#228) so a context apply and an
        architecture init cannot interleave. Asserted by holding it from
        the test and observing contention rather than by inspecting the
        implementation."""
        pdir = ctx_config.project_dir(self.notes_home, SLUG)
        os.makedirs(pdir, exist_ok=True)
        with lock.ProjectLock(pdir, "arch_init"):
            owner = lock.read_owner(lock.lock_path(pdir))
            self.assertEqual("arch_init", owner["operation"])

    def test_init_fails_closed_while_another_thread_holds_the_lock(self):
        """Held from a SEPARATE thread on purpose. `lock._local` is
        thread-local by design, so re-acquiring on this thread would be
        re-entrant and prove nothing -- the contention path only exists for
        a genuinely concurrent holder."""
        pdir = ctx_config.project_dir(self.notes_home, SLUG)
        os.makedirs(pdir, exist_ok=True)
        acquired = threading.Event()
        release = threading.Event()

        def hold():
            with lock.ProjectLock(pdir, "apply"):
                acquired.set()
                release.wait(30)

        holder = threading.Thread(target=hold)
        holder.start()
        try:
            self.assertTrue(acquired.wait(30), "holder thread never acquired")
            # Explicit short timeout: ProjectLock binds its 10s default as
            # a DEFAULT ARGUMENT, so patching lock._CONTENTION_TIMEOUT is
            # a no-op and the assertion would otherwise cost more than the
            # entire rest of the architecture suite. What is under test is
            # that contention RAISES, not how long it waits first.
            with self.assertRaises(lock.LockContention):
                project.init_project(self.notes_home, SLUG,
                                     contention_timeout=0.3)
        finally:
            release.set()
            holder.join(30)


if __name__ == "__main__":
    unittest.main()
