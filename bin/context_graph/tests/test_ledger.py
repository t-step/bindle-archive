import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import ledger, config


class LedgerIO(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.slug = "proj"
        config.init_project(self.notes_home, self.slug)
        self.path = ledger.judgments_path(self.notes_home, self.slug)

    def test_missing_file_reduces_to_empty(self):
        self.assertEqual(ledger.load_judgments(self.path), [])

    def test_append_then_load_roundtrip_preserves_order(self):
        ledger.append_judgment(self.path, {"schema_version": 1, "n": 1})
        ledger.append_judgment(self.path, {"schema_version": 1, "n": 2})
        loaded = ledger.load_judgments(self.path)
        self.assertEqual([e["n"] for e in loaded], [1, 2])

    def test_path_is_under_context_dir(self):
        self.assertTrue(self.path.endswith(os.path.join(".bindle", "context", "judgments.jsonl")))

    def test_malformed_line_raises(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json}\n")
        with self.assertRaises(ledger.LedgerError):
            ledger.load_judgments(self.path)
