import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import proposals, canonical
from context_graph.tests import fixtures_184 as fx


class ValidateEdgeProposal(unittest.TestCase):
    def test_valid_semantic_edge_produces_candidate(self):
        out = proposals.validate_edge_proposal(fx.edge_proposal(), fx.preview())
        self.assertEqual(out["findings"], [])
        c = out["candidate"]
        self.assertEqual(c["subject_type"], "edge")
        self.assertEqual(c["candidate_origin"], "validated_proposal")
        self.assertEqual(c["validation_status"], "valid")
        self.assertEqual(c["source_class"], "semantic")
        self.assertEqual(c["source_kind"], "decision")
        self.assertEqual(c["target_kind"], "learning")
        self.assertTrue(c["candidate_key"].startswith("candidate:sha256:"))
        # Key equals the frozen primitive over the resolved ids + basis.
        self.assertEqual(
            c["candidate_key"],
            canonical.candidate_key(fx.DECISION_A["id"], "supports", fx.LEARNING_B["id"], []),
        )
        self.assertEqual(out["subject_key"],
                         canonical.edge_subject_key(fx.DECISION_A["id"], "supports", fx.LEARNING_B["id"]))

    def test_unknown_endpoint_is_rejected_without_a_key(self):
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(target="context-node:bindle:nope"), fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_UNKNOWN_ENDPOINT", [f["code"] for f in out["findings"]])

    def test_illegal_endpoint_is_rejected_before_key_construction(self):
        # 'supersedes' requires same kind; decision -> learning is illegal.
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(relationship="supersedes"), fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_ILLEGAL_ENDPOINT", [f["code"] for f in out["findings"]])

    def test_advisory_key_mismatch_is_a_precise_failure(self):
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(advisory_key="candidate:sha256:" + "0" * 64), fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_ADVISORY_KEY_MISMATCH", [f["code"] for f in out["findings"]])

    def test_malformed_proposal_missing_field(self):
        bad = {"source": fx.DECISION_A["id"], "relationship": "supports"}  # no target
        out = proposals.validate_edge_proposal(bad, fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_MALFORMED", [f["code"] for f in out["findings"]])

    def test_invalid_basis_entry_rejected(self):
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(basis=[{"kind": "bogus"}]), fx.preview())
        self.assertIsNone(out["candidate"])
        self.assertIn("E_PROPOSAL_BASIS_INVALID", [f["code"] for f in out["findings"]])

    def test_evidence_target_edge_is_legal(self):
        out = proposals.validate_edge_proposal(
            fx.edge_proposal(relationship="implemented_by", target=fx.PR_NODE["id"]),
            fx.preview())
        self.assertEqual(out["findings"], [])
        self.assertEqual(out["candidate"]["target_class"], "evidence")
