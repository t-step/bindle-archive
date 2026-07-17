import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import validation as v


def codes(findings):
    return [f["code"] for f in findings]


DECISION_A = {
    "id": "context-node:bindle:11111111111111111111111111111111",
    "class": "semantic", "kind": "decision", "label": "A", "status": "current",
}
DECISION_B = {
    "id": "context-node:bindle:22222222222222222222222222222222",
    "class": "semantic", "kind": "decision", "label": "B", "status": "current",
}
LEARNING_B = {
    "id": "context-node:bindle:22222222222222222222222222222222",
    "class": "semantic", "kind": "learning", "label": "B", "status": "current",
}
ISSUE = {"id": "github-issue:thomas-estep/bindle#1", "class": "evidence",
         "kind": "github_issue", "label": "issue", "status": "current"}
PR = {"id": "github-pr:thomas-estep/bindle#1", "class": "evidence",
      "kind": "github_pr", "label": "pr", "status": "current"}


class TestConfig(unittest.TestCase):
    def test_valid_repositoryless_config(self):
        config = {"schema_version": 1,
                   "project_id": "project:" + "a" * 32,
                   "project_slug": "bindle", "repositories": []}
        self.assertEqual(v.validate_config(config), [])

    def test_malformed_project_id(self):
        config = {"schema_version": 1, "project_id": "not-a-project-id",
                   "project_slug": "bindle", "repositories": []}
        self.assertIn("E_CONFIG_MALFORMED_PROJECT_ID", codes(v.validate_config(config)))

    def test_repo_shaped_project_id(self):
        config = {"schema_version": 1, "project_id": "project:thomas-estep/bindle",
                   "project_slug": "bindle", "repositories": []}
        self.assertIn(
            "E_CONFIG_PROJECT_ID_REPO_SHAPED", codes(v.validate_config(config))
        )

    def test_duplicate_alias_rejected(self):
        config = {
            "schema_version": 1, "project_id": "project:" + "a" * 32,
            "project_slug": "bindle",
            "repositories": [
                {"alias": "primary", "binding_id": "repository-binding:" + "b" * 32,
                 "provider": "github", "coordinates": "x/y"},
                {"alias": "primary", "binding_id": "repository-binding:" + "c" * 32,
                 "provider": "github", "coordinates": "x/z"},
            ],
        }
        self.assertIn("E_CONFIG_DUPLICATE_ALIAS", codes(v.validate_config(config)))

    def test_duplicate_binding_id_rejected(self):
        config = {
            "schema_version": 1, "project_id": "project:" + "a" * 32,
            "project_slug": "bindle",
            "repositories": [
                {"alias": "primary", "binding_id": "repository-binding:" + "b" * 32,
                 "provider": "github", "coordinates": "x/y"},
                {"alias": "secondary", "binding_id": "repository-binding:" + "b" * 32,
                 "provider": "github", "coordinates": "x/z"},
            ],
        }
        self.assertIn("E_CONFIG_DUPLICATE_BINDING_ID", codes(v.validate_config(config)))

    def test_multiple_default_rejected(self):
        config = {
            "schema_version": 1, "project_id": "project:" + "a" * 32,
            "project_slug": "bindle",
            "repositories": [
                {"alias": "primary", "binding_id": "repository-binding:" + "b" * 32,
                 "provider": "github", "coordinates": "x/y",
                 "default_for_bare_references": True},
                {"alias": "secondary", "binding_id": "repository-binding:" + "c" * 32,
                 "provider": "github", "coordinates": "x/z",
                 "default_for_bare_references": True},
            ],
        }
        self.assertIn("E_CONFIG_MULTIPLE_DEFAULT", codes(v.validate_config(config)))


