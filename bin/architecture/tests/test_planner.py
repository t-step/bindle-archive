"""Tests for architecture.planner (issue #230 child D, slice D3).

Scope note: these tests assert plan DETERMINISM -- an identical interchange
produces a byte-identical plan -- and never plan EQUIVALENCE across two
adapters. PT7b is a combined D+E release gate and child E (#231) is
unstarted, so equivalence is not claimable here and is deliberately absent.
"""
import copy
import unittest

from architecture import candidates
from architecture import planner


def _metric(band, value):
    return {"band": band, "value": value}


def _component(key, name, blast="high", fan_in="medium", fan_out="low",
               blast_value=40, member_count=3):
    return {
        "candidate_key": key,
        "projection_type": "arch_component",
        "name": name,
        "source_paths": ["src/%s" % (name,)],
        "symbol_names": [],
        "member_count": member_count,
        "entry_points": [],
        "bindings": ["ref"],
        "metrics": {
            "blast_radius": _metric(blast, blast_value),
            "fan_in": _metric(fan_in, 12),
            "fan_out": _metric(fan_out, 2),
        },
    }


def _map_record():
    return {
        "candidate_key": candidates.CODEBASE_MAP_KEY,
        "projection_type": "arch_codebase_map",
        "name": "Codebase Map",
        "source_paths": ["."],
        "symbol_names": [],
        "member_count": 2,
        "entry_points": [],
        "bindings": ["ref"],
        "metrics": {},
    }


def _identities(*keys):
    identity = {}
    for key in keys:
        if key == candidates.CODEBASE_MAP_KEY:
            identity[key] = {"slug": "codebase-map"}
        else:
            identity[key] = {"slug": key.split(":", 1)[1]}
    return identity


_BINDING_ID = "repository-binding:" + "d" * 32


def _config(max_nodes=10):
    return {
        "schema_version": 1,
        "projection_schema_version": 1,
        "project_id": "project:" + "a" * 32,
        "project_slug": "bindle",
        "bindings": [{"binding_id": _BINDING_ID, "alias": "bindle"}],
        "caps": {"max_nodes": max_nodes, "over_cap_behavior": "report"},
        "thresholds": {"high": 0.9, "low": 0.4},
        "diff_size_confirmation_limit": 20,
    }


def _terms(records=None, config=None):
    records = records if records is not None else [_component("component:auth", "auth")]
    return {
        "bindings": {"ref": {"source_commit": "a" * 40}},
        "provider": {"name": "reference", "version": "1.0.0"},
        "config": config if config is not None else _config(),
        "candidates": records,
        "manifest": ["Components/auth.md"],
    }


class TestPlanFingerprintShape(unittest.TestCase):

    def test_fingerprint_is_domain_prefixed_sha256(self):
        value = planner.plan_fingerprint(_terms())
        self.assertTrue(value.startswith(planner.PLAN_FINGERPRINT_PREFIX))
        digest = value[len(planner.PLAN_FINGERPRINT_PREFIX):]
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower())
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))

    def test_prefix_is_distinct_from_the_judgment_record_prefix(self):
        # A plan is not a judgment record; sharing a domain tag would let one
        # digest be presented as the other.
        from architecture import canonical
        self.assertNotEqual(planner.PLAN_FINGERPRINT_PREFIX,
                            canonical.RECORD_ID_PREFIX)

    def test_fingerprint_is_deterministic(self):
        self.assertEqual(planner.plan_fingerprint(_terms()),
                         planner.plan_fingerprint(_terms()))

    def test_fingerprint_does_not_mutate_its_input(self):
        terms = _terms()
        before = copy.deepcopy(terms)
        planner.plan_fingerprint(terms)
        self.assertEqual(terms, before)


