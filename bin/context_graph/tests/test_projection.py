import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import projection


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


if __name__ == "__main__":
    unittest.main()
