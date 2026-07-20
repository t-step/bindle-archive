import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

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
        os.makedirs(os.path.dirname(path), exist_ok=True)
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

    def test_write_failure_does_not_orphan_lock_file(self):
        """Verify that if metadata write fails, the lock file is removed."""
        path = lock.lock_path(self.tmp)
        # _try_acquire is called directly here, bypassing __enter__'s
        # makedirs; without this the assertRaises(OSError) below would be
        # satisfied by a FileNotFoundError instead of the simulated write
        # failure it is meant to exercise.
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Patch the fdopen to raise an exception during write
        original_fdopen = os.fdopen

        def failing_fdopen(fd, *args, **kwargs):
            f = original_fdopen(fd, *args, **kwargs)
            original_write = f.write

            def failing_write(data):
                # Simulate write failure (e.g., disk full, EIO)
                raise OSError("Simulated write failure")

            f.write = failing_write
            return f

        # Try to acquire with the failing write
        with mock.patch("os.fdopen", side_effect=failing_fdopen):
            with self.assertRaises(OSError):
                lock._try_acquire(path, "init")

        # Verify the lock file does not exist (not orphaned)
        self.assertFalse(os.path.exists(path))

    def test_directory_fsync_is_called_on_acquisition(self):
        """Verify that directory fsync is called after lock file creation."""
        path = lock.lock_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        fsync_calls = []

        original_fsync_dir = lock.atomic_io._fsync_dir

        def tracking_fsync_dir(directory):
            fsync_calls.append(directory)
            return original_fsync_dir(directory)

        # Acquire lock with mocked _fsync_dir
        with mock.patch.object(lock.atomic_io, "_fsync_dir", side_effect=tracking_fsync_dir):
            lock._try_acquire(path, "init")
            try:
                # Verify _fsync_dir was called with the lock file's directory
                self.assertEqual(len(fsync_calls), 1)
                self.assertEqual(fsync_calls[0], os.path.dirname(path))
            finally:
                os.unlink(path)