class TestNodeChecks(unittest.TestCase):
    def test_reserved_kind_rejected(self):
        node = dict(DECISION_A, kind="architecture_component")
        bundle = {"nodes": [node]}
        self.assertIn("E_NODE_RESERVED_KIND", codes(v.validate_bundle(bundle)))

    def test_malformed_node_id_rejected(self):
        node = dict(DECISION_A, id="context-node:bindle:short")
        bundle = {"nodes": [node]}
        self.assertIn("E_NODE_MALFORMED_ID", codes(v.validate_bundle(bundle)))

    def test_confidence_valid_only_for_assumption_and_tension(self):
        bad = dict(DECISION_A, confidence="high")
        bundle = {"nodes": [bad]}
        self.assertIn(
            "E_NODE_CONFIDENCE_INVALID_KIND", codes(v.validate_bundle(bundle))
        )
        good = {"id": "context-node:bindle:33333333333333333333333333333333",
                 "class": "semantic", "kind": "assumption", "label": "x",
                 "status": "current", "confidence": "high"}
        self.assertEqual(v.validate_bundle({"nodes": [good]}), [])

    def test_tension_requires_exactly_two_sides(self):
        bad = {"id": "context-node:bindle:44444444444444444444444444444444",
               "class": "semantic", "kind": "tension", "label": "t",
               "status": "current", "confidence": "low",
               "sides": [{"label": "a", "evidence": []}]}
        self.assertIn(
            "E_NODE_TENSION_CARDINALITY",
            codes(v.validate_bundle({"nodes": [bad]})),
        )

    def test_tension_side_may_not_carry_its_own_id(self):
        bad = {"id": "context-node:bindle:55555555555555555555555555555555",
               "class": "semantic", "kind": "tension", "label": "t",
               "status": "current", "confidence": "low",
               "sides": [
                   {"label": "a", "evidence": [], "id": "context-node:bindle:" + "6" * 32},
                   {"label": "b", "evidence": []},
               ]}
        self.assertIn(
            "E_NODE_TENSION_SIDE_IDENTITY",
            codes(v.validate_bundle({"nodes": [bad]})),
        )

    def test_duplicate_node_id_rejected(self):
        bundle = {"nodes": [DECISION_A, dict(DECISION_A, label="dup")]}
        self.assertIn("E_NODE_DUPLICATE_ID", codes(v.validate_bundle(bundle)))


