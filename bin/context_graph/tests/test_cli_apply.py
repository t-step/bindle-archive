"""Process-boundary test for #185's `apply` subcommand wiring in
bin/context-graph.py. context-graph.py's filename is not import-safe (a
hyphen), so it is loaded via importlib.util from its real path -- the same
sys.path-insert-then-import trick the CLI script itself performs still runs
inside exec_module, so `context_graph.*` imports inside it resolve.

This asserts the subcommand is registered and dispatches to
context_graph.apply.apply correctly: exit 0 on ok/no-conflicts and
index.json materialized on disk. Deeper apply-pipeline behavior (build_plan
tiers, atomic writes, context.md conflict handling) is already covered by
test_apply.py against the apply module directly; this file only proves the
CLI wiring itself.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import compiler, config, review

_CLI_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "context-graph.py")
_spec = importlib.util.spec_from_file_location("context_graph_cli", _CLI_PATH)
_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cli)

ANCHOR_MAP = (
    "# Demo\n\n"
    "## Brief\n\n"
    "## Decisions\n"
    "### Use a single-writer lock (2026-07, settled)\n"
    "why: correctness\nso: no double allocation\nevidence:\n\n"
    "## Learnings\n\n"
    "## Assumptions & tensions\n\n"
    "## Open questions\n\n"
    "## Superseded\n"
)


def _write_map(notes_home, slug, text):
    pdir = os.path.join(notes_home, "projects", slug)
    with open(os.path.join(pdir, "map.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


class CmdApplyTest(unittest.TestCase):
    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        _write_map(self.nh, self.slug, ANCHOR_MAP)
        # Accept the one identity anchor via #184's confirm path so apply has
        # a legal graph to materialize.
        review.confirm(self.nh, self.slug, self._anchor_key(), "accepted",
                       now="2026-07-17T00:00:00Z")

    def _anchor_key(self):
        preview = compiler.compile_preview(self.nh, self.slug)
        return preview["identity_anchor_candidates"][0]["candidate_key"]

    def _index_path(self):
        return os.path.join(self.nh, "projects", self.slug,
                             ".bindle", "context", "index.json")

    def test_apply_subcommand_registered_and_dispatches(self):
        rc = _cli.main(["apply", "--notes-home", self.nh, "--project", self.slug])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(self._index_path()))

    def test_apply_subcommand_accepts_repeatable_repo_root_and_adopt_flag(self):
        # Usage-level proof: both apply-specific flags parse (no argparse
        # usage error) and the parsed --repo-root dict reaches apply.apply --
        # no repository named "origin" is configured for this fixture, so
        # apply.apply reports it back as an unknown-repo-root-alias conflict
        # (exit 1), which is only possible if the flag's value made it
        # through _parse_repo_roots into the call.
        rc = _cli.main([
            "apply", "--notes-home", self.nh, "--project", self.slug,
            "--repo-root", "origin=/nonexistent", "--adopt-context-md",
        ])
        self.assertEqual(rc, 1)
        self.assertTrue(os.path.exists(self._index_path()))


if __name__ == "__main__":
    unittest.main()