class TestCrossSurfaceScope(unittest.TestCase):
    """#228 slice 4: one lock at project_dir() covers both .bindle/context
    and .bindle/architecture (PT28)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_lock_path_is_under_the_bindle_root_not_the_project_root(self):
        path = lock.lock_path(self.tmp)
        self.assertEqual(
            path, os.path.join(self.tmp, ".bindle", ".lock"))

    def test_lock_path_is_not_scoped_to_either_surface(self):
        path = lock.lock_path(self.tmp)
        self.assertNotIn(os.path.join(".bindle", "context"), path)
        self.assertNotIn(os.path.join(".bindle", "architecture"), path)

    def test_architecture_operations_are_valid(self):
        for operation in ("arch_init", "arch_config",
                          "arch_confirm", "arch_apply"):
            with lock.ProjectLock(self.tmp, operation) as held:
                self.assertEqual(
                    lock.read_owner(held.path)["operation"], operation)

    def test_context_apply_and_architecture_apply_contend_for_one_lock(self):
        """PT28: the two surfaces are serialized, not interleaved. Written
        with a foreign owner (another process's context apply) because
        same-process nesting is deliberately re-entrant."""
        path = lock.lock_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"pid": 999999, "hostname": "elsewhere",
                                "operation": "apply", "acquired_at": "x"}))
        with self.assertRaises(lock.LockContention) as ctx:
            with lock.ProjectLock(self.tmp, "arch_apply",
                                  contention_timeout=0.3, backoff_start=0.05,
                                  backoff_cap=0.1):
                pass
        self.assertEqual(ctx.exception.owner["operation"], "apply")


class TestReentrancy(unittest.TestCase):
    """An architecture orchestrator holding the project lock may call into
    context_graph.apply, which acquires the same lock. Nesting in one
    process is a no-op, not a self-deadlock."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_nested_acquire_of_the_same_path_does_not_contend(self):
        with lock.ProjectLock(self.tmp, "arch_apply") as outer:
            with lock.ProjectLock(self.tmp, "apply",
                                  contention_timeout=0.3) as inner:
                self.assertEqual(inner.path, outer.path)
                self.assertTrue(os.path.exists(inner.path))

    def test_inner_release_does_not_release_the_outer_lock(self):
        with lock.ProjectLock(self.tmp, "arch_apply") as outer:
            with lock.ProjectLock(self.tmp, "apply"):
                pass
            self.assertTrue(os.path.exists(outer.path))
        self.assertFalse(os.path.exists(outer.path))

    def test_owner_metadata_stays_that_of_the_outermost_holder(self):
        with lock.ProjectLock(self.tmp, "arch_apply") as outer:
            with lock.ProjectLock(self.tmp, "apply"):
                self.assertEqual(
                    lock.read_owner(outer.path)["operation"], "arch_apply")

    def test_reentrancy_is_per_path_not_global(self):
        other = tempfile.mkdtemp()
        with lock.ProjectLock(self.tmp, "arch_apply") as a:
            with lock.ProjectLock(other, "apply") as b:
                self.assertNotEqual(a.path, b.path)
                self.assertTrue(os.path.exists(a.path))
                self.assertTrue(os.path.exists(b.path))

    def test_exception_inside_a_nested_hold_unwinds_the_depth(self):
        with self.assertRaises(RuntimeError):
            with lock.ProjectLock(self.tmp, "arch_apply"):
                with lock.ProjectLock(self.tmp, "apply"):
                    raise RuntimeError("boom")
        self.assertFalse(os.path.exists(lock.lock_path(self.tmp)))
        # the registry must be clean, so a later acquire still works
        with lock.ProjectLock(self.tmp, "apply") as held:
            self.assertTrue(os.path.exists(held.path))

    def test_a_second_thread_still_contends_while_one_thread_nests(self):
        """Re-entrancy is per-process bookkeeping; it must not weaken the
        mutual exclusion the threading test already proves."""
        outcome = {}
        started = threading.Event()
        release = threading.Event()

        def holder():
            with lock.ProjectLock(self.tmp, "arch_apply"):
                with lock.ProjectLock(self.tmp, "apply"):
                    started.set()
                    release.wait(5.0)

        def contender():
            started.wait(5.0)
            try:
                with lock.ProjectLock(self.tmp, "confirm",
                                      contention_timeout=0.3,
                                      backoff_start=0.05, backoff_cap=0.1):
                    outcome["result"] = "acquired"
            except lock.LockContention:
                outcome["result"] = "contended"
            release.set()

        threads = [threading.Thread(target=holder),
                   threading.Thread(target=contender)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10.0)
        self.assertEqual(outcome.get("result"), "contended")


class TestLegacyContextLock(unittest.TestCase):
    """A crashed pre-#228 run can leave .bindle/context/.lock behind. The
    new code reports it and never removes it outside break-lock."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.legacy = os.path.join(
            self.tmp, ".bindle", "context", ".lock")
        os.makedirs(os.path.dirname(self.legacy), exist_ok=True)
        with open(self.legacy, "w", encoding="utf-8") as f:
            f.write(json.dumps({"pid": 999999, "hostname": "elsewhere",
                                "operation": "apply", "acquired_at": "x"}))

    def test_legacy_lock_path_points_at_the_context_subdir(self):
        self.assertEqual(lock.legacy_lock_path(self.tmp), self.legacy)

    def test_a_legacy_lock_does_not_block_acquisition(self):
        with lock.ProjectLock(self.tmp, "apply") as held:
            self.assertNotEqual(held.path, self.legacy)

    def test_acquiring_never_removes_a_legacy_lock(self):
        with lock.ProjectLock(self.tmp, "apply"):
            pass
        self.assertTrue(os.path.exists(self.legacy))

    def test_break_lock_leaves_the_legacy_lock_alone(self):
        lock.break_lock(self.tmp)
        self.assertTrue(os.path.exists(self.legacy))

    def test_break_legacy_lock_removes_it_and_returns_the_owner(self):
        owner = lock.break_legacy_lock(self.tmp)
        self.assertEqual(owner["hostname"], "elsewhere")
        self.assertFalse(os.path.exists(self.legacy))

    def test_break_legacy_lock_returns_none_when_absent(self):
        lock.break_legacy_lock(self.tmp)
        self.assertIsNone(lock.break_legacy_lock(self.tmp))


if __name__ == "__main__":
    unittest.main()
