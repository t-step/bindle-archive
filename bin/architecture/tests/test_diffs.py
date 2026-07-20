"""Deterministic diffs and the minimal changed-set (#229 child C, slice C3,
epic #141).

The frozen contract this exercises: "a changed input yields a minimal correct
changed-set", supplying the primitive child D needs for AC11 (changed-only
refresh) and PT31 ("a commit touching one unrelated file rewrites zero
notes").

WHAT IS *NOT* IN THE FINGERPRINT IS THE POINT. Provenance -- `bindings`, and
anything a provider stamps per run -- moves on commits that changed no
architecture, so including it would mark every candidate changed on any
commit and defeat PT31 outright. Metrics participate as BANDS ONLY, for the
same reason ranking bands: a fan-in of 21 -> 22 must not rewrite a note.
`test_a_raw_metric_change_inside_one_band_is_unchanged` is the assertion that
catches a fingerprint rewritten against raw measurements.

The corpus is literal hand-authored data. A corpus, a validator and a writer
that all route through one implementation prove agreement, not correctness.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import candidates
from architecture import diffs
from architecture import metrics


def _m(value, coverage="observed"):
    return metrics.measurement(value, coverage)


def _component(key, blast=0, paths=None, names=None, name=None,
               bindings=None, member_count=None, entry_points=None,
               neighborhood=None):
    paths = paths if paths is not None else [key + "/a.py"]
    return {
        "candidate_key": candidates.COMPONENT_KEY_PREFIX + key,
        "projection_type": "arch_component",
        "source_paths": list(paths),
        "symbol_names": list(names if names is not None else []),
        "neighborhood": list(neighborhood if neighborhood is not None else []),
        "name": name if name is not None else key,
        "metrics": {
            "blast_radius": _m(blast),
            "fan_in": _m(0),
            "fan_out": _m(0),
        },
        "entry_points": list(entry_points if entry_points is not None else []),
        "bindings": list(bindings if bindings is not None else []),
        "member_count": (member_count if member_count is not None
                         else len(paths)),
    }


def _changed_keys(result):
    return [entry["candidate_key"] for entry in result["changed"]]


def _changed_fields(result, key):
    for entry in result["changed"]:
        if entry["candidate_key"] == key:
            return entry["fields"]
    raise AssertionError("no changed entry for " + key)


class FingerprintFields(unittest.TestCase):
    def test_fingerprint_covers_the_semantic_record_fields(self):
        self.assertEqual(
            set(diffs.FINGERPRINT_FIELDS) | set(diffs.EXCLUDED_FIELDS),
            set(candidates.RECORD_FIELDS),
        )

    def test_fingerprint_and_excluded_fields_do_not_overlap(self):
        self.assertEqual(
            set(diffs.FINGERPRINT_FIELDS) & set(diffs.EXCLUDED_FIELDS),
            set(),
        )

    def test_provenance_is_excluded(self):
        self.assertIn("bindings", diffs.EXCLUDED_FIELDS)

    def test_a_fingerprint_carries_exactly_the_fingerprint_fields(self):
        self.assertEqual(
            set(diffs.fingerprint(_component("a"))),
            set(diffs.FINGERPRINT_FIELDS),
        )

    def test_an_unknown_field_is_refused(self):
        # The matcher hard-aborts on an unknown candidate field rather than
        # ignoring it; a fingerprint that silently dropped one would compare
        # equal across a real change.
        record = _component("a")
        record["provider_version"] = "1.2.3"
        with self.assertRaises(diffs.DiffInputError):
            diffs.fingerprint(record)


class FingerprintBanding(unittest.TestCase):
    def test_metrics_are_reduced_to_bands(self):
        printed = diffs.fingerprint(_component("a", blast=7))
        self.assertEqual(printed["metrics"]["blast_radius"], "moderate")

    def test_a_raw_metric_change_inside_one_band_is_unchanged(self):
        # 5 and 19 are both "moderate". Fingerprinted on raw measurements
        # these differ and every candidate churns; on bands they do not.
        self.assertEqual(
            diffs.fingerprint(_component("a", blast=5)),
            diffs.fingerprint(_component("a", blast=19)),
        )

    def test_a_band_crossing_is_a_change(self):
        self.assertNotEqual(
            diffs.fingerprint(_component("a", blast=19)),
            diffs.fingerprint(_component("a", blast=20)),
        )

    def test_an_empty_metrics_map_fingerprints(self):
        record = _component("a")
        record["metrics"] = {}
        self.assertEqual(diffs.fingerprint(record)["metrics"], {})


class Buckets(unittest.TestCase):
    def test_a_new_candidate_is_added(self):
        result = diffs.diff([], [_component("a")])
        self.assertEqual(result["added"], ["component:a"])

    def test_a_vanished_candidate_is_removed(self):
        result = diffs.diff([_component("a")], [])
        self.assertEqual(result["removed"], ["component:a"])

    def test_an_identical_candidate_is_unchanged(self):
        result = diffs.diff([_component("a")], [_component("a")])
        self.assertEqual(result["unchanged"], ["component:a"])

    def test_a_moved_member_is_changed(self):
        result = diffs.diff(
            [_component("a", paths=["a/one.py"])],
            [_component("a", paths=["a/two.py"])],
        )
        self.assertEqual(_changed_keys(result), ["component:a"])

    def test_every_candidate_lands_in_exactly_one_bucket(self):
        result = diffs.diff(
            [_component("gone"), _component("same"),
             _component("moved", paths=["moved/one.py"])],
            [_component("same"), _component("moved", paths=["moved/two.py"]),
             _component("new")],
        )
        landed = (result["added"] + result["removed"] +
                  _changed_keys(result) + result["unchanged"])
        self.assertEqual(sorted(landed), sorted(set(landed)))
        self.assertEqual(len(landed), 4)

    def test_all_buckets_are_sorted(self):
        result = diffs.diff(
            [_component("z"), _component("a")],
            [_component("y"), _component("b")],
        )
        self.assertEqual(result["added"], sorted(result["added"]))
        self.assertEqual(result["removed"], sorted(result["removed"]))

    def test_changed_entries_are_sorted_by_key(self):
        result = diffs.diff(
            [_component("z", paths=["z/one.py"]),
             _component("a", paths=["a/one.py"])],
            [_component("z", paths=["z/two.py"]),
             _component("a", paths=["a/two.py"])],
        )
        self.assertEqual(_changed_keys(result), ["component:a", "component:z"])


class ChangedFields(unittest.TestCase):
    def test_a_changed_entry_names_the_field_that_moved(self):
        result = diffs.diff(
            [_component("a", paths=["a/one.py"])],
            [_component("a", paths=["a/two.py"])],
        )
        self.assertEqual(_changed_fields(result, "component:a"),
                         ["source_paths"])

    def test_a_changed_entry_names_every_field_that_moved(self):
        result = diffs.diff(
            [_component("a", name="old", paths=["a/one.py"])],
            [_component("a", name="new", paths=["a/two.py"])],
        )
        self.assertEqual(_changed_fields(result, "component:a"),
                         ["name", "source_paths"])

    def test_changed_fields_are_sorted(self):
        result = diffs.diff(
            [_component("a", name="old", blast=0)],
            [_component("a", name="new", blast=50)],
        )
        fields = _changed_fields(result, "component:a")
        self.assertEqual(fields, sorted(fields))

    def test_a_band_change_names_the_metrics_field(self):
        result = diffs.diff(
            [_component("a", blast=0)], [_component("a", blast=50)])
        self.assertEqual(_changed_fields(result, "component:a"), ["metrics"])


class MinimalChangedSet(unittest.TestCase):
    """PT31 -- a commit touching one unrelated file rewrites zero notes."""

    def test_a_provenance_only_change_is_unchanged(self):
        result = diffs.diff(
            [_component("a", bindings=["binding:" + "1" * 32])],
            [_component("a", bindings=["binding:" + "2" * 32])],
        )
        self.assertEqual(result["unchanged"], ["component:a"])
        self.assertEqual(result["changed"], [])

    def test_an_edit_in_one_cluster_leaves_the_others_unchanged(self):
        previous = [_component("a", paths=["a/one.py"]),
                    _component("b"), _component("c")]
        current = [_component("a", paths=["a/two.py"]),
                   _component("b"), _component("c")]
        result = diffs.diff(previous, current)
        self.assertEqual(_changed_keys(result), ["component:a"])
        self.assertEqual(result["unchanged"], ["component:b", "component:c"])

    def test_an_unchanged_rerun_reports_no_work(self):
        # AC10's zero-write rerun, stated at C's layer: identical input must
        # produce an empty added/removed/changed set, or D cannot honour it.
        records = [_component("a"), _component("b")]
        result = diffs.diff(records, records)
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])
        self.assertEqual(result["changed"], [])


class Observability(unittest.TestCase):
    def test_applied_echoes_the_fingerprint_fields(self):
        result = diffs.diff([], [])
        self.assertEqual(result["applied"]["fingerprint_fields"],
                         list(diffs.FINGERPRINT_FIELDS))

    def test_applied_echoes_the_excluded_fields(self):
        # An exclusion is a deliberate blind spot, so it is reported rather
        # than left to be discovered by a caller wondering why a change was
        # not seen.
        result = diffs.diff([], [])
        self.assertEqual(result["applied"]["excluded_fields"],
                         list(diffs.EXCLUDED_FIELDS))

    def test_applied_declares_that_metrics_compare_as_bands(self):
        result = diffs.diff([], [])
        self.assertEqual(result["applied"]["metric_comparison"], "band")


class Determinism(unittest.TestCase):
    def test_input_order_does_not_change_the_output(self):
        one = diffs.diff([_component("a"), _component("b")],
                         [_component("b"), _component("a")])
        other = diffs.diff([_component("b"), _component("a")],
                           [_component("a"), _component("b")])
        self.assertEqual(one, other)

    def test_a_duplicate_candidate_key_is_refused(self):
        with self.assertRaises(diffs.DiffInputError):
            diffs.diff([], [_component("a"), _component("a")])

    def test_diffing_does_not_mutate_its_input(self):
        previous = [_component("a", paths=["a/one.py"])]
        current = [_component("a", paths=["a/two.py"])]
        before = ([dict(r) for r in previous], [dict(r) for r in current])
        diffs.diff(previous, current)
        self.assertEqual((previous, current), before)


class Integration(unittest.TestCase):
    def test_a_planned_run_diffs_clean_against_itself(self):
        from architecture.tests import test_candidates

        planned = candidates.plan(test_candidates.GRAPH)["candidates"]
        result = diffs.diff(planned, planned)
        self.assertEqual(result["changed"], [])
        self.assertEqual(
            result["unchanged"],
            sorted(c["candidate_key"] for c in planned),
        )

    def test_a_planned_candidate_fingerprints(self):
        from architecture.tests import test_candidates

        planned = candidates.plan(test_candidates.GRAPH)["candidates"]
        for record in planned:
            self.assertEqual(set(diffs.fingerprint(record)),
                             set(diffs.FINGERPRINT_FIELDS))


if __name__ == "__main__":
    unittest.main()
