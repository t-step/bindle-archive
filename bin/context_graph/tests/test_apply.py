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
from context_graph import apply, canonical, compiler, config, ledger, review

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


# Tier-2 fixture: an ANCHORED decision O (known id, legal `motivates` source)
# plus an UNANCHORED learning entry E. E is absent from the on-disk (base)
# graph, so an edge O --motivates--> E defers past Tier 1; once E is
# first-anchored THIS run its planned kind is `learning`, which is not a legal
# `motivates` target ({decision, question}) -> Tier 2 hard abort.
_O = "context-node:demo:" + "c" * 32

TIER2_MAP = (
    "# Demo\n\n"
    "## Brief\n\n"
    "## Decisions\n"
    "### The decision (2026-07, settled) <!-- bindle:context-id: %s -->\n"
    "why: x\nso: y\nevidence:\n\n"
    "## Learnings\n"
    "### First learning (2026-07)\n"
    "why: x\nso: y\nevidence:\n\n"
    "## Assumptions & tensions\n\n"
    "## Open questions\n\n"
    "## Superseded\n"
) % _O


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


class BuildPlanTier1DropTest(unittest.TestCase):
    """TIER 1 (design section 11/12/16): an edge accepted while both endpoints
    were legal in `base` becomes illegal against `base` at apply time (a
    referenced node's kind changed) -> the reducer drops it as inert and emits
    a `stale_illegal_judgment` finding; the apply CONTINUES (ok=True, artifacts
    present, the illegal edge simply not materialized)."""

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

    def test_illegal_against_base_drops_and_continues(self):
        # Move D into Learnings: it becomes a learning, so `motivates -> D` is
        # no longer a legal endpoint pair. BOTH endpoints still exist in the
        # on-disk (base) graph -> Tier 1: drop-and-continue.
        _write_map(self.nh, self.slug, ABORT_MAP_ILLEGAL)
        plan = apply.build_plan(self.nh, self.slug)
        self.assertIs(plan["ok"], True, plan.get("findings"))
        self.assertIn("artifacts", plan)
        self.assertIn("stale_illegal_judgment",
                      [f["code"] for f in plan["findings"]])
        # The dropped edge never reaches the planned graph.
        planned_edges = plan["artifacts"]["index"]["planned_obj"]["edges"]
        self.assertNotIn("motivates", [e.get("relationship") for e in planned_edges])


class BuildPlanTier2AbortTest(unittest.TestCase):
    """TIER 2 (design section 11/12/16): an accepted edge that PASSES ledger
    reduction (an endpoint is absent from `base`, first-anchored this run) but
    is ILLEGAL against the PLANNED graph -> hard abort (ok=False, no artifacts),
    distinct `illegal_edge_planned_state` finding.

    The edge's endpoint is the id the anchor is randomly assigned this run;
    that id does not exist until the anchor is accepted, so no propose/confirm
    path can validate the edge against a not-yet-anchored node. The edge event
    is therefore appended to the ledger directly with the real assigned id --
    the only way to construct an edge onto a first-anchored-this-run endpoint.
    """

    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        _write_map(self.nh, self.slug, TIER2_MAP)

    def _anchor_key(self):
        preview = compiler.compile_preview(self.nh, self.slug)
        cands = preview["identity_anchor_candidates"]
        self.assertEqual(len(cands), 1, cands)
        return cands[0]["candidate_key"]

    def test_illegal_against_planned_graph_aborts(self):
        # Accept the first-anchor for the (unanchored) learning entry E; its
        # randomly assigned id becomes E's node id in the planned graph only.
        res = review.confirm(self.nh, self.slug, self._anchor_key(), "accepted",
                             now="2026-07-17T00:00:00Z")
        assigned = res["event"]["assigned_id"]
        self.assertTrue(assigned, res)
        # Sanity: E is NOT a node in base (still unanchored on disk), so the
        # edge below defers past Tier 1 and only fails against the planned graph.
        base = compiler.compile_preview(self.nh, self.slug)
        self.assertNotIn(assigned, {n["id"] for n in base["nodes"]})

        # O --motivates--> E. Legal source (decision), but E's planned kind is
        # `learning`, an illegal `motivates` target.
        edge_event = {
            "schema_version": 1, "subject_type": "edge",
            "subject_key": canonical.edge_subject_key(_O, "motivates", assigned),
            "candidate_key": canonical.candidate_key(_O, "motivates", assigned, []),
            "decision": "accepted", "decided_at": "2026-07-17T00:00:00Z",
            "source": _O, "relationship": "motivates", "target": assigned,
            "basis": [],
        }
        ledger.append_judgment(
            ledger.judgments_path(self.nh, self.slug), edge_event)

        plan = apply.build_plan(self.nh, self.slug)
        self.assertIs(plan["ok"], False)
        self.assertNotIn("artifacts", plan)
        codes = [f["code"] for f in plan["findings"]]
        self.assertIn("illegal_edge_planned_state", codes)
        # Tier 2 must NOT masquerade as the Tier 1 (continued) code.
        self.assertNotIn("stale_illegal_judgment", codes)


if __name__ == "__main__":
    unittest.main()
