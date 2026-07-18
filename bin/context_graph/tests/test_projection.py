import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import projection
from context_graph import projection as P


def _graph():
    return {
        "project_id": "context-project:abc",
        "nodes": [
            {"id": "n:a", "class": "semantic", "kind": "decision", "label": "Use a lock", "status": "active"},
            {"id": "e:s1", "class": "evidence", "kind": "session", "label": "2026-07-01 note", "status": "active"},
        ],
        "edges": [
            {"key": "n:a|implemented_by|e:s1", "source": "n:a", "relationship": "implemented_by",
             "target": "e:s1", "status": "confirmed", "origin": "human_judgment",
             "basis": [], "review_trigger": False},
        ],
        "coverage": {"project_map": "complete", "sessions": "complete", "handoffs": "complete",
                     "documents": "complete", "github_issues": "complete",
                     "github_prs": "complete", "commits": "complete"},
        "conflicts": [],
    }


class RenderManagedRegionTest(unittest.TestCase):
    def test_contains_expected_sections(self):
        body = projection.render_managed_region(_graph())
        for heading in ["## Decision and learning graph", "## Evidence and delivery",
                        "## Review-triggering coupling", "## Unconnected durable entries",
                        "## Evidence coverage", "## Conflicts"]:
            self.assertIn(heading, body)

    def test_deterministic(self):
        self.assertEqual(projection.render_managed_region(_graph()),
                         projection.render_managed_region(_graph()))

    def test_evidence_attribution_rendered(self):
        body = projection.render_managed_region(_graph())
        self.assertIn("Use a lock", body)
        self.assertIn("implemented_by", body)

    def test_contains_only_node_is_unconnected(self):
        # A semantic node whose ONLY edge is the compiler's unconditional
        # project->node `contains` edge must still surface in "Unconnected
        # durable entries" -- `contains` is structural bookkeeping, not a
        # sign the entry has real structural/evidence coupling.
        graph = {
            "project_id": "context-project:abc",
            "nodes": [
                {"id": "project:abc", "class": "project", "kind": "project",
                 "label": "Project abc", "status": "active"},
                {"id": "n:isolated", "class": "semantic", "kind": "decision",
                 "label": "Isolated decision", "status": "active"},
            ],
            "edges": [
                {"key": "project:abc|contains|n:isolated", "source": "project:abc",
                 "relationship": "contains", "target": "n:isolated",
                 "status": "confirmed", "origin": "project_membership",
                 "basis": [], "review_trigger": False},
            ],
            "coverage": {"project_map": "complete", "sessions": "complete", "handoffs": "complete",
                         "documents": "complete", "github_issues": "complete",
                         "github_prs": "complete", "commits": "complete"},
            "conflicts": [],
        }
        body = projection.render_managed_region(graph)
        section = body.split("## Unconnected durable entries\n\n", 1)[1]
        section = section.split("\n## ", 1)[0]
        self.assertIn("Isolated decision", section)
        self.assertNotEqual(section.strip(), "(none)")


SKELE_BODY = "## Decision and learning graph\n(none)\n"


class PlanContextMdTest(unittest.TestCase):
    def test_absent_creates_skeleton_with_markers(self):
        out = P.plan_context_md(None, SKELE_BODY)
        self.assertEqual(out["action"], "create")
        self.assertIn(P.BEGIN, out["text"])
        self.assertIn(P.END, out["text"])
        self.assertIn(SKELE_BODY, out["text"])

    def test_update_replaces_only_managed_region(self):
        existing = ("# Demo — context\n" + P.BEGIN + "\nOLD\n" + P.END +
                    "\n## Maintainer notes\nkeep me\n")
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out["action"], "update")
        self.assertIn("keep me", out["text"])
        self.assertIn(SKELE_BODY, out["text"])
        self.assertNotIn("OLD", out["text"])

    def test_identical_region_is_noop(self):
        existing = P.BEGIN + "\n" + SKELE_BODY + P.END + "\n"
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out["action"], "noop")

    def test_markerless_is_conflict(self):
        out = P.plan_context_md("# hand written, no markers\n", SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_unmanaged"})

    def test_duplicate_markers_is_conflict(self):
        existing = P.BEGIN + "\nA\n" + P.END + "\n" + P.BEGIN + "\nB\n" + P.END + "\n"
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_malformed_markers"})

    def test_reversed_markers_is_conflict(self):
        existing = P.END + "\nx\n" + P.BEGIN + "\n"
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_malformed_markers"})

    def test_partial_marker_is_conflict(self):
        existing = P.BEGIN + "\nonly begin, no end\n"
        out = P.plan_context_md(existing, SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_malformed_markers"})


class AdoptContextMdTest(unittest.TestCase):
    def test_still_markerless_adopts(self):
        out = P.plan_adopt_context_md("hand written notes\n", SKELE_BODY)
        self.assertEqual(out["action"], "adopt")
        self.assertIn(P.BEGIN, out["text"])
        self.assertIn("hand written notes", out["text"])

    def test_gained_marker_refuses(self):
        existing = P.BEGIN + "\nx\n" + P.END + "\n"
        out = P.plan_adopt_context_md(existing, SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_adopt_state_changed"})

    def test_gained_malformed_marker_refuses(self):
        out = P.plan_adopt_context_md(P.BEGIN + "\nno end\n", SKELE_BODY)
        self.assertEqual(out, {"action": "conflict", "code": "context_md_adopt_state_changed"})


if __name__ == "__main__":
    unittest.main()
