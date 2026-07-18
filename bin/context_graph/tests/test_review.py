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


from context_graph import review, ledger


class ConfirmEdge(ProposeBase):
    def _valid_proposal(self):
        ids = self.node_ids()
        # "motivates" requires target in {decision, question} (see
        # relationships.ENDPOINT_MATRIX["motivates"]) -- source=learning,
        # target=decision is the legal pair the fixture's two anchored
        # nodes can form.
        return {"source": ids["learning"], "relationship": "motivates",
                "target": ids["decision"], "basis": [], "explanation": "x",
                "producer": "human"}

    def test_accept_appends_event_with_edge_content(self):
        p = self._valid_proposal()
        out = review.propose(self.notes_home, self.slug, p)
        key = out["candidate"]["candidate_key"]
        res = review.confirm(self.notes_home, self.slug, key, "accepted",
                             proposal=p, now="2026-07-17T00:00:00Z")
        self.assertEqual(res["findings"], [])
        self.assertFalse(res["idempotent"])
        events = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["decision"], "accepted")
        self.assertEqual(events[0]["source"], p["source"])   # embedded content
        self.assertEqual(events[0]["relationship"], "motivates")

    def test_accept_is_idempotent(self):
        p = self._valid_proposal()
        key = review.propose(self.notes_home, self.slug, p)["candidate"]["candidate_key"]
        review.confirm(self.notes_home, self.slug, key, "accepted", proposal=p,
                       now="2026-07-17T00:00:00Z")
        res2 = review.confirm(self.notes_home, self.slug, key, "accepted", proposal=p,
                              now="2026-07-17T00:00:01Z")
        self.assertTrue(res2["idempotent"])
        events = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))
        self.assertEqual(len(events), 1)  # no second line

    def test_confirm_key_mismatch_refused(self):
        p = self._valid_proposal()
        bogus = "candidate:sha256:" + "0" * 64
        res = review.confirm(self.notes_home, self.slug, bogus, "accepted", proposal=p,
                             now="2026-07-17T00:00:00Z")
        self.assertIsNone(res["event"])
        self.assertTrue(res["findings"])

    def test_reject_appends_event_without_edge_content(self):
        p = self._valid_proposal()
        key = review.propose(self.notes_home, self.slug, p)["candidate"]["candidate_key"]
        res = review.confirm(self.notes_home, self.slug, key, "rejected", proposal=p,
                             now="2026-07-17T00:00:00Z")
        self.assertEqual(res["findings"], [])
        events = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["decision"], "rejected")
        self.assertNotIn("source", events[0])

    def test_retire_needs_no_input_and_names_prior_subject(self):
        p = self._valid_proposal()
        key = review.propose(self.notes_home, self.slug, p)["candidate"]["candidate_key"]
        review.confirm(self.notes_home, self.slug, key, "accepted", proposal=p,
                       now="2026-07-17T00:00:00Z")
        res = review.confirm(self.notes_home, self.slug, key, "retired",
                             now="2026-07-17T00:00:01Z")
        self.assertEqual(res["findings"], [])
        events = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["decision"], "retired")
        self.assertEqual(events[1]["subject_key"], events[0]["subject_key"])


class ConfirmAnchor(ProposeBase):
    def setUp(self):
        # ProposeBase's map has both entries fully anchored (each carries a
        # bindle:context-id marker) so it yields zero anchor candidates on
        # its own -- rewrite the map with one unanchored assumption bullet
        # under "## Assumptions & tensions" (the shape proven by
        # test_compiler.py's AnchorCandidates fixture) so compile_preview
        # emits exactly one identity_anchor_candidate to confirm against.
        super().setUp()
        pdir = os.path.join(self.notes_home, "projects", self.slug)
        map_text = MAP_TWO_DECISIONS.replace(
            "## Assumptions & tensions\n\n",
            "## Assumptions & tensions\n"
            "- An unanchored assumption — confidence: low — evidence: docs/w.md\n\n",
        )
        with open(os.path.join(pdir, "map.md"), "w", encoding="utf-8") as fh:
            fh.write(map_text)

    def _anchor_candidate(self):
        from context_graph import compiler
        preview = compiler.compile_preview(self.notes_home, self.slug)
        cands = preview["identity_anchor_candidates"]
        self.assertTrue(cands, "map must yield at least one anchor candidate")
        return cands[0]

    def test_accept_allocates_id_and_appends(self):
        c = self._anchor_candidate()
        res = review.confirm(self.notes_home, self.slug, c["candidate_key"], "accepted",
                             now="2026-07-17T00:00:00Z")
        self.assertEqual(res["findings"], [])
        ev = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))[0]
        self.assertEqual(ev["subject_type"], "identity_anchor")
        self.assertTrue(ev["assigned_id"].startswith("context-node:"))
        self.assertEqual(ev["entry_fingerprint"], c["entry_fingerprint"])

    def test_retired_of_prior_acceptance_carries_assigned_id(self):
        c = self._anchor_candidate()
        review.confirm(self.notes_home, self.slug, c["candidate_key"], "accepted",
                       now="2026-07-17T00:00:00Z")
        events = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))
        accepted_id = events[0]["assigned_id"]
        res = review.confirm(self.notes_home, self.slug, c["candidate_key"], "retired",
                             now="2026-07-17T00:00:01Z")
        self.assertEqual(res["findings"], [])
        events = ledger.load_judgments(ledger.judgments_path(self.notes_home, self.slug))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["subject_type"], "identity_anchor")
        self.assertEqual(events[1]["assigned_id"], accepted_id)
        self.assertEqual(events[1]["entry_fingerprint"], c["entry_fingerprint"])