class TestEdgeChecks(unittest.TestCase):
    def _edge(self, **overrides):
        edge = {
            "key": DECISION_A["id"] + "|depends_on|" + DECISION_B["id"],
            "source": DECISION_A["id"], "relationship": "depends_on",
            "target": DECISION_B["id"], "status": "confirmed",
            "origin": "human_judgment", "review_trigger": True, "basis": [],
        }
        edge.update(overrides)
        return edge

    def test_valid_judged_edge_with_matching_judgment(self):
        edge = self._edge()
        judgment = {
            "schema_version": 1, "subject_type": "edge",
            "subject_key": edge["key"], "candidate_key": "candidate:sha256:" + "a" * 64,
            "decision": "accepted", "decided_at": "2026-07-16T00:00:00Z",
        }
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge],
                  "judgments": [judgment]}
        self.assertEqual(v.validate_bundle(bundle), [])

    def test_judgment_required_missing(self):
        edge = self._edge()
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge]}
        self.assertIn(
            "E_EDGE_JUDGMENT_REQUIRED_MISSING", codes(v.validate_bundle(bundle))
        )

    def test_unknown_relationship_rejected(self):
        edge = self._edge(relationship="frobnicates",
                           key=DECISION_A["id"] + "|frobnicates|" + DECISION_B["id"])
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge]}
        self.assertIn(
            "E_EDGE_UNKNOWN_RELATIONSHIP", codes(v.validate_bundle(bundle))
        )

    def test_implements_specifically_rejected(self):
        edge = self._edge(relationship="implements",
                           key=DECISION_A["id"] + "|implements|" + PR["id"],
                           target=PR["id"])
        bundle = {"nodes": [DECISION_A, PR], "edges": [edge]}
        self.assertIn(
            "E_EDGE_RELATIONSHIP_REJECTED", codes(v.validate_bundle(bundle))
        )

    def test_endpoint_illegal(self):
        edge = self._edge(relationship="contains",
                           key="project:" + "a" * 32 + "|contains|" + ISSUE["id"],
                           source="project:" + "a" * 32, target=ISSUE["id"],
                           origin="deterministic",
                           deterministic_source={"kind": "project_membership"})
        project_node = {"id": "project:" + "a" * 32, "class": "project",
                         "kind": None, "label": "p", "status": "current"}
        bundle = {"nodes": [project_node, ISSUE], "edges": [edge]}
        self.assertIn("E_EDGE_ENDPOINT_ILLEGAL", codes(v.validate_bundle(bundle)))

    def test_self_edge_forbidden(self):
        edge = self._edge(source=DECISION_A["id"], target=DECISION_A["id"],
                           key=DECISION_A["id"] + "|depends_on|" + DECISION_A["id"])
        bundle = {"nodes": [DECISION_A], "edges": [edge]}
        self.assertIn(
            "E_EDGE_SELF_EDGE_FORBIDDEN", codes(v.validate_bundle(bundle))
        )

    def test_supersedes_cross_kind_rejected(self):
        edge = self._edge(relationship="supersedes", target=LEARNING_B["id"],
                           key=DECISION_A["id"] + "|supersedes|" + LEARNING_B["id"],
                           origin="deterministic",
                           deterministic_source={"kind": "map_tombstone"})
        bundle = {"nodes": [DECISION_A, LEARNING_B], "edges": [edge]}
        self.assertIn(
            "E_EDGE_ENDPOINT_ILLEGAL", codes(v.validate_bundle(bundle))
        )

    def test_missing_node_ref(self):
        edge = self._edge(target="context-node:bindle:" + "9" * 32,
                           key=DECISION_A["id"] + "|depends_on|context-node:bindle:" + "9" * 32)
        bundle = {"nodes": [DECISION_A], "edges": [edge]}
        self.assertIn(
            "E_EDGE_MISSING_NODE_REF", codes(v.validate_bundle(bundle))
        )

    def test_duplicate_edge_key(self):
        edge = self._edge()
        judgment = {
            "schema_version": 1, "subject_type": "edge",
            "subject_key": edge["key"], "candidate_key": "candidate:sha256:" + "a" * 64,
            "decision": "accepted", "decided_at": "2026-07-16T00:00:00Z",
        }
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge, dict(edge)],
                  "judgments": [judgment]}
        self.assertIn("E_EDGE_DUPLICATE_KEY", codes(v.validate_bundle(bundle)))

    def test_review_trigger_mismatch(self):
        edge = self._edge(review_trigger=False)
        judgment = {
            "schema_version": 1, "subject_type": "edge",
            "subject_key": edge["key"], "candidate_key": "candidate:sha256:" + "a" * 64,
            "decision": "accepted", "decided_at": "2026-07-16T00:00:00Z",
        }
        bundle = {"nodes": [DECISION_A, DECISION_B], "edges": [edge],
                  "judgments": [judgment]}
        self.assertIn(
            "E_EDGE_REVIEW_TRIGGER_MISMATCH", codes(v.validate_bundle(bundle))
        )

    def test_deterministic_authority_missing(self):
        edge = self._edge(relationship="closes", origin="deterministic",
                           source=PR["id"], target=ISSUE["id"],
                           key=PR["id"] + "|closes|" + ISSUE["id"])
        bundle = {"nodes": [PR, ISSUE], "edges": [edge]}
        self.assertIn(
            "E_EDGE_DETERMINISTIC_AUTHORITY_MISSING",
            codes(v.validate_bundle(bundle)),
        )

    def test_deterministic_authority_present_is_valid(self):
        edge = self._edge(relationship="closes", origin="deterministic",
                           source=PR["id"], target=ISSUE["id"],
                           key=PR["id"] + "|closes|" + ISSUE["id"],
                           review_trigger=False,
                           deterministic_source={"kind": "github_closure"})
        bundle = {"nodes": [PR, ISSUE], "edges": [edge]}
        self.assertEqual(v.validate_bundle(bundle), [])


class TestDeterminism(unittest.TestCase):
    def test_finding_order_is_stable_across_repeated_runs(self):
        node = dict(DECISION_A, kind="architecture_component", confidence="high")
        bundle = {"nodes": [node]}
        first = v.validate_bundle(bundle)
        second = v.validate_bundle(bundle)
        self.assertEqual(first, second)

    def test_findings_do_not_stop_at_first_error(self):
        node = dict(DECISION_A, kind="architecture_component", confidence="high")
        findings = v.validate_bundle({"nodes": [node]})
        self.assertGreaterEqual(len(findings), 2)


if __name__ == "__main__":
    unittest.main()