class TestPlanFingerprintKnownAnswer(unittest.TestCase):
    """A pinned vector. Without it the digest's serialization, its domain
    tag, and its term set are all free to drift under a refactor while every
    relative comparison in this file keeps passing."""

    VECTOR = ("arch-plan:sha256:"
              "e3afcf8a1a5260ad27f558a7b755e661769ab6d4cda7f3047bcab6789b2ca874")

    def test_fingerprint_matches_its_pinned_vector(self):
        self.assertEqual(planner.plan_fingerprint(_terms()), self.VECTOR)


class TestPlanFingerprintTerms(unittest.TestCase):

    def test_a_config_that_does_not_validate_is_refused(self):
        # Digesting a malformed document would compare equal to itself and
        # carry the malformation into apply.
        broken = _config()
        del broken["project_id"]
        with self.assertRaises(planner.PlanInputError):
            planner.plan_fingerprint(_terms(config=broken))

    def test_unknown_term_is_refused(self):
        terms = _terms()
        terms["extra"] = 1
        with self.assertRaises(planner.PlanInputError):
            planner.plan_fingerprint(terms)

    def test_missing_term_is_refused(self):
        terms = _terms()
        del terms["manifest"]
        with self.assertRaises(planner.PlanInputError):
            planner.plan_fingerprint(terms)

    def test_binding_source_commit_change_moves_the_fingerprint(self):
        other = _terms()
        other["bindings"] = {"ref": {"source_commit": "b" * 40}}
        self.assertNotEqual(planner.plan_fingerprint(_terms()),
                            planner.plan_fingerprint(other))

    def test_provider_version_change_moves_the_fingerprint(self):
        other = _terms()
        other["provider"] = {"name": "reference", "version": "2.0.0"}
        self.assertNotEqual(planner.plan_fingerprint(_terms()),
                            planner.plan_fingerprint(other))

    def test_provider_name_change_moves_the_fingerprint(self):
        other = _terms()
        other["provider"] = {"name": "codegraph", "version": "1.0.0"}
        self.assertNotEqual(planner.plan_fingerprint(_terms()),
                            planner.plan_fingerprint(other))

    def test_manifest_change_moves_the_fingerprint(self):
        other = _terms()
        other["manifest"] = ["Components/auth.md", "Components/billing.md"]
        self.assertNotEqual(planner.plan_fingerprint(_terms()),
                            planner.plan_fingerprint(other))

    def test_cap_change_moves_the_fingerprint(self):
        self.assertNotEqual(
            planner.plan_fingerprint(_terms(config=_config(max_nodes=10))),
            planner.plan_fingerprint(_terms(config=_config(max_nodes=1))))


class TestPlanFingerprintStability(unittest.TestCase):
    """What must NOT move the fingerprint. Each case is a real edit that
    changes no meaning; aborting on it would invalidate a plan the operator
    legitimately confirmed."""

    def test_config_key_order_does_not_move_the_fingerprint(self):
        reordered = dict(reversed(list(_config().items())))
        reordered["caps"] = {"over_cap_behavior": "report", "max_nodes": 10}
        self.assertEqual(planner.plan_fingerprint(_terms()),
                         planner.plan_fingerprint(_terms(config=reordered)))

    def test_candidate_order_does_not_move_the_fingerprint(self):
        first = [_component("component:auth", "auth"),
                 _component("component:billing", "billing")]
        self.assertEqual(planner.plan_fingerprint(_terms(records=first)),
                         planner.plan_fingerprint(_terms(records=list(reversed(first)))))

    def test_raw_metric_move_inside_a_band_does_not_move_the_fingerprint(self):
        # The banded reading is the churn-guarded one -- diffs.py's frozen
        # rationale. A blast_radius of 40 -> 41 is not an architecture change.
        moved = [_component("component:auth", "auth", blast_value=41)]
        self.assertEqual(planner.plan_fingerprint(_terms()),
                         planner.plan_fingerprint(_terms(records=moved)))

    def test_binding_membership_of_a_candidate_does_not_move_the_fingerprint(self):
        # `bindings` is provenance and is diffs.EXCLUDED_FIELDS by contract;
        # the binding TERM carries source commits separately.
        record = _component("component:auth", "auth")
        record["bindings"] = ["ref", "second"]
        self.assertEqual(planner.plan_fingerprint(_terms()),
                         planner.plan_fingerprint(_terms(records=[record])))

    def test_band_change_does_move_the_fingerprint(self):
        # The guard on the three cases above: the band reading must still be
        # discriminating, or they pass vacuously.
        banded = [_component("component:auth", "auth", blast="low")]
        self.assertNotEqual(planner.plan_fingerprint(_terms()),
                            planner.plan_fingerprint(_terms(records=banded)))


