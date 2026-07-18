"""Tests for context_graph.apply.build_plan -- the side-effect-free
planned-state construction for the #185 apply pipeline (design doc section
12 steps 1-6). build_plan writes nothing; these tests assert only on the
returned plan.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import apply, compiler, config, review

# One UNANCHORED decision (no bindle:context-id marker) so compile_preview
# emits exactly one identity_anchor candidate. The heading carries the
# required `(YYYY-MM, settled)` status suffix -- without it HEADING_CLAIM_RE
# does not match and no entry (and so no candidate) is produced. All six `##`
# sections are present so the map is valid grammar.
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

_A = "context-node:demo:" + "a" * 32
_B = "context-node:demo:" + "b" * 32

# Two anchored decisions/learnings for the abort test. D is a decision, L a
# learning; `L --motivates--> D` is legal because motivates' target may be a
# decision. Moving D into `## Learnings` (ABORT_MAP_ILLEGAL) turns it into a
# learning, making the accepted edge illegal at apply time.
ABORT_MAP_LEGAL = (
    "# Demo\n\n"
    "## Brief\n\n"
    "## Decisions\n"
    "### The decision (2026-07, settled) <!-- bindle:context-id: %s -->\n"
    "why: x\nso: y\nevidence:\n\n"
    "## Learnings\n"
    "### The learning (2026-07) <!-- bindle:context-id: %s -->\n"
    "why: x\nso: y\nevidence:\n\n"
    "## Assumptions & tensions\n\n"
    "## Open questions\n\n"
    "## Superseded\n"
) % (_A, _B)

ABORT_MAP_ILLEGAL = (
    "# Demo\n\n"
    "## Brief\n\n"
    "## Decisions\n\n"
    "## Learnings\n"
    "### The decision (2026-07) <!-- bindle:context-id: %s -->\n"
    "why: x\nso: y\nevidence:\n"
    "### The learning (2026-07) <!-- bindle:context-id: %s -->\n"
    "why: x\nso: y\nevidence:\n\n"
    "## Assumptions & tensions\n\n"
    "## Open questions\n\n"
    "## Superseded\n"
) % (_A, _B)


def _write_map(notes_home, slug, text):
    pdir = os.path.join(notes_home, "projects", slug)
    with open(os.path.join(pdir, "map.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


class BuildPlanAnchorTest(unittest.TestCase):
    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        _write_map(self.nh, self.slug, ANCHOR_MAP)
        # Accept the one identity anchor via #184's real confirm path
        # (confirm(notes_home, slug, candidate_key, decision, ...)).
        review.confirm(self.nh, self.slug, self._anchor_key(), "accepted",
                       now="2026-07-17T00:00:00Z")

    def _anchor_key(self):
        preview = compiler.compile_preview(self.nh, self.slug)
        return preview["identity_anchor_candidates"][0]["candidate_key"]

    def test_first_apply_anchor_node_present(self):
        plan = apply.build_plan(self.nh, self.slug)
        self.assertTrue(plan["ok"], plan.get("findings"))
        labels = [n["label"]
                  for n in plan["artifacts"]["index"]["planned_obj"]["nodes"]]
        self.assertIn("Use a single-writer lock", labels)
        # The planned map carries the inserted anchor marker (bytes).
        self.assertIn(b"bindle:context-id:",
                      plan["artifacts"]["map"]["planned_bytes"])

    def test_index_planned_bytes_match_json_serialization(self):
        import json
        plan = apply.build_plan(self.nh, self.slug)
        obj = plan["artifacts"]["index"]["planned_obj"]
        expected = (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")
        self.assertEqual(plan["artifacts"]["index"]["planned_bytes"], expected)


class BuildPlanAbortTest(unittest.TestCase):
    """Step-5 abort test: an edge accepted while legal becomes illegal at
    apply time -> the whole apply aborts, no artifacts (design doc s12 step 6).
    """

    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        _write_map(self.nh, self.slug, ABORT_MAP_LEGAL)
        # Accept `L --motivates--> D` while both are their original kinds
        # (target D is a decision -> legal).
        proposal = {"source": _B, "relationship": "motivates", "target": _A,
                    "basis": [], "explanation": "x", "producer": "human"}
        key = review.propose(self.nh, self.slug, proposal)["candidate"]["candidate_key"]
        res = review.confirm(self.nh, self.slug, key, "accepted", proposal=proposal,
                             now="2026-07-17T00:00:00Z")
        self.assertEqual(res["findings"], [], res["findings"])

    def test_legal_at_accept_illegal_at_apply_aborts(self):
        # Move D into Learnings: it becomes a learning, so `motivates -> D` is
        # no longer a legal endpoint pair.
        _write_map(self.nh, self.slug, ABORT_MAP_ILLEGAL)
        plan = apply.build_plan(self.nh, self.slug)
        self.assertIs(plan["ok"], False)
        self.assertIn("stale_illegal_judgment",
                      [f["code"] for f in plan["findings"]])
        self.assertNotIn("artifacts", plan)


if __name__ == "__main__":
    unittest.main()
