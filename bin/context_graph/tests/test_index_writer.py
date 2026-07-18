import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import index_writer


class RenderIndexTest(unittest.TestCase):
    def _graph(self):
        return {
            "schema_version": 1,
            "project_id": "context-project:abc",
            "nodes": [
                {"id": "n:b", "class": "semantic", "kind": "decision", "label": "B", "status": "active"},
                {"id": "n:a", "class": "semantic", "kind": "decision", "label": "A", "status": "active"},
            ],
            "edges": [
                {"key": "n:b|supports|n:a", "source": "n:b", "relationship": "supports",
                 "target": "n:a", "status": "confirmed", "origin": "human_judgment",
                 "basis": [], "review_trigger": False},
            ],
            "coverage": {"project_map": "complete", "sessions": "complete",
                         "handoffs": "complete", "documents": "complete",
                         "github_issues": "complete", "github_prs": "complete",
                         "commits": "complete"},
            "conflicts": [],
        }

    def test_nodes_sorted_by_id(self):
        out = index_writer.render_index(self._graph())
        self.assertEqual([n["id"] for n in out["nodes"]], ["n:a", "n:b"])

    def test_edge_origin_and_key_preserved(self):
        out = index_writer.render_index(self._graph())
        self.assertEqual(out["edges"][0]["origin"], "human_judgment")
        self.assertEqual(out["edges"][0]["key"], "n:b|supports|n:a")

    def test_list_fields_default_empty(self):
        out = index_writer.render_index(self._graph())
        self.assertEqual(out["unresolved_evidence"], [])
        self.assertEqual(out["suppressed_rejections"], [])
        self.assertEqual(out["conflicts"], [])

    def test_project_id_and_version(self):
        out = index_writer.render_index(self._graph())
        self.assertEqual(out["project_id"], "context-project:abc")
        self.assertEqual(out["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