class TestPlanDispositions(unittest.TestCase):

    def test_first_ever_run_against_no_previous_mints(self):
        records = [_map_record(), _component("component:auth", "auth")]
        result = planner.plan(records, previous=(), config=_config(),
                              identities=_identities(candidates.CODEBASE_MAP_KEY,
                                                     "component:auth"))
        self.assertEqual({e["disposition"] for e in result["entries"]}, {"mint"})

    def test_unchanged_candidate_is_a_noop(self):
        records = [_component("component:auth", "auth")]
        identities = _identities("component:auth")
        first = planner.plan(records, previous=(), config=_config(),
                             identities=identities)
        second = planner.plan(records, previous=records, config=_config(),
                              identities=identities)
        self.assertEqual(first["entries"][0]["disposition"], "mint")
        self.assertEqual(second["entries"][0]["disposition"], "noop")

    def test_changed_candidate_refreshes(self):
        before = [_component("component:auth", "auth")]
        after = [_component("component:auth", "auth", blast="low")]
        result = planner.plan(after, previous=before, config=_config(),
                              identities=_identities("component:auth"))
        self.assertEqual(result["entries"][0]["disposition"], "refresh")

    def test_a_candidate_whose_raw_metric_moved_inside_its_band_is_a_noop(self):
        before = [_component("component:auth", "auth", blast_value=40)]
        after = [_component("component:auth", "auth", blast_value=41)]
        result = planner.plan(after, previous=before, config=_config(),
                              identities=_identities("component:auth"))
        self.assertEqual(result["entries"][0]["disposition"], "noop")


class TestPlanOverCap(unittest.TestCase):

    def test_over_cap_candidate_is_present_as_an_explicit_noop(self):
        records = [_component("component:strong", "strong", blast="high"),
                   _component("component:weak", "weak", blast="low")]
        result = planner.plan(records, previous=(), config=_config(max_nodes=1),
                              identities=_identities("component:strong",
                                                     "component:weak"))
        by_key = {e["candidate_key"]: e for e in result["entries"]}
        self.assertIn("component:weak", by_key,
                      "an over-cap node is retained and reported, never omitted")
        self.assertTrue(by_key["component:weak"]["over_cap"])
        self.assertEqual(by_key["component:weak"]["disposition"], "noop")
        self.assertFalse(by_key["component:strong"]["over_cap"])
        self.assertEqual(by_key["component:strong"]["disposition"], "mint")

    def test_over_cap_uses_the_over_cap_spelling(self):
        # The frozen config key is `caps.over_cap_behavior` and merged
        # ranking.py emits `over_cap`; the preview surface agrees with both.
        records = [_component("component:auth", "auth")]
        result = planner.plan(records, previous=(), config=_config(),
                              identities=_identities("component:auth"))
        self.assertIn("over_cap", result["entries"][0])
        self.assertNotIn("below_cap_threshold", result["entries"][0])

    def test_an_over_cap_note_is_not_in_the_write_manifest(self):
        # The manifest is what apply will WRITE. An over-cap node is retained
        # and reported, never written -- so its path must not enter the
        # manifest term, or the fingerprint would bind a write nobody planned.
        strong = _component("component:strong", "strong", blast="high")
        weak = _component("component:weak", "weak", blast="low")
        result = planner.plan([strong, weak], previous=(),
                              config=_config(max_nodes=1),
                              identities=_identities("component:strong",
                                                     "component:weak"))
        self.assertIn("Components/strong.md", result["manifest"])
        self.assertNotIn("Components/weak.md", result["manifest"])
        self.assertIn("component:weak",
                      [e["candidate_key"] for e in result["entries"]],
                      "excluded from the manifest, still reported in preview")

    def test_codebase_map_is_exempt_from_the_cap(self):
        records = [_map_record(),
                   _component("component:auth", "auth", blast="high")]
        result = planner.plan(records, previous=(), config=_config(max_nodes=1),
                              identities=_identities(candidates.CODEBASE_MAP_KEY,
                                                     "component:auth"))
        by_key = {e["candidate_key"]: e for e in result["entries"]}
        self.assertFalse(by_key[candidates.CODEBASE_MAP_KEY]["over_cap"],
                         "the map must not spend the only cap slot")
        self.assertEqual(by_key[candidates.CODEBASE_MAP_KEY]["disposition"], "mint")
        self.assertFalse(by_key["component:auth"]["over_cap"],
                         "the exempt map must not consume the component's slot")


