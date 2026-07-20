"""Ranking, caps and over-cap retention (#229 child C, slice C3, epic #141).

The frozen contract this exercises: "The cap binds CREATION. A projected node
that falls out of the ranked set is RETAINED, marked `over_cap`, and excluded
from further refresh until the operator stales it via G. It is never deleted
and never auto-staled. RANKING USES THE SAME BUCKETED/BANDED METRIC VALUES as
F's churn guard, not raw numbers -- otherwise a rank swap at the cap boundary
mints one note and strands another every few commits."

THE BANDED-RANKING TEST IS THE LOAD-BEARING ONE. `a_raw_change_inside_one_band
_does_not_reorder` is the assertion that would catch a ranking rewritten
against `value` instead of `band`: every other test in this file passes
identically under both readings, because a hand-authored corpus tends to put
its raw values in different bands anyway. That test is built so the raw
numbers swap while the bands do not.

The corpus is literal hand-authored data. A corpus, a validator and a writer
that all route through one implementation prove agreement, not correctness.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import candidates
from architecture import metrics
from architecture import ranking


def _m(value, coverage="observed"):
    return metrics.measurement(value, coverage)


def _component(key, blast=0, fan_in=0, fan_out=0, coverage="observed"):
    """A component candidate carrying only what ranking reads."""
    return {
        "candidate_key": candidates.COMPONENT_KEY_PREFIX + key,
        "projection_type": "arch_component",
        "source_paths": [key + "/a.py"],
        "symbol_names": [],
        "neighborhood": [],
        "name": key,
        "metrics": {
            "blast_radius": _m(blast, coverage),
            "fan_in": _m(fan_in, coverage),
            "fan_out": _m(fan_out, coverage),
        },
        "entry_points": [],
        "bindings": [],
        "member_count": 1,
    }


def _map_candidate():
    return {
        "candidate_key": candidates.CODEBASE_MAP_KEY,
        "projection_type": "arch_codebase_map",
        "source_paths": ["."],
        "symbol_names": [],
        "neighborhood": [],
        "name": candidates.CODEBASE_MAP_KEY,
        "metrics": {},
        "entry_points": [],
        "bindings": [],
        "member_count": 1,
    }


def _keys(entries):
    return [entry["candidate_key"] for entry in entries]


def _entry(result, key):
    for entry in result["ranked"]:
        if entry["candidate_key"] == key:
            return entry
    raise AssertionError("no ranked entry for " + key)


class BandOrder(unittest.TestCase):
    def test_band_order_covers_every_metrics_band(self):
        self.assertEqual(
            set(ranking.BAND_ORDER),
            set(metrics.BAND_NAMES) | {metrics.UNKNOWN_BAND},
        )

    def test_unknown_ranks_below_none(self):
        # An unobserved metric must never win a cap slot over an observed
        # zero. This is the fabricated-zero failure inverted: absence read as
        # strength instead of as zero.
        self.assertLess(
            ranking.BAND_ORDER.index(metrics.UNKNOWN_BAND),
            ranking.BAND_ORDER.index("none"),
        )

    def test_bands_ascend_by_strength(self):
        ordinals = [ranking.BAND_ORDER.index(name)
                    for name in metrics.BAND_NAMES]
        self.assertEqual(ordinals, sorted(ordinals))


class RankOrder(unittest.TestCase):
    def test_higher_blast_radius_ranks_first(self):
        result = ranking.rank([
            _component("small", blast=1),
            _component("large", blast=50),
        ])
        self.assertEqual(_keys(result["ranked"])[0], "component:large")

    def test_fan_in_breaks_a_blast_radius_tie(self):
        # The winner is named so that the KEY tie-break would order these
        # the other way. A fixture whose names agree with the expected order
        # passes even when the signal is not consulted at all.
        result = ranking.rank([
            _component("alpha", blast=50, fan_in=1),
            _component("zeta", blast=50, fan_in=50),
        ])
        self.assertEqual(_keys(result["ranked"])[0], "component:zeta")

    def test_fan_out_breaks_a_blast_radius_and_fan_in_tie(self):
        result = ranking.rank([
            _component("alpha", blast=50, fan_in=50, fan_out=1),
            _component("zeta", blast=50, fan_in=50, fan_out=50),
        ])
        self.assertEqual(_keys(result["ranked"])[0], "component:zeta")

    def test_candidate_key_breaks_a_full_tie_ascending(self):
        result = ranking.rank([
            _component("zebra", blast=50, fan_in=50, fan_out=50),
            _component("alpha", blast=50, fan_in=50, fan_out=50),
        ])
        self.assertEqual(
            _keys(result["ranked"])[:2],
            ["component:alpha", "component:zebra"],
        )

    def test_an_unknown_metric_ranks_below_an_observed_zero(self):
        result = ranking.rank([
            _component("unobserved", blast=None, coverage="unknown"),
            _component("observed_zero", blast=0),
        ])
        self.assertEqual(_keys(result["ranked"])[0], "component:observed_zero")

    def test_ranks_are_consecutive_from_zero(self):
        result = ranking.rank([
            _component("a", blast=50),
            _component("b", blast=5),
            _component("c", blast=0),
        ])
        self.assertEqual([e["rank"] for e in result["ranked"]], [0, 1, 2])

    def test_raw_value_does_not_order_within_a_band(self):
        # THE FREEZE, STATED AS A TEST. 20 and 99 are both "high", so these
        # tie on bands and fall to the key tie-break. Ranked on raw numbers
        # `b` would lead. The earlier draft of this test compared two runs
        # whose raw values both moved the same way -- it read like the freeze
        # and passed identically against a raw-valued ranking, which the
        # mutation run caught.
        result = ranking.rank([
            _component("a", blast=20), _component("b", blast=99),
        ])
        self.assertEqual(_keys(result["ranked"]),
                         ["component:a", "component:b"])

    def test_a_raw_change_inside_one_band_does_not_reorder(self):
        before = ranking.rank([
            _component("a", blast=20), _component("b", blast=19),
        ])
        after = ranking.rank([
            _component("a", blast=99), _component("b", blast=5),
        ])
        self.assertEqual(_keys(before["ranked"]), _keys(after["ranked"]))

    def test_a_candidate_with_no_metrics_ranks_below_an_observed_zero(self):
        # `unknown` and `none` must stay distinct for a candidate carrying no
        # metrics map at all, not only for one whose coverage is unknown.
        # The key tie-break would order these the other way.
        bare = _component("alpha")
        bare["metrics"] = {}
        result = ranking.rank([bare, _component("zeta", blast=0)])
        self.assertEqual(_keys(result["ranked"])[0], "component:zeta")

    def test_a_band_crossing_does_reorder(self):
        # The complement of the test above: banding must not flatten every
        # difference away, or ranking would degenerate to key order.
        result = ranking.rank([
            _component("a", blast=19),   # moderate
            _component("b", blast=20),   # high
        ])
        self.assertEqual(_keys(result["ranked"])[0], "component:b")


class Cap(unittest.TestCase):
    def test_no_cap_leaves_nothing_over_cap(self):
        result = ranking.rank(
            [_component("a"), _component("b")], cap=None)
        self.assertEqual(result["over_cap"], [])

    def test_cap_keeps_the_top_ranked_components(self):
        result = ranking.rank([
            _component("a", blast=50),
            _component("b", blast=5),
            _component("c", blast=0),
        ], cap=2)
        self.assertEqual(
            [e["candidate_key"] for e in result["ranked"] if not e["over_cap"]],
            ["component:a", "component:b"],
        )

    def test_an_over_cap_candidate_is_retained_not_dropped(self):
        # never-auto-delete: the cap binds creation, so the record stays in
        # the output and is merely marked.
        result = ranking.rank([
            _component("a", blast=50), _component("b", blast=0),
        ], cap=1)
        self.assertIn("component:b", _keys(result["ranked"]))
        self.assertTrue(_entry(result, "component:b")["over_cap"])

    def test_over_cap_list_agrees_with_the_ranked_entries(self):
        result = ranking.rank([
            _component("a", blast=50),
            _component("b", blast=5),
            _component("c", blast=0),
        ], cap=1)
        marked = sorted(e["candidate_key"] for e in result["ranked"]
                        if e["over_cap"])
        self.assertEqual(result["over_cap"], marked)

    def test_a_cap_of_zero_puts_every_component_over_cap(self):
        result = ranking.rank(
            [_component("a"), _component("b")], cap=0)
        self.assertEqual(result["over_cap"],
                         ["component:a", "component:b"])

    def test_a_cap_above_the_candidate_count_marks_nothing(self):
        result = ranking.rank(
            [_component("a"), _component("b")], cap=99)
        self.assertEqual(result["over_cap"], [])

    def test_a_negative_cap_is_refused(self):
        with self.assertRaises(ranking.RankingInputError):
            ranking.rank([_component("a")], cap=-1)


class MapExemption(unittest.TestCase):
    def test_the_codebase_map_is_never_over_cap(self):
        result = ranking.rank(
            [_map_candidate(), _component("a", blast=50)], cap=0)
        self.assertFalse(
            _entry(result, candidates.CODEBASE_MAP_KEY)["over_cap"])

    def test_the_map_does_not_consume_a_cap_slot(self):
        # Under `cap=1` with the map counted, the one component would be
        # stranded and the release's unconditional map would be the only
        # note. The map is exempt, so the slot goes to the component.
        result = ranking.rank(
            [_map_candidate(), _component("a", blast=50)], cap=1)
        self.assertFalse(_entry(result, "component:a")["over_cap"])

    def test_the_map_consumes_no_slot_even_when_it_ranks_first(self):
        # The test above cannot see a map that consumes a slot, because a map
        # carries no metrics and so normally sorts LAST, where a stolen slot
        # is harmless. Here the component is unmeasured too, so both tie on
        # bands and "codebase-map" wins the key tie-break -- the map is now
        # ahead of the component, and a slot it consumed would strand it.
        result = ranking.rank([
            _map_candidate(),
            _component("a", blast=None, coverage="unknown"),
        ], cap=1)
        self.assertEqual(_keys(result["ranked"])[0],
                         candidates.CODEBASE_MAP_KEY)
        self.assertFalse(_entry(result, "component:a")["over_cap"])

    def test_the_map_is_marked_exempt(self):
        result = ranking.rank([_map_candidate(), _component("a")], cap=1)
        self.assertTrue(_entry(result, candidates.CODEBASE_MAP_KEY)["exempt"])
        self.assertFalse(_entry(result, "component:a")["exempt"])

    def test_exemption_is_declared_in_applied(self):
        result = ranking.rank([_map_candidate()], cap=1)
        self.assertEqual(result["applied"]["exempt_keys"],
                         sorted(ranking.CAP_EXEMPT_KEYS))


class RankSwapStability(unittest.TestCase):
    """PT22 -- a rank swap at the cap boundary does not orphan a note."""

    def test_both_sides_of_the_boundary_survive_a_swap(self):
        before = ranking.rank([
            _component("a", blast=50), _component("b", blast=5),
        ], cap=1)
        after = ranking.rank([
            _component("a", blast=5), _component("b", blast=50),
        ], cap=1)
        self.assertEqual(sorted(_keys(before["ranked"])),
                         sorted(_keys(after["ranked"])))

    def test_a_swap_moves_the_mark_and_not_the_membership(self):
        before = ranking.rank([
            _component("a", blast=50), _component("b", blast=5),
        ], cap=1)
        after = ranking.rank([
            _component("a", blast=5), _component("b", blast=50),
        ], cap=1)
        self.assertEqual(before["over_cap"], ["component:b"])
        self.assertEqual(after["over_cap"], ["component:a"])


class Observability(unittest.TestCase):
    def test_applied_echoes_the_cap(self):
        self.assertEqual(ranking.rank([_component("a")], cap=7)["cap"], 7)

    def test_applied_echoes_the_rank_signals(self):
        result = ranking.rank([_component("a")])
        self.assertEqual(result["applied"]["rank_signals"],
                         list(ranking.RANK_SIGNALS))

    def test_applied_echoes_the_band_order(self):
        result = ranking.rank([_component("a")])
        self.assertEqual(result["applied"]["band_order"],
                         list(ranking.BAND_ORDER))

    def test_an_absent_cap_is_reported_as_none_not_omitted(self):
        # "silent enforcement and silent non-enforcement are both forbidden"
        # -- an uncapped run must say so rather than leave the key missing.
        result = ranking.rank([_component("a")])
        self.assertIn("cap", result)
        self.assertIsNone(result["cap"])


class Determinism(unittest.TestCase):
    def test_input_order_does_not_change_the_output(self):
        one = ranking.rank([
            _component("a", blast=50), _component("b", blast=5),
        ], cap=1)
        other = ranking.rank([
            _component("b", blast=5), _component("a", blast=50),
        ], cap=1)
        self.assertEqual(one, other)

    def test_repeating_a_run_reproduces_the_output(self):
        args = [_component("a", blast=50), _component("b", blast=5)]
        self.assertEqual(ranking.rank(args, cap=1), ranking.rank(args, cap=1))

    def test_ranking_does_not_mutate_its_input(self):
        given = [_component("a", blast=50)]
        before = [dict(record) for record in given]
        ranking.rank(given, cap=1)
        self.assertEqual(given, before)


class Integration(unittest.TestCase):
    """Ranking must survive real `plan()` output, not just the corpus."""

    def test_every_planned_candidate_is_ranked_exactly_once(self):
        from architecture.tests import test_candidates

        planned = candidates.plan(test_candidates.GRAPH)["candidates"]
        result = ranking.rank(planned, cap=1)
        self.assertEqual(
            sorted(_keys(result["ranked"])),
            sorted(c["candidate_key"] for c in planned),
        )

    def test_a_planned_map_is_exempt(self):
        from architecture.tests import test_candidates

        planned = candidates.plan(test_candidates.GRAPH)["candidates"]
        result = ranking.rank(planned, cap=0)
        self.assertEqual(result["over_cap"],
                         sorted(c["candidate_key"] for c in planned
                                if c["projection_type"] == "arch_component"))


if __name__ == "__main__":
    unittest.main()