class ListCandidates(ConfirmAnchor):
    # ProposeBase's own map has both entries fully anchored, so it yields
    # zero identity_anchor_candidates on its own (see ConfirmAnchor.setUp's
    # comment) -- reuse ConfirmAnchor's fixture (one unanchored assumption
    # bullet added) so pending-anchor listing actually has rows to assert on.
    def test_pending_edge_is_always_empty(self):
        out = review.list_candidates(self.notes_home, self.slug,
                                     subject_type="edge", status="pending")
        self.assertEqual(out["rows"], [])

    def test_pending_anchor_lists_live_candidates(self):
        out = review.list_candidates(self.notes_home, self.slug,
                                     subject_type="identity_anchor", status="pending")
        self.assertTrue(out["rows"])
        for r in out["rows"]:
            self.assertEqual(r["subject_type"], "identity_anchor")
            self.assertIn("candidate_origin", r)

    def test_accepted_reads_ledger(self):
        c = review.list_candidates(self.notes_home, self.slug,
                                   subject_type="identity_anchor", status="pending")["rows"][0]
        review.confirm(self.notes_home, self.slug, c["candidate_key"], "accepted",
                       now="2026-07-17T00:00:00Z")
        out = review.list_candidates(self.notes_home, self.slug, status="accepted")
        self.assertTrue(any(r["candidate_key"] == c["candidate_key"] for r in out["rows"]))

    def _valid_edge_proposal(self):
        # Same legal pair as ConfirmEdge._valid_proposal (learning -> decision
        # under "motivates") -- ListCandidates doesn't inherit ConfirmEdge, so
        # this is its own copy of that fixture shape.
        ids = self.node_ids()
        return {"source": ids["learning"], "relationship": "motivates",
                "target": ids["decision"], "basis": [], "explanation": "x",
                "producer": "human"}

    def test_reject_then_reaccept_identical_key_lists_only_accepted(self):
        # Reject candidate K, then re-propose the byte-identical edge (same
        # basis -> same candidate_key K) and accept it. rejected_keys is a
        # monotonic set on the reducer (never pruned), so a naive per-event
        # projection would show K as BOTH rejected and accepted. The fix must
        # dedupe to K's most-recent decision only.
        p = self._valid_edge_proposal()
        key1 = review.propose(self.notes_home, self.slug, p)["candidate"]["candidate_key"]
        res1 = review.confirm(self.notes_home, self.slug, key1, "rejected", proposal=p,
                              now="2026-07-17T00:00:00Z")
        self.assertEqual(res1["findings"], [])
        key2 = review.propose(self.notes_home, self.slug, p)["candidate"]["candidate_key"]
        self.assertEqual(key1, key2, "identical proposal must recompute the same candidate_key")
        res2 = review.confirm(self.notes_home, self.slug, key2, "accepted", proposal=p,
                              now="2026-07-17T00:00:01Z")
        self.assertEqual(res2["findings"], [])

        out = review.list_candidates(self.notes_home, self.slug, subject_type="edge")
        matching = [r for r in out["rows"] if r["candidate_key"] == key1]
        self.assertEqual(len(matching), 1, "must list K exactly once")
        self.assertEqual(matching[0]["status"], "accepted")

        rejected = review.list_candidates(self.notes_home, self.slug, status="rejected")
        self.assertFalse(any(r["candidate_key"] == key1 for r in rejected["rows"]),
                         "--status rejected must not list a currently-effective key")

    def test_double_reject_lists_single_row(self):
        # Two `rejected` confirms of one candidate_key must project to one
        # rejected row, not two duplicate rows.
        p = self._valid_edge_proposal()
        key1 = review.propose(self.notes_home, self.slug, p)["candidate"]["candidate_key"]
        review.confirm(self.notes_home, self.slug, key1, "rejected", proposal=p,
                       now="2026-07-17T00:00:00Z")
        key2 = review.propose(self.notes_home, self.slug, p)["candidate"]["candidate_key"]
        self.assertEqual(key1, key2)
        review.confirm(self.notes_home, self.slug, key2, "rejected", proposal=p,
                       now="2026-07-17T00:00:01Z")

        out = review.list_candidates(self.notes_home, self.slug, status="rejected")
        matching = [r for r in out["rows"] if r["candidate_key"] == key1]
        self.assertEqual(len(matching), 1, "double reject must yield a single row")


if __name__ == "__main__":
    unittest.main()