class TestPlanContainment(unittest.TestCase):

    def test_a_planned_path_escaping_the_notes_home_rejects_the_whole_plan(self):
        records = [_component("component:auth", "auth"),
                   _component("component:evil", "evil")]
        identities = _identities("component:auth", "component:evil")
        identities["component:evil"] = {"slug": "evil",
                                        "note_path": "../outside.md"}
        with self.assertRaises(planner.PlanInputError):
            planner.plan(records, previous=(), config=_config(),
                         identities=identities, notes_root="/tmp/notes-home")

    def test_rejection_reports_every_offender_not_just_the_first(self):
        records = [_component("component:a", "a"), _component("component:b", "b")]
        identities = {
            "component:a": {"slug": "a", "note_path": "../one.md"},
            "component:b": {"slug": "b", "note_path": "../two.md"},
        }
        with self.assertRaises(planner.PlanInputError) as caught:
            planner.plan(records, previous=(), config=_config(),
                         identities=identities, notes_root="/tmp/notes-home")
        message = str(caught.exception)
        self.assertIn("../one.md", message)
        self.assertIn("../two.md", message)


class TestPlanDeterminism(unittest.TestCase):
    """Determinism only -- see this module's docstring on PT7b."""

    def test_identical_input_produces_an_identical_plan(self):
        records = [_component("component:billing", "billing"),
                   _component("component:auth", "auth")]
        identities = _identities("component:auth", "component:billing")
        first = planner.plan(records, previous=(), config=_config(),
                             identities=identities)
        second = planner.plan(list(reversed(records)), previous=(),
                              config=_config(), identities=identities)
        self.assertEqual(first, second)

    def test_entries_are_ordered_by_candidate_key(self):
        records = [_component("component:zeta", "zeta"),
                   _component("component:alpha", "alpha")]
        result = planner.plan(records, previous=(), config=_config(),
                              identities=_identities("component:zeta",
                                                     "component:alpha"))
        keys = [e["candidate_key"] for e in result["entries"]]
        self.assertEqual(keys, sorted(keys))

    def test_plan_carries_its_own_fingerprint(self):
        records = [_component("component:auth", "auth")]
        result = planner.plan(records, previous=(), config=_config(),
                              identities=_identities("component:auth"),
                              bindings={"ref": {"source_commit": "a" * 40}},
                              provider={"name": "reference", "version": "1.0.0"})
        self.assertTrue(
            result["fingerprint"].startswith(planner.PLAN_FINGERPRINT_PREFIX))

    def test_plan_does_not_mutate_its_input_records(self):
        records = [_component("component:auth", "auth")]
        before = copy.deepcopy(records)
        planner.plan(records, previous=(), config=_config(),
                     identities=_identities("component:auth"))
        self.assertEqual(records, before)


if __name__ == "__main__":
    unittest.main()
