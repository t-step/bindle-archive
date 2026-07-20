"""Monotonically-degrading clustering and deterministic naming (#229 child
C, slice C2, epic #141).

The frozen contract this exercises: clustering is "capability-set-
deterministic, MONOTONICALLY-DEGRADING (a lost capability may merge/coarsen,
never re-partition)", and "every component has a deterministic human-readable
name; model assistance may only improve it" (R3).

MONOTONICITY IS STRUCTURAL HERE, NOT HOPED FOR. A directory qualifies as a
component boundary when it holds enough internal edge evidence, and each
file joins its DEEPEST qualifying ancestor. Losing a capability removes
edges, which can only un-qualify directories, which can only move files to a
shallower ancestor. Every degraded cluster is therefore a union of full
clusters -- the refinement test below asserts exactly that, which is the
property a modularity optimizer could not have given us.

The corpus is literal hand-authored data. A corpus, a validator and a writer
that all route through one implementation prove agreement, not correctness.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import clustering
from architecture import metrics

B1 = "binding:" + "1" * 32
FULL_CAPS = ["contains", "imports", "depends_on", "calls", "tests"]


def _binding(capabilities):
    return {
        "status": "loaded",
        "freshness": "current",
        "capabilities": list(capabilities),
        "coverage": [{"path_prefix": "", "capability": c, "status": "observed"}
                     for c in capabilities],
    }


def _q(value):
    return B1 + "::" + value


def _file(path):
    return {"path": path, "binding_id": B1}


def _symbol(name, path, kind="function"):
    return {"id": "sym:" + name, "name": name, "kind": kind, "path": path,
            "binding_id": B1}


def _edge(kind, source, target):
    return {"type": kind, "source": _q(source), "target": _q(target),
            "binding_id": B1}


# Two cohesive directories plus a loose root script. Each directory holds one
# internal import, which is the evidence that makes it a boundary; main.py
# has no directory of its own and belongs to the root cluster.
PATHS = [
    "bin/auth/session.py",
    "bin/auth/tokens.py",
    "bin/render/html.py",
    "bin/render/markdown.py",
    "main.py",
]

GRAPH = {
    "bindings": {B1: _binding(FULL_CAPS)},
    "facts": {
        "files": {_q(p): _file(p) for p in PATHS},
        "symbols": {
            _q("sym:SessionStore"): _symbol(
                "SessionStore", "bin/auth/session.py", "class"),
            _q("sym:issue_token"): _symbol("issue_token", "bin/auth/tokens.py"),
            _q("sym:render_html"): _symbol("render_html", "bin/render/html.py"),
            _q("sym:render_md"): _symbol(
                "render_md", "bin/render/markdown.py"),
            _q("sym:main"): _symbol("main", "main.py"),
        },
        "edges": [
            _edge("imports", "bin/auth/session.py", "bin/auth/tokens.py"),
            _edge("imports", "bin/render/html.py", "bin/render/markdown.py"),
            _edge("imports", "main.py", "bin/auth/session.py"),
        ],
    },
    "findings": [],
}

NO_EDGE_GRAPH = {
    "bindings": {B1: _binding(["contains"])},
    "facts": dict(GRAPH["facts"], edges=[]),
    "findings": [],
}


def _cluster(graph):
    return clustering.cluster(metrics.compute(graph), graph)


def _by_prefix(result):
    return {c["prefix"]: sorted(c["members"]) for c in result["clusters"]}


class Partitioning(unittest.TestCase):
    def setUp(self):
        self.result = _cluster(GRAPH)

    def test_a_cohesive_directory_becomes_its_own_cluster(self):
        self.assertEqual(
            _by_prefix(self.result)["bin/auth"],
            ["bin/auth/session.py", "bin/auth/tokens.py"],
        )

    def test_sibling_directories_do_not_merge(self):
        prefixes = _by_prefix(self.result)
        self.assertIn("bin/auth", prefixes)
        self.assertIn("bin/render", prefixes)

    def test_a_loose_root_file_lands_in_the_root_cluster(self):
        self.assertEqual(_by_prefix(self.result)[""], ["main.py"])

    def test_every_kept_path_lands_in_exactly_one_cluster(self):
        seen = [m for c in self.result["clusters"] for m in c["members"]]
        self.assertEqual(sorted(seen), sorted(PATHS))
        self.assertEqual(len(seen), len(set(seen)))

    def test_clusters_are_ordered_deterministically(self):
        prefixes = [c["prefix"] for c in self.result["clusters"]]
        self.assertEqual(prefixes, sorted(prefixes))

    def test_output_is_identical_across_edge_orderings(self):
        shuffled = {
            "bindings": GRAPH["bindings"],
            "facts": dict(GRAPH["facts"],
                          edges=list(reversed(GRAPH["facts"]["edges"]))),
            "findings": [],
        }
        self.assertEqual(_cluster(shuffled), self.result)

    def test_a_directory_without_internal_evidence_is_not_a_boundary(self):
        # bin/ holds two internal edges, but each lies wholly inside a child;
        # the deepest qualifying ancestor rule must still pick the children.
        self.assertNotIn("bin", _by_prefix(self.result))

    def test_a_single_file_directory_is_not_a_boundary(self):
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": {
                "files": {_q("a/only.py"): _file("a/only.py"),
                          _q("b.py"): _file("b.py")},
                "symbols": {},
                "edges": [_edge("imports", "a/only.py", "b.py")],
            },
            "findings": [],
        }
        self.assertEqual(list(_by_prefix(_cluster(graph))), [""])

    def test_an_excluded_path_never_joins_a_cluster(self):
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": dict(
                GRAPH["facts"],
                files=dict(GRAPH["facts"]["files"],
                           **{_q("vendor/x/y.go"): _file("vendor/x/y.go")}),
            ),
            "findings": [],
        }
        members = [m for c in _cluster(graph)["clusters"] for m in c["members"]]
        self.assertNotIn("vendor/x/y.go", members)


class MonotonicDegradation(unittest.TestCase):
    def test_losing_every_edge_collapses_to_one_cluster(self):
        self.assertEqual(list(_by_prefix(_cluster(NO_EDGE_GRAPH))), [""])

    def test_a_degraded_cluster_is_a_union_of_full_clusters(self):
        # The frozen rule in its testable form: coarsen, never re-partition.
        full = _cluster(GRAPH)["clusters"]
        degraded = _cluster(NO_EDGE_GRAPH)["clusters"]
        for coarse in degraded:
            coarse_members = set(coarse["members"])
            for fine in full:
                fine_members = set(fine["members"])
                overlap = coarse_members & fine_members
                self.assertIn(
                    overlap, (set(), fine_members),
                    "cluster %r splits full cluster %r"
                    % (coarse["prefix"], fine["prefix"]),
                )

    def test_degradation_never_increases_the_cluster_count(self):
        self.assertLessEqual(
            len(_cluster(NO_EDGE_GRAPH)["clusters"]),
            len(_cluster(GRAPH)["clusters"]),
        )

    def test_dropping_one_capability_never_re_partitions(self):
        partial = {
            "bindings": {B1: _binding(["contains", "imports"])},
            "facts": GRAPH["facts"],
            "findings": [],
        }
        full = _cluster(GRAPH)["clusters"]
        for coarse in _cluster(partial)["clusters"]:
            coarse_members = set(coarse["members"])
            for fine in full:
                overlap = coarse_members & set(fine["members"])
                self.assertIn(overlap, (set(), set(fine["members"])))


class Naming(unittest.TestCase):
    def setUp(self):
        self.result = _cluster(GRAPH)
        self.names = {c["prefix"]: c["name"] for c in self.result["clusters"]}

    def test_every_cluster_has_a_non_empty_deterministic_name(self):
        # R3: the deterministic name must always exist. Child I may only
        # improve it, so a cluster with no name would make I load-bearing.
        for cluster in self.result["clusters"]:
            self.assertTrue(cluster["name"])
            self.assertIsInstance(cluster["name"], str)

    def test_name_is_the_dominant_path_segment(self):
        self.assertEqual(self.names["bin/auth"], "auth")
        self.assertEqual(self.names["bin/render"], "render")

    def test_the_root_cluster_has_a_stable_name(self):
        self.assertEqual(self.names[""], clustering.ROOT_CLUSTER_NAME)

    def test_colliding_names_are_disambiguated_deterministically(self):
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": {
                "files": {_q(p): _file(p) for p in [
                    "bin/auth/a.py", "bin/auth/b.py",
                    "src/auth/a.py", "src/auth/b.py"]},
                "symbols": {},
                "edges": [
                    _edge("imports", "bin/auth/a.py", "bin/auth/b.py"),
                    _edge("imports", "src/auth/a.py", "src/auth/b.py"),
                ],
            },
            "findings": [],
        }
        names = sorted(c["name"] for c in _cluster(graph)["clusters"])
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names, ["bin/auth", "src/auth"])

    def test_names_do_not_depend_on_input_order(self):
        reversed_files = dict(
            reversed(list(GRAPH["facts"]["files"].items()))
        )
        graph = {
            "bindings": GRAPH["bindings"],
            "facts": dict(GRAPH["facts"], files=reversed_files),
            "findings": [],
        }
        self.assertEqual(
            {c["prefix"]: c["name"] for c in _cluster(graph)["clusters"]},
            self.names,
        )


class ClusterMetrics(unittest.TestCase):
    def test_a_cluster_carries_aggregated_banded_metrics(self):
        result = _cluster(GRAPH)
        for cluster in result["clusters"]:
            for name in ("fan_in", "fan_out", "blast_radius"):
                self.assertIn("band", cluster["metrics"][name])

    def test_cluster_metrics_count_only_boundary_crossing_edges(self):
        # Summing member fan-in would count bin/auth's internal import twice
        # and read a cohesive component as a hub. Only main.py -> session.py
        # crosses the boundary.
        auth = {c["prefix"]: c for c in _cluster(GRAPH)["clusters"]}["bin/auth"]
        self.assertEqual(auth["metrics"]["fan_in"]["value"], 1)
        self.assertEqual(auth["metrics"]["fan_out"]["value"], 0)

    def test_cluster_metrics_never_fabricate_a_zero(self):
        result = _cluster(NO_EDGE_GRAPH)
        entry = result["clusters"][0]["metrics"]["fan_in"]
        self.assertIsNone(entry["value"])
        self.assertEqual(entry["coverage"], "unknown")

    def test_applied_constants_are_echoed(self):
        applied = _cluster(GRAPH)["applied"]
        self.assertEqual(
            applied["min_internal_edges"], clustering.MIN_INTERNAL_EDGES
        )

    def test_the_evidence_floor_actually_binds(self):
        # Raising the floor above the fixture's evidence must coarsen the
        # partition. Without this the constant is decorative: `_qualifying`
        # only ever visits directories that already have an edge, so a floor
        # of 0 and a floor of 1 are indistinguishable.
        original = clustering.MIN_INTERNAL_EDGES
        try:
            clustering.MIN_INTERNAL_EDGES = 2
            raised = _by_prefix(_cluster(GRAPH))
        finally:
            clustering.MIN_INTERNAL_EDGES = original
        # bin/auth and bin/render hold one internal edge each and drop out;
        # bin holds both and survives. The partition coarsens rather than
        # collapsing, which is the floor binding AND monotonicity holding.
        self.assertEqual(sorted(raised), ["", "bin"])
        self.assertEqual(
            raised["bin"],
            ["bin/auth/session.py", "bin/auth/tokens.py",
             "bin/render/html.py", "bin/render/markdown.py"],
        )


if __name__ == "__main__":
    unittest.main()
