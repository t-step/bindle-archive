"""Tests for context_graph.review -- the #184 propose/confirm orchestration.
This file covers only `propose` (Task 5); `confirm`/`list_candidates` are
later tasks and are intentionally not exercised here.
"""
import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import review, config

# Known-good map grammar, proven by test_compiler.py's `base_map` fixture
# (see CompilerTestBase.base_map / DeterministicEdges tests): a `###`
# heading under `## Decisions` carrying a `bindle:context-id` marker and
# `(YYYY-MM, settled)` status becomes an anchored semantic "decision" node;
# the identical shape under `## Learnings` (status token omitted -- Learnings
# freeze it out per map_parser's ANCHOR_KIND/HEADING_CLAIM_RE docstring)
# becomes an anchored semantic "learning" node. Both must carry an explicit
# `bindle:context-id` marker: compiler.compile_preview only emits a semantic
# node for an *anchored* entry -- an unanchored one only yields an
# identity_anchor candidate, never a usable proposal endpoint.
MAP_TWO_DECISIONS = (
    "## Brief\n\n"
    "## Decisions\n"
    "### A decision (2026-07, settled) "
    "<!-- bindle:context-id: context-node:proj:11111111111111111111111111111111 -->\n"
    "why: x\nso: y\nrevisit-when: z\nevidence:\n"
    "\n## Learnings\n"
    "### A learning (2026-07) "
    "<!-- bindle:context-id: context-node:proj:22222222222222222222222222222222 -->\n"
    "why: x\nso: y\nevidence:\n"
    "\n## Assumptions & tensions\n\n"
    "## Open questions\n\n"
    "## Superseded\n"
)


class ProposeBase(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.slug = "proj"
        config.init_project(self.notes_home, self.slug)
        pdir = os.path.join(self.notes_home, "projects", self.slug)
        with open(os.path.join(pdir, "map.md"), "w", encoding="utf-8") as fh:
            fh.write(MAP_TWO_DECISIONS)

    def node_ids(self):
        from context_graph import compiler
        preview = compiler.compile_preview(self.notes_home, self.slug)
        return {n["kind"]: n["id"] for n in preview["nodes"] if n["class"] == "semantic"}


class Propose(ProposeBase):
    def test_valid_proposal_returns_candidate_and_writes_nothing(self):
        ids = self.node_ids()
        self.assertIn("decision", ids)
        self.assertIn("learning", ids)
        # decision -> learning is a legal `supports` pair (source in
        # {decision, learning, assumption}, target = any semantic kind) --
        # see relationships.ENDPOINT_MATRIX["supports"].
        proposal = {"source": ids["decision"], "relationship": "supports",
                    "target": ids["learning"], "basis": [], "explanation": "x",
                    "producer": "human"}
        out = review.propose(self.notes_home, self.slug, proposal)
        self.assertEqual(out["findings"], [])
        self.assertTrue(out["candidate"]["candidate_key"].startswith("candidate:sha256:"))
        # No judgments.jsonl created by propose.
        from context_graph import ledger
        self.assertFalse(os.path.exists(ledger.judgments_path(self.notes_home, self.slug)))

    def test_illegal_proposal_surfaces_finding(self):
        ids = self.node_ids()
        # supersedes requires same_kind endpoints; decision -> learning is
        # cross-kind and therefore illegal (relationships.ENDPOINT_MATRIX
        # ["supersedes"]["same_kind_required"] is True).
        proposal = {"source": ids["decision"], "relationship": "supersedes",
                    "target": ids["learning"], "basis": [], "explanation": "x",
                    "producer": "human"}
        out = review.propose(self.notes_home, self.slug, proposal)
        self.assertIsNone(out["candidate"])
        self.assertTrue(out["findings"])


class ProposeCompilerError(unittest.TestCase):
    def test_missing_configuration_raises_review_error(self):
        notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, notes_home, ignore_errors=True)
        proposal = {"source": "x", "relationship": "supports", "target": "y",
                    "basis": [], "explanation": "x", "producer": "human"}
        with self.assertRaises(review.ReviewError) as ctx:
            review.propose(notes_home, "nope", proposal)
        self.assertTrue(ctx.exception.findings)
        self.assertEqual(ctx.exception.findings[0]["code"], "E_CONFIG_MISSING")


if __name__ == "__main__":
    unittest.main()
