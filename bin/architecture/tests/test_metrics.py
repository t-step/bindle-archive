"""Bindle-computed structural metrics (#229 child C, slice C1, epic #141).

The frozen contract this exercises: ABSENCE IS NEVER ZERO. A capability
nobody could observe is not a capability observed to be empty -- per entity,
not merely per graph -- and cross-binding aggregation propagates
unavailable/partial rather than summing a missing contribution as 0. The
worked failure #141 names is a real 40k-line subsystem reading as
"fan-in: 0, fan-out: 0", falling under an evidence threshold, and vanishing
from the map with no marker anywhere.

Two further properties:

BANDS ARE ABSOLUTE, NOT QUANTILES. A band boundary is a fixed cut point, so
an entity's band depends only on its own metric. Under quantiles, adding an
unrelated file moves other entities across bands, and the churn that F's
guard keeps out of note BYTES re-enters through note EXISTENCE.

METRICS ARE PURE. The graph arrives as an argument, already loaded. Nothing
here reads a document, a filesystem, or a provider.

The corpus is literal hand-authored data in the shape graphset.load_set
returns -- deliberately not built by calling load_set. A corpus, a validator
and a writer that all route through one implementation prove agreement, not
correctness.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import metrics

# ---------------------------------------------------------------- corpus

B1 = "binding:" + "1" * 32
B2 = "binding:" + "2" * 32

FULL_CAPS = ["contains", "imports", "depends_on", "calls", "tests"]


def _cover(capabilities, status="observed", prefix=""):
    return [
        {"path_prefix": prefix, "capability": capability, "status": status}
        for capability in capabilities
    ]


def _binding(capabilities, status="loaded", coverage=None):
    return {
        "status": status,
        "freshness": "current",
        "capabilities": list(capabilities),
        "coverage": _cover(capabilities) if coverage is None else coverage,
    }


def _q(binding_id, value):
    return binding_id + "::" + value


# Four files in one binding. auth/session.py is imported by two others and
# imports one: fan-in 2, fan-out 1. Every number below is hand-counted.
ONE_BINDING = {
    "bindings": {B1: _binding(FULL_CAPS)},
    "facts": {
        "files": {
            _q(B1, "bin/auth/session.py"): {
                "path": "bin/auth/session.py", "binding_id": B1},
            _q(B1, "bin/auth/tokens.py"): {
                "path": "bin/auth/tokens.py", "binding_id": B1},
            _q(B1, "bin/api/login.py"): {
                "path": "bin/api/login.py", "binding_id": B1},
            _q(B1, "bin/api/logout.py"): {
                "path": "bin/api/logout.py", "binding_id": B1},
        },
        "symbols": {
            _q(B1, "sym:SessionStore"): {
                "id": "sym:SessionStore", "name": "SessionStore",
                "kind": "class", "path": "bin/auth/session.py",
                "binding_id": B1},
            _q(B1, "sym:issue_token"): {
                "id": "sym:issue_token", "name": "issue_token",
                "kind": "function", "path": "bin/auth/tokens.py",
                "binding_id": B1},
            _q(B1, "sym:login"): {
                "id": "sym:login", "name": "login", "kind": "function",
                "path": "bin/api/login.py", "binding_id": B1},
            _q(B1, "sym:logout"): {
                "id": "sym:logout", "name": "logout", "kind": "function",
                "path": "bin/api/logout.py", "binding_id": B1},
        },
        "edges": [
            {"type": "imports", "source": _q(B1, "bin/api/login.py"),
             "target": _q(B1, "bin/auth/session.py"), "binding_id": B1},
            {"type": "imports", "source": _q(B1, "bin/api/logout.py"),
             "target": _q(B1, "bin/auth/session.py"), "binding_id": B1},
            {"type": "imports", "source": _q(B1, "bin/auth/session.py"),
             "target": _q(B1, "bin/auth/tokens.py"), "binding_id": B1},
            {"type": "calls", "source": _q(B1, "sym:login"),
             "target": _q(B1, "sym:SessionStore"), "binding_id": B1},
        ],
    },
    "findings": [],
}

SESSION = "bin/auth/session.py"


def _without_capability(graph, capability):
    """The same graph with one capability unadvertised and its edges gone."""
    caps = [c for c in FULL_CAPS if c != capability]
    return {
        "bindings": {B1: _binding(caps)},
        "facts": {
            "files": dict(graph["facts"]["files"]),
            "symbols": dict(graph["facts"]["symbols"]),
            "edges": [e for e in graph["facts"]["edges"]
                      if e["type"] != capability],
        },
        "findings": [],
    }


# Two bindings. B2 advertises no `calls` and no `imports` at all, so its
# contribution to a shared component is unavailable, not zero.
TWO_BINDINGS = {
    "bindings": {
        B1: _binding(FULL_CAPS),
        B2: _binding(["contains"]),
    },
    "facts": {
        "files": dict(
            ONE_BINDING["facts"]["files"],
            **{_q(B2, "svc/handler.go"): {
                "path": "svc/handler.go", "binding_id": B2}}
        ),
        "symbols": dict(ONE_BINDING["facts"]["symbols"]),
        "edges": list(ONE_BINDING["facts"]["edges"]),
    },
    "findings": [],
}


class Bands(unittest.TestCase):
    def test_band_boundaries_are_absolute_cut_points(self):
        self.assertTrue(metrics.BANDS)
        values = [floor for _name, floor in metrics.BANDS]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[0], 0)

    def test_band_of_none_is_unknown_not_the_lowest_band(self):
        self.assertEqual(metrics.band(None), "unknown")

    def test_unknown_is_not_a_band_floor(self):
        self.assertNotIn("unknown", [name for name, _floor in metrics.BANDS])

    def test_band_is_stable_regardless_of_other_entities(self):
        # The quantile trap: this must be a pure function of one value.
        self.assertEqual(metrics.band(7), metrics.band(7))

    def test_cut_points_are_inclusive_floors(self):
        # Pins the boundary itself: a floor belongs to its own band. Without
        # this, `>=` and `>` are indistinguishable and every band silently
        # shifts by one.
        for name, floor in metrics.BANDS:
            self.assertEqual(metrics.band(floor), name)

    def test_a_value_below_a_floor_stays_in_the_lower_band(self):
        names = [name for name, _floor in metrics.BANDS]
        for index, (_name, floor) in enumerate(metrics.BANDS):
            if index == 0:
                continue
            self.assertEqual(metrics.band(floor - 1), names[index - 1])

    def test_bands_are_monotonic_in_value(self):
        names = [name for name, _floor in metrics.BANDS]
        seen = [names.index(metrics.band(v)) for v in (0, 1, 5, 20, 100, 5000)]
        self.assertEqual(seen, sorted(seen))


class Measurement(unittest.TestCase):
    def test_observed_measurement_carries_an_exact_value(self):
        m = metrics.measurement(3, "observed")
        self.assertEqual(m["value"], 3)
        self.assertEqual(m["lower_bound"], 3)
        self.assertEqual(m["coverage"], "observed")

    def test_partial_measurement_has_no_exact_value_only_a_lower_bound(self):
        m = metrics.measurement(40, "partial")
        self.assertIsNone(m["value"])
        self.assertEqual(m["lower_bound"], 40)
        self.assertEqual(m["coverage"], "partial")

    def test_unknown_measurement_is_none_never_zero(self):
        m = metrics.measurement(0, "unknown")
        self.assertIsNone(m["value"])
        self.assertIsNone(m["lower_bound"])
        self.assertEqual(m["band"], "unknown")

    def test_partial_bands_from_its_lower_bound(self):
        self.assertEqual(
            metrics.measurement(40, "partial")["band"], metrics.band(40)
        )

    def test_observed_zero_stays_zero(self):
        # The other half of absence-vs-zero: a genuinely observed 0 must not
        # be laundered into "unknown" either.
        m = metrics.measurement(0, "observed")
        self.assertEqual(m["value"], 0)
        self.assertEqual(m["coverage"], "observed")


class Aggregation(unittest.TestCase):
    def test_all_observed_parts_sum_exactly(self):
        agg = metrics.aggregate(
            [metrics.measurement(40, "observed"),
             metrics.measurement(2, "observed")]
        )
        self.assertEqual(agg["value"], 42)
        self.assertEqual(agg["coverage"], "observed")

    def test_an_unknown_part_never_sums_as_zero(self):
        agg = metrics.aggregate(
            [metrics.measurement(40, "observed"),
             metrics.measurement(0, "unknown")]
        )
        self.assertIsNone(agg["value"])
        self.assertEqual(agg["lower_bound"], 40)
        self.assertEqual(agg["coverage"], "partial")

    def test_all_unknown_parts_aggregate_to_unknown(self):
        agg = metrics.aggregate(
            [metrics.measurement(0, "unknown"),
             metrics.measurement(0, "unknown")]
        )
        self.assertEqual(agg["coverage"], "unknown")
        self.assertIsNone(agg["lower_bound"])

    def test_a_partial_part_makes_the_aggregate_partial(self):
        agg = metrics.aggregate(
            [metrics.measurement(40, "observed"),
             metrics.measurement(2, "partial")]
        )
        self.assertEqual(agg["coverage"], "partial")
        self.assertEqual(agg["lower_bound"], 42)

    def test_no_parts_is_unknown_not_zero(self):
        self.assertEqual(metrics.aggregate([])["coverage"], "unknown")

    def test_aggregation_is_order_independent(self):
        a = metrics.measurement(40, "observed")
        b = metrics.measurement(0, "unknown")
        self.assertEqual(metrics.aggregate([a, b]), metrics.aggregate([b, a]))


class ComputedSignals(unittest.TestCase):
    def setUp(self):
        self.result = metrics.compute(ONE_BINDING)
        self.entities = self.result["entities"]

    def test_every_kept_file_gets_an_entity(self):
        self.assertEqual(
            sorted(self.entities),
            ["bin/api/login.py", "bin/api/logout.py",
             "bin/auth/session.py", "bin/auth/tokens.py"],
        )

    def test_fan_in_counts_distinct_dependents(self):
        self.assertEqual(self.entities[SESSION]["fan_in"]["value"], 2)

    def test_fan_out_counts_distinct_dependencies(self):
        self.assertEqual(self.entities[SESSION]["fan_out"]["value"], 1)

    def test_symbol_edges_fold_into_their_file(self):
        # The calls edge is symbol-to-symbol; login.py must still read as a
        # dependent of session.py through it.
        self.assertEqual(
            self.entities["bin/api/login.py"]["fan_out"]["value"], 1
        )

    def test_a_file_with_no_edges_reads_as_observed_zero(self):
        tokens = self.entities["bin/auth/tokens.py"]
        self.assertEqual(tokens["fan_out"]["value"], 0)
        self.assertEqual(tokens["fan_out"]["coverage"], "observed")

    def test_self_edges_are_not_counted(self):
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": {
                "files": dict(ONE_BINDING["facts"]["files"]),
                "symbols": {},
                "edges": [{"type": "imports", "source": _q(B1, SESSION),
                           "target": _q(B1, SESSION), "binding_id": B1}],
            },
            "findings": [],
        }
        self.assertEqual(
            metrics.compute(graph)["entities"][SESSION]["fan_in"]["value"], 0
        )

    def test_neighborhood_is_repo_relative_paths(self):
        for path in self.entities[SESSION]["neighborhood"]:
            self.assertFalse(path.startswith(B1))
            self.assertNotIn("::", path)

    def test_neighborhood_is_sorted_and_excludes_self(self):
        hood = self.entities[SESSION]["neighborhood"]
        self.assertEqual(hood, sorted(hood))
        self.assertNotIn(SESSION, hood)

    def test_neighborhood_holds_both_directions_of_adjacency(self):
        self.assertEqual(
            self.entities[SESSION]["neighborhood"],
            ["bin/api/login.py", "bin/api/logout.py", "bin/auth/tokens.py"],
        )

    def test_a_call_only_neighbor_is_not_in_the_neighborhood(self):
        # The neighborhood signal carries matcher weight 0.2. Built from
        # `calls`, it vanishes wholesale when a provider drops that
        # capability -- a signal disappearing on a capability toggle is
        # PT16's churn failure. So call-only adjacency is deliberately not
        # neighborhood, and this fixture has no import to hide behind.
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": {
                "files": {
                    _q(B1, "a.py"): {"path": "a.py", "binding_id": B1},
                    _q(B1, "b.py"): {"path": "b.py", "binding_id": B1},
                },
                "symbols": {},
                "edges": [{"type": "calls", "source": _q(B1, "a.py"),
                           "target": _q(B1, "b.py"), "binding_id": B1}],
            },
            "findings": [],
        }
        entities = metrics.compute(graph)["entities"]
        self.assertEqual(entities["a.py"]["neighborhood"], [])
        # Still a real dependency, though -- only the neighborhood excludes it.
        self.assertEqual(entities["a.py"]["fan_out"]["value"], 1)

    def test_the_neighborhood_survives_losing_the_calls_capability(self):
        full = metrics.compute(ONE_BINDING)["entities"]
        degraded = metrics.compute(
            _without_capability(ONE_BINDING, "calls")
        )["entities"]
        for path, entity in full.items():
            self.assertEqual(
                degraded[path]["neighborhood"], entity["neighborhood"]
            )

    def test_blast_radius_is_the_transitive_dependent_closure(self):
        # tokens.py is imported by session.py, which two api files import.
        self.assertEqual(
            self.entities["bin/auth/tokens.py"]["blast_radius"]["value"], 3
        )

    def test_blast_radius_terminates_on_a_cycle(self):
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": {
                "files": {
                    _q(B1, "a.py"): {"path": "a.py", "binding_id": B1},
                    _q(B1, "b.py"): {"path": "b.py", "binding_id": B1},
                },
                "symbols": {},
                "edges": [
                    {"type": "imports", "source": _q(B1, "a.py"),
                     "target": _q(B1, "b.py"), "binding_id": B1},
                    {"type": "imports", "source": _q(B1, "b.py"),
                     "target": _q(B1, "a.py"), "binding_id": B1},
                ],
            },
            "findings": [],
        }
        entities = metrics.compute(graph)["entities"]
        self.assertEqual(entities["a.py"]["blast_radius"]["value"], 1)

    def test_every_metric_carries_a_band(self):
        for entity in self.entities.values():
            for name in ("fan_in", "fan_out", "blast_radius"):
                self.assertIn(entity[name]["band"], metrics.BAND_NAMES)

    def test_output_is_identical_across_edge_orderings(self):
        shuffled = {
            "bindings": ONE_BINDING["bindings"],
            "facts": dict(
                ONE_BINDING["facts"],
                edges=list(reversed(ONE_BINDING["facts"]["edges"])),
            ),
            "findings": [],
        }
        self.assertEqual(metrics.compute(shuffled), self.result)

    def test_applied_thresholds_and_bands_are_echoed(self):
        # #229 requires caps/thresholds "enforced and observable"; these are
        # module constants, so the result envelope is where they show up.
        self.assertEqual(self.result["applied"]["bands"], list(metrics.BANDS))


class CapabilityDegradation(unittest.TestCase):
    def test_no_dependency_capability_at_all_reads_as_unknown_not_zero(self):
        # The #141 failure in full: a real subsystem must not read as
        # "fan-in: 0, fan-out: 0" merely because nobody could look.
        graph = {
            "bindings": {B1: _binding(["contains"])},
            "facts": dict(ONE_BINDING["facts"], edges=[]),
            "findings": [],
        }
        entity = metrics.compute(graph)["entities"][SESSION]
        self.assertIsNone(entity["fan_in"]["value"])
        self.assertEqual(entity["fan_in"]["coverage"], "unknown")
        self.assertEqual(entity["fan_in"]["band"], "unknown")

    def test_losing_one_of_several_capabilities_reads_as_partial(self):
        # `calls` survives, so 1 dependent is still observed -- that is a
        # lower bound, not the answer, and not an unknown either.
        graph = _without_capability(ONE_BINDING, "imports")
        entity = metrics.compute(graph)["entities"][SESSION]
        self.assertEqual(entity["fan_in"]["coverage"], "partial")
        self.assertIsNone(entity["fan_in"]["value"])
        self.assertEqual(entity["fan_in"]["lower_bound"], 1)

    def test_a_partially_covered_subtree_reads_as_partial(self):
        coverage = _cover(FULL_CAPS) + [
            {"path_prefix": "bin/auth", "capability": "imports",
             "status": "partial_parse_failure"}
        ]
        graph = {
            "bindings": {B1: _binding(FULL_CAPS, coverage=coverage)},
            "facts": ONE_BINDING["facts"],
            "findings": [],
        }
        entity = metrics.compute(graph)["entities"][SESSION]
        self.assertEqual(entity["fan_in"]["coverage"], "partial")
        self.assertIsNone(entity["fan_in"]["value"])

    def test_a_mixed_capability_aggregate_never_fabricates_a_zero(self):
        entity = metrics.compute(TWO_BINDINGS)["entities"]["svc/handler.go"]
        self.assertIsNone(entity["fan_in"]["value"])
        self.assertNotEqual(entity["fan_in"]["band"], metrics.band(0))

    def test_an_unloaded_binding_does_not_zero_the_other(self):
        graph = {
            "bindings": {
                B1: _binding(FULL_CAPS),
                B2: {"status": "unavailable", "freshness": "freshness_unknown",
                     "capabilities": [], "coverage": []},
            },
            "facts": ONE_BINDING["facts"],
            "findings": [],
        }
        entity = metrics.compute(graph)["entities"][SESSION]
        self.assertEqual(entity["fan_in"]["lower_bound"], 2)

    def test_losing_a_capability_never_raises_a_band(self):
        # Monotonic degradation at the metric level: less capability may
        # lower a band or make it unknown, never raise it.
        def rank(name):
            return -1 if name == "unknown" else metrics.BAND_NAMES.index(name)

        full = metrics.compute(ONE_BINDING)["entities"]
        degraded = metrics.compute(
            _without_capability(ONE_BINDING, "calls")
        )["entities"]
        for path, entity in full.items():
            for name in ("fan_in", "fan_out", "blast_radius"):
                self.assertLessEqual(
                    rank(degraded[path][name]["band"]),
                    rank(entity[name]["band"]),
                )

    def test_a_binding_that_could_not_load_is_reported_not_silent(self):
        graph = {
            "bindings": {
                B1: _binding(FULL_CAPS),
                B2: {"status": "unavailable", "freshness": "freshness_unknown",
                     "capabilities": [], "coverage": []},
            },
            "facts": ONE_BINDING["facts"],
            "findings": [],
        }
        self.assertEqual(
            metrics.compute(graph)["bindings"][B2]["status"], "unavailable"
        )


class ExclusionIntegration(unittest.TestCase):
    def test_an_excluded_path_never_appears_as_an_entity(self):
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": dict(
                ONE_BINDING["facts"],
                files=dict(
                    ONE_BINDING["facts"]["files"],
                    **{_q(B1, "vendor/pkg/errors.go"): {
                        "path": "vendor/pkg/errors.go", "binding_id": B1}}
                ),
            ),
            "findings": [],
        }
        result = metrics.compute(graph)
        self.assertNotIn("vendor/pkg/errors.go", result["entities"])
        self.assertIn(
            "vendor/pkg/errors.go",
            [entry["path"] for entry in result["excluded"]],
        )

    def test_an_excluded_path_never_appears_in_a_neighborhood(self):
        graph = {
            "bindings": {B1: _binding(FULL_CAPS)},
            "facts": {
                "files": dict(
                    ONE_BINDING["facts"]["files"],
                    **{_q(B1, "vendor/pkg/errors.go"): {
                        "path": "vendor/pkg/errors.go", "binding_id": B1}}
                ),
                "symbols": {},
                "edges": [
                    {"type": "imports", "source": _q(B1, SESSION),
                     "target": _q(B1, "vendor/pkg/errors.go"),
                     "binding_id": B1},
                ],
            },
            "findings": [],
        }
        entity = metrics.compute(graph)["entities"][SESSION]
        self.assertEqual(entity["neighborhood"], [])
        self.assertEqual(entity["fan_out"]["value"], 0)

    def test_a_denylisted_path_is_excluded_from_metrics(self):
        result = metrics.compute(ONE_BINDING, denylist=["auth"])
        self.assertNotIn(SESSION, result["entities"])

    def test_configured_exclusions_reach_the_filter(self):
        result = metrics.compute(ONE_BINDING, configured=["bin/api/"])
        self.assertEqual(
            sorted(result["entities"]),
            ["bin/auth/session.py", "bin/auth/tokens.py"],
        )


if __name__ == "__main__":
    unittest.main()
