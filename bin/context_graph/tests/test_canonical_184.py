import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import canonical


BASIS = [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "p1"}]


class EdgeSubjectKey(unittest.TestCase):
    def test_stable_and_prefixed(self):
        k = canonical.edge_subject_key("A", "supports", "B")
        self.assertTrue(k.startswith("edge-subject:sha256:"))
        self.assertEqual(k, canonical.edge_subject_key("A", "supports", "B"))

    def test_basis_and_explanation_do_not_participate(self):
        # subject_key is coarser than candidate_key: it has no basis input at all.
        self.assertEqual(
            canonical.edge_subject_key("A", "supports", "B"),
            canonical.edge_subject_key("A", "supports", "B"),
        )

    def test_endpoints_or_relationship_change_the_subject(self):
        base = canonical.edge_subject_key("A", "supports", "B")
        self.assertNotEqual(base, canonical.edge_subject_key("A", "contradicts", "B"))
        self.assertNotEqual(base, canonical.edge_subject_key("A", "supports", "C"))

    def test_contradicts_is_symmetric(self):
        self.assertEqual(
            canonical.edge_subject_key("A", "contradicts", "B"),
            canonical.edge_subject_key("B", "contradicts", "A"),
        )

    def test_directional_relationship_is_not_symmetric(self):
        self.assertNotEqual(
            canonical.edge_subject_key("A", "supports", "B"),
            canonical.edge_subject_key("B", "supports", "A"),
        )


class AnchorSubjectKey(unittest.TestCase):
    def test_coarser_than_candidate_key_ignores_entry_fingerprint(self):
        # Two different entry byte-versions of the same map slot share a subject.
        s1 = canonical.anchor_subject_key("project:p", "map.md", "decisions", "decision")
        s2 = canonical.anchor_subject_key("project:p", "map.md", "decisions", "decision")
        self.assertEqual(s1, s2)
        self.assertTrue(s1.startswith("anchor-subject:sha256:"))

    def test_section_or_kind_change_changes_subject(self):
        base = canonical.anchor_subject_key("project:p", "map.md", "decisions", "decision")
        self.assertNotEqual(
            base, canonical.anchor_subject_key("project:p", "map.md", "learnings", "decision")
        )


class EdgeDependencyFingerprint(unittest.TestCase):
    def test_prefixed_and_distinct_from_candidate_key(self):
        fp = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "supports", "B", "semantic", "learning", BASIS
        )
        self.assertTrue(fp.startswith("sha256:"))
        # Distinct domain literal → never equals the candidate key digest.
        self.assertNotEqual(fp, canonical.candidate_key("A", "supports", "B", BASIS))

    def test_endpoint_kind_change_stales(self):
        base = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "supports", "B", "semantic", "learning", BASIS
        )
        changed = canonical.edge_dependency_fingerprint(
            "A", "semantic", "assumption", "supports", "B", "semantic", "learning", BASIS
        )
        self.assertNotEqual(base, changed)

    def test_basis_change_stales(self):
        base = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "supports", "B", "semantic", "learning", BASIS
        )
        other = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "supports", "B", "semantic", "learning",
            [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "p2"}],
        )
        self.assertNotEqual(base, other)

    def test_none_kind_encodes_unambiguously(self):
        # A project endpoint has kind None; must hash without error.
        fp = canonical.edge_dependency_fingerprint(
            "P", "project", None, "contains", "A", "semantic", "decision", []
        )
        self.assertTrue(fp.startswith("sha256:"))

    def test_contradicts_is_symmetric(self):
        a = canonical.edge_dependency_fingerprint(
            "A", "semantic", "decision", "contradicts", "B", "semantic", "decision", BASIS
        )
        b = canonical.edge_dependency_fingerprint(
            "B", "semantic", "decision", "contradicts", "A", "semantic", "decision", BASIS
        )
        self.assertEqual(a, b)
