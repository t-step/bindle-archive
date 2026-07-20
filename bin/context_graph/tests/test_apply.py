"""Tests for context_graph.apply.build_plan -- the side-effect-free
planned-state construction for the #185 apply pipeline (design doc section
12 steps 1-6). build_plan writes nothing; these tests assert only on the
returned plan.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import apply, canonical, compiler, config, ledger, lock, review

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

# TWO unanchored decisions, same section+kind, DISTINCT claim headings. Bug 1
# (#185 dogfood / #184 defect): anchor_subject_key had no per-entry input, so
# both entries produced the SAME subject_key -> the reducer's `effective`
# dict (keyed by subject_key) let the second accepted anchor silently
# overwrite the first.
TWO_DECISION_MAP = (
    "# Demo\n\n"
    "## Brief\n\n"
    "## Decisions\n"
    "### First decision (2026-07, settled)\n"
    "why: x\nso: y\nevidence:\n\n"
    "### Second decision (2026-07, settled)\n"
    "why: x\nso: y\nevidence:\n\n"
    "## Learnings\n\n"
    "## Assumptions & tensions\n\n"
    "## Open questions\n\n"
    "## Superseded\n"
)

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


class ApplyWriteTest(unittest.TestCase):
    """Task 9 (design section 12 step 7): apply() acquires the single-writer
    lock, calls build_plan inside it, and atomically writes only the artifacts
    whose planned bytes differ from disk, in the fixed order map -> index ->
    context. setUp mirrors BuildPlanAnchorTest: one accepted identity anchor."""

    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        _write_map(self.nh, self.slug, ANCHOR_MAP)
        review.confirm(self.nh, self.slug, self._anchor_key(), "accepted",
                       now="2026-07-17T00:00:00Z")

    def _anchor_key(self):
        preview = compiler.compile_preview(self.nh, self.slug)
        return preview["identity_anchor_candidates"][0]["candidate_key"]

    def _mtimes(self):
        pdir = os.path.join(self.nh, "projects", self.slug)
        cdir = os.path.join(pdir, ".bindle", "context")
        return {
            "map": os.path.getmtime(os.path.join(pdir, "map.md")),
            "index": os.path.getmtime(os.path.join(cdir, "index.json")),
            "context": os.path.getmtime(os.path.join(pdir, "context.md")),
        }

    def test_first_apply_writes_all_three(self):
        res = apply.apply(self.nh, self.slug)
        self.assertTrue(res["ok"], res.get("findings"))
        pdir = os.path.join(self.nh, "projects", self.slug)
        self.assertTrue(os.path.exists(os.path.join(pdir, "context.md")))
        self.assertTrue(os.path.exists(
            os.path.join(pdir, ".bindle", "context", "index.json")))
        with open(os.path.join(pdir, "map.md")) as fh:
            self.assertIn("bindle:context-id:", fh.read())
        # Every artifact was written on the first apply, and the lock released.
        self.assertTrue(all(w["written"] for w in res["writes"]))
        self.assertFalse(os.path.exists(
            lock.lock_path(config.project_dir(self.nh, self.slug))))

    def test_second_unchanged_apply_zero_writes(self):
        apply.apply(self.nh, self.slug)
        before = self._mtimes()
        res = apply.apply(self.nh, self.slug)
        after = self._mtimes()
        self.assertEqual(before, after)  # no mtime advances
        self.assertTrue(all(not w["written"] for w in res["writes"]))
        self.assertTrue(all(w["reason"] == "noop" for w in res["writes"]))

    def test_markerless_context_md_refused_but_map_index_written(self):
        pdir = os.path.join(self.nh, "projects", self.slug)
        with open(os.path.join(pdir, "context.md"), "w") as fh:
            fh.write("hand written, no markers\n")
        res = apply.apply(self.nh, self.slug)
        with open(os.path.join(pdir, "context.md")) as fh:
            self.assertEqual(fh.read(), "hand written, no markers\n")  # untouched
        codes = [c.get("code") for c in res["conflicts"]]
        self.assertIn("context_md_unmanaged", codes)
        self.assertTrue(os.path.exists(
            os.path.join(pdir, ".bindle", "context", "index.json")))
        # map + index still wrote despite the context conflict.
        ctx_write = next(w for w in res["writes"] if w["path"].endswith("context.md"))
        self.assertEqual(ctx_write["reason"], "conflict")
        self.assertFalse(ctx_write["written"])
        self.assertTrue(res["writes"][0]["written"])  # map
        self.assertTrue(res["writes"][1]["written"])  # index

    def test_stale_lock_broken_then_apply_reconstructs_full_state(self):
        """Incomplete-apply detection and safe retry (design section 12): a
        stale `.lock` (operation:"apply", old acquired_at) is left by a crashed
        writer. After `lock.break_lock(project_dir)` a fresh apply re-derives the whole
        state from sources -- proving retry is a clean re-derivation, not a
        resume of partial work. (apply's lock uses the default 10s contention
        window, so we do not block on it here; break_lock is the operator path.)
        """
        pdir_ = config.project_dir(self.nh, self.slug)
        lpath = lock.lock_path(pdir_)
        os.makedirs(os.path.dirname(lpath), exist_ok=True)
        stale = {
            "pid": 999999, "hostname": "crashed-host", "operation": "apply",
            "acquired_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400)),
        }
        with open(lpath, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(stale, sort_keys=True))

        # The stale lock is present and carries the crashed writer's metadata.
        owner = lock.break_lock(pdir_)
        self.assertEqual(owner["operation"], "apply")
        self.assertEqual(owner["hostname"], "crashed-host")
        self.assertFalse(os.path.exists(lpath))

        # A fresh apply reconstructs full state and releases the lock.
        res = apply.apply(self.nh, self.slug)
        self.assertTrue(res["ok"], res.get("findings"))
        pdir = os.path.join(self.nh, "projects", self.slug)
        with open(os.path.join(pdir, "map.md")) as fh:
            self.assertIn("bindle:context-id:", fh.read())
        self.assertTrue(os.path.exists(
            os.path.join(pdir, ".bindle", "context", "index.json")))
        self.assertTrue(os.path.exists(os.path.join(pdir, "context.md")))
        self.assertFalse(os.path.exists(lpath))


class BuildPlanTwoDecisionAnchorTest(unittest.TestCase):
    """Bug 1 (#185 dogfood, a #184 defect fixed here per maintainer ruling):
    anchor_subject_key(project_id, map_path, section, entry_kind) has no
    per-entry input, so two decisions in the same section+kind collide onto
    ONE subject_key -> ledger.reduce_judgments' `effective` dict (keyed by
    subject_key) lets the second accepted anchor silently overwrite the
    first. Confirming BOTH sibling anchors must yield BOTH anchored nodes.
    FAILS before the fix (only one decision anchors)."""

    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        _write_map(self.nh, self.slug, TWO_DECISION_MAP)

    def test_both_sibling_anchors_survive(self):
        preview = compiler.compile_preview(self.nh, self.slug)
        cands = preview["identity_anchor_candidates"]
        self.assertEqual(len(cands), 2, cands)
        for c in cands:
            res = review.confirm(self.nh, self.slug, c["candidate_key"], "accepted",
                                 now="2026-07-17T00:00:00Z")
            self.assertIsNotNone(res["event"], res["findings"])

        plan = apply.build_plan(self.nh, self.slug)
        self.assertTrue(plan["ok"], plan.get("findings"))
        planned_bytes = plan["artifacts"]["map"]["planned_bytes"]
        self.assertEqual(planned_bytes.count(b"bindle:context-id:"), 2)
        labels = [n["label"]
                  for n in plan["artifacts"]["index"]["planned_obj"]["nodes"]]
        self.assertIn("First decision", labels)
        self.assertIn("Second decision", labels)


class ApplyIdempotentAnchorTest(unittest.TestCase):
    """Bug 2 (#185's own bug): `_revalidate`'s identity_anchor branch only
    checked `base_anchor_fps`, which the compiler emits ONLY for UNANCHORED
    entries -- so once an anchor is materialized (its marker written on a
    prior apply), the NEXT apply flags the accepted event
    `stale_illegal_judgment` and drops it, forever. FAILS before the fix
    (second apply loses the anchor)."""

    def setUp(self):
        self.nh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.nh, ignore_errors=True)
        self.slug = "demo"
        config.init_project(self.nh, self.slug)
        _write_map(self.nh, self.slug, ANCHOR_MAP)
        preview = compiler.compile_preview(self.nh, self.slug)
        key = preview["identity_anchor_candidates"][0]["candidate_key"]
        review.confirm(self.nh, self.slug, key, "accepted",
                       now="2026-07-17T00:00:00Z")

    def test_second_apply_keeps_anchor_effective(self):
        res1 = apply.apply(self.nh, self.slug)
        self.assertTrue(res1["ok"], res1.get("findings"))

        plan2 = apply.build_plan(self.nh, self.slug)
        self.assertTrue(plan2["ok"], plan2.get("findings"))
        codes = [f["code"] for f in plan2["findings"]]
        self.assertNotIn("stale_illegal_judgment", codes)
        labels = [n["label"]
                  for n in plan2["artifacts"]["index"]["planned_obj"]["nodes"]]
        self.assertIn("Use a single-writer lock", labels)

    def test_second_apply_emits_no_findings(self):
        """A satisfied anchor (materialized by apply #1) was still being
        passed whole to plan_map_bytes, which only matches anchors to
        UNANCHORED entries by fingerprint -- so apply #2 emitted a spurious
        `stale_anchor_no_entry` finding for it every time, even though
        nothing on disk needed to change. A clean, unchanged re-apply must
        produce ZERO findings and write NOTHING. FAILS before the fix
        (stale_anchor_no_entry appears in plan2["findings"])."""
        res1 = apply.apply(self.nh, self.slug)
        self.assertTrue(res1["ok"], res1.get("findings"))

        res2 = apply.apply(self.nh, self.slug)
        self.assertTrue(res2["ok"], res2.get("findings"))
        self.assertEqual(res2["findings"], [])
        for w in res2["writes"]:
            self.assertFalse(w["written"], w)


if __name__ == "__main__":
    unittest.main()
