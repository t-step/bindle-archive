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
