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


if __name__ == "__main__":
    unittest.main()
