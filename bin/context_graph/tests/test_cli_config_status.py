"""Process-boundary test for #185's orphaned-temp-file reporting added to
`config status` in bin/context-graph.py (cmd_config_status). context-graph.py's
filename is not import-safe (a hyphen), so it is loaded via importlib.util
from its real path -- the same sys.path-insert-then-import trick the CLI
script itself performs still runs inside exec_module, so `context_graph.*`
imports inside it resolve.

Apply writes atomically via a temp-file-in-the-same-directory + os.replace
(context_graph.atomic_io.write_atomic). A crash between the temp write and
the rename leaves an orphaned temp file behind. `config status` is the
existing read-only diagnostic command; it must REPORT such orphans (design
doc section 12, "Temporary files ... orphan cleanup" is passive, never
automatic) but never delete them.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import config

_CLI_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "context-graph.py")
_spec = importlib.util.spec_from_file_location("context_graph_cli", _CLI_PATH)
_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cli)


def _run_status(nh, slug):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _cli.main([
            "config", "status", "--notes-home", nh, "--project", slug,
        ])
    return rc, json.loads(buf.getvalue())


class CmdConfigStatusOrphanedTempFilesTest(unittest.TestCase):
    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        self.cdir = config.context_dir(self.nh, self.slug)

    def test_no_orphans_reports_empty_list(self):
        rc, obj = _run_status(self.nh, self.slug)
        self.assertEqual(rc, 0)
        self.assertIn("orphaned_temp_files", obj)
        self.assertEqual(obj["orphaned_temp_files"], [])

    def test_orphaned_temp_file_in_context_dir_is_reported_not_deleted(self):
        # Named per atomic_io.write_atomic's exact tempfile.mkstemp
        # convention: prefix=".tmp-", no fixed suffix, created in the same
        # directory as the target file it was standing in for.
        orphan_path = os.path.join(self.cdir, ".tmp-orphan123")
        with open(orphan_path, "w", encoding="utf-8") as fh:
            fh.write("leftover from a crash between write and os.replace")

        rc, obj = _run_status(self.nh, self.slug)

        self.assertEqual(rc, 0)
        self.assertIn("orphaned_temp_files", obj)
        self.assertIn(orphan_path, obj["orphaned_temp_files"])
        # never auto-deleted -- config status is read-only diagnostics only
        self.assertTrue(os.path.exists(orphan_path))

    def test_unrelated_file_is_not_reported_as_orphan(self):
        unrelated_path = os.path.join(self.cdir, "not-a-temp-file.txt")
        with open(unrelated_path, "w", encoding="utf-8") as fh:
            fh.write("unrelated")

        rc, obj = _run_status(self.nh, self.slug)

        self.assertEqual(rc, 0)
        self.assertNotIn(unrelated_path, obj["orphaned_temp_files"])


if __name__ == "__main__":
    unittest.main()
