import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import relationships as rel


class TestVocabulary(unittest.TestCase):
    def test_fourteen_relationships(self):
        self.assertEqual(len(rel.RELATIONSHIPS), 14)
        self.assertNotIn("implements", rel.RELATIONSHIPS)
        self.assertNotIn("related_to", rel.RELATIONSHIPS)

    def test_tension_is_a_semantic_kind(self):
        self.assertIn("tension", rel.SEMANTIC_KINDS)

    def test_reserved_kinds_disjoint_from_semantic_kinds(self):
        self.assertEqual(
            rel.RESERVED_SEMANTIC_KINDS & rel.SEMANTIC_KINDS, set()
        )


class TestEndpointMatrix(unittest.TestCase):
    def test_contains_project_to_semantic_ok(self):
        r = rel.validate_endpoint_pair("contains", "project", None, "semantic", "decision")
        self.assertTrue(r["ok"])

    def test_contains_project_to_evidence_fails(self):
        r = rel.validate_endpoint_pair(
            "contains", "project", None, "evidence", "github_issue"
        )
        self.assertFalse(r["ok"])

    def test_supported_by_semantic_to_evidence_ok(self):
        r = rel.validate_endpoint_pair(
            "supported_by", "semantic", "learning", "evidence", "session"
        )
        self.assertTrue(r["ok"])

    def test_supported_by_evidence_to_semantic_fails(self):
        r = rel.validate_endpoint_pair(
            "supported_by", "evidence", "session", "semantic", "learning"
        )
        self.assertFalse(r["ok"])

    def test_closes_pr_to_issue_ok_reversed_fails(self):
        ok = rel.validate_endpoint_pair(
            "closes", "evidence", "github_pr", "evidence", "github_issue"
        )
        bad = rel.validate_endpoint_pair(
            "closes", "evidence", "github_issue", "evidence", "github_pr"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])

    def test_implemented_by_decision_to_pr_ok_learning_fails(self):
        ok = rel.validate_endpoint_pair(
            "implemented_by", "semantic", "decision", "evidence", "github_pr"
        )
        bad = rel.validate_endpoint_pair(
            "implemented_by", "semantic", "learning", "evidence", "github_pr"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])

    def test_validated_by_learning_to_design_ok_question_to_issue_fails(self):
        ok = rel.validate_endpoint_pair(
            "validated_by", "semantic", "learning", "evidence", "design_document"
        )
        bad = rel.validate_endpoint_pair(
            "validated_by", "semantic", "question", "evidence", "github_issue"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])

    def test_resolves_decision_to_question_ok_reversed_fails(self):
        ok = rel.validate_endpoint_pair(
            "resolves", "semantic", "decision", "semantic", "question"
        )
        bad = rel.validate_endpoint_pair(
            "resolves", "semantic", "question", "semantic", "decision"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])

    def test_resolves_decision_to_tension_ok(self):
        r = rel.validate_endpoint_pair(
            "resolves", "semantic", "decision", "semantic", "tension"
        )
        self.assertTrue(r["ok"])

    def test_constrains_tension_to_decision_ok(self):
        r = rel.validate_endpoint_pair(
            "constrains", "semantic", "tension", "semantic", "decision"
        )
        self.assertTrue(r["ok"])

    def test_supersedes_same_kind_ok_cross_kind_fails(self):
        ok = rel.validate_endpoint_pair(
            "supersedes", "semantic", "decision", "semantic", "decision"
        )
        bad = rel.validate_endpoint_pair(
            "supersedes", "semantic", "decision", "semantic", "learning"
        )
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])
        self.assertTrue(rel.ENDPOINT_MATRIX["supersedes"]["same_kind_required"])

    def test_implements_is_unknown_relationship(self):
        r = rel.validate_endpoint_pair(
            "implements", "semantic", "decision", "evidence", "github_pr"
        )
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "unknown_relationship")

    def test_reserved_future_kind_satisfies_no_group(self):
        r = rel.validate_endpoint_pair(
            "contains", "project", None, "semantic", "architecture_component"
        )
        self.assertFalse(r["ok"])


class TestContradictsCanonicalOrdering(unittest.TestCase):
    def test_reversed_pair_collapses_to_one_order(self):
        a = "context-node:bindle:11111111111111111111111111111111"
        b = "context-node:bindle:22222222222222222222222222222222"
        self.assertEqual(
            rel.canonicalize_contradicts_endpoints(a, b),
            rel.canonicalize_contradicts_endpoints(b, a),
        )
        self.assertEqual(rel.canonicalize_contradicts_endpoints(a, b), (a, b))

    def test_self_edge_forbidden_flag(self):
        self.assertTrue(rel.ENDPOINT_MATRIX["contradicts"]["self_edge_forbidden"])
        self.assertTrue(rel.ENDPOINT_MATRIX["depends_on"]["self_edge_forbidden"])
        self.assertTrue(rel.ENDPOINT_MATRIX["supersedes"]["self_edge_forbidden"])


class TestReviewTriggerDefaults(unittest.TestCase):
    def test_review_triggering_set(self):
        for name in ("constrains", "depends_on", "contradicts", "supersedes"):
            self.assertTrue(rel.get_review_trigger_default(name))

    def test_contextual_set(self):
        for name in ("supports", "supported_by", "discussed_in", "implemented_by",
                      "validated_by", "contains", "closes", "motivates",
                      "resolves", "revisits"):
            self.assertFalse(rel.get_review_trigger_default(name))


if __name__ == "__main__":
    unittest.main()
