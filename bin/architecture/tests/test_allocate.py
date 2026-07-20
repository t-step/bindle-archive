"""Tests for architecture.allocate — the mint side of identity.

`matcher.match` emits `outcome="mint", arch_id=None`; `apply()` requires
`identities[key]["arch_id"]` and, through the planner, a kebab-case `slug`.
Nothing converted one into the other, so a first-ever projection raised
`PlanInputError: slug must be kebab-case: None` at plan time. This module
closes that gap.

The slug is the load-bearing half. `planner.FINGERPRINT_TERMS` includes
`manifest`, which is the list of planned `note_path`s, and a note path
derives from the slug — so a slug that is not identical across preview and
apply aborts every first-ever projection as `stale_preview`. The hex enters
no fingerprint term and may be random.
"""
import unittest

from architecture import allocate
from architecture import ids
from architecture import state

PROJECT_ID = "project:" + "a" * 32
DECIDED_AT = "2026-07-20T00:00:00Z"


def _candidate(key, name, projection_type="arch_component"):
    return {"candidate_key": key,
            "name": name,
            "projection_type": projection_type}


class DeriveSlug(unittest.TestCase):

    def test_kebab_cases_a_display_name(self):
        self.assertEqual(allocate.derive_slug("Auth Layer"), "auth-layer")

    def test_collapses_runs_of_separators(self):
        self.assertEqual(allocate.derive_slug("Auth__/  Layer!!"), "auth-layer")

    def test_trims_leading_and_trailing_separators(self):
        self.assertEqual(allocate.derive_slug("  !Auth Layer!  "), "auth-layer")

    def test_result_always_satisfies_the_frozen_note_slug_shape(self):
        for name in ["Auth Layer", "API", "v2.1 Core", "a-b-c", "Ünïcode Bits"]:
            slug = allocate.derive_slug(name)
            self.assertIsNotNone(state._NOTE_SLUG_RE.match(slug),
                                 "%r produced %r" % (name, slug))

    def test_a_name_with_no_alphanumerics_is_refused(self):
        with self.assertRaises(allocate.SlugError):
            allocate.derive_slug("!!!")

    def test_a_non_string_name_is_refused(self):
        with self.assertRaises(allocate.SlugError):
            allocate.derive_slug(None)

    def test_is_deterministic(self):
        self.assertEqual(allocate.derive_slug("Auth Layer"),
                         allocate.derive_slug("Auth Layer"))


class Allocate(unittest.TestCase):

    def _allocate(self, candidates, **kwargs):
        kwargs.setdefault("mint_hex", _counting_hex())
        return allocate.allocate(PROJECT_ID, candidates, DECIDED_AT, **kwargs)

    def test_mints_a_parseable_arch_id_per_candidate(self):
        result = self._allocate([_candidate("component:auth", "Auth Layer")])
        arch_id = result["identities"]["component:auth"]["arch_id"]
        parsed = ids.parse_arch_node_id(arch_id)
        self.assertEqual(parsed["project_id"], PROJECT_ID)

    def test_the_slug_places_a_legal_note_path(self):
        result = self._allocate([_candidate("component:auth", "Auth Layer")])
        identity = result["identities"]["component:auth"]
        self.assertEqual(
            state.format_note_path("arch_component", identity["slug"]),
            "Components/auth-layer.md")

    def test_the_codebase_map_is_allocated_too(self):
        result = self._allocate(
            [_candidate("codebase-map", "codebase-map", "arch_codebase_map")])
        self.assertIn("codebase-map", result["identities"])

    def test_emits_one_identity_allocation_record_per_candidate(self):
        result = self._allocate([
            _candidate("component:auth", "Auth Layer"),
            _candidate("component:db", "Database"),
        ])
        self.assertEqual(len(result["records"]), 2)
        for record in result["records"]:
            self.assertEqual(record["kind"], "identity_allocation")
            self.assertEqual(record["project_id"], PROJECT_ID)
            self.assertEqual(record["decided_at"], DECIDED_AT)
            self.assertEqual(record["schema_version"], state.SCHEMA_VERSION)

    def test_each_record_names_the_identity_it_allocates(self):
        result = self._allocate([_candidate("component:auth", "Auth Layer")])
        record = result["records"][0]
        self.assertEqual(record["arch_id"],
                         result["identities"]["component:auth"]["arch_id"])
        self.assertEqual(record["payload"]["candidate_key"], "component:auth")

    def test_records_come_back_ordered_by_candidate_key(self):
        result = self._allocate([
            _candidate("component:zulu", "Zulu"),
            _candidate("component:alpha", "Alpha"),
        ])
        self.assertEqual([r["payload"]["candidate_key"] for r in result["records"]],
                         ["component:alpha", "component:zulu"])

    def test_distinct_candidates_get_distinct_identities(self):
        result = self._allocate([
            _candidate("component:auth", "Auth Layer"),
            _candidate("component:db", "Database"),
        ])
        arch_ids = {identity["arch_id"]
                    for identity in result["identities"].values()}
        self.assertEqual(len(arch_ids), 2)

    def test_the_slug_is_identical_across_two_allocations(self):
        """The fingerprint's `manifest` term digests note paths, which derive
        from the slug. A slug that moved between preview and apply would
        abort every first-ever projection as stale_preview."""
        candidates = [_candidate("component:auth", "Auth Layer")]
        first = self._allocate(candidates)
        second = self._allocate(candidates)
        self.assertEqual(first["identities"]["component:auth"]["slug"],
                         second["identities"]["component:auth"]["slug"])

    def test_allocating_nothing_yields_nothing(self):
        result = self._allocate([])
        self.assertEqual(result["identities"], {})
        self.assertEqual(result["records"], [])

    def test_the_default_hex_source_is_random_and_well_formed(self):
        """No mint_hex injected: the real source must still produce a
        parseable identity. Random is legal because the hex enters no
        fingerprint term."""
        result = allocate.allocate(
            PROJECT_ID, [_candidate("component:auth", "Auth Layer")], DECIDED_AT)
        arch_id = result["identities"]["component:auth"]["arch_id"]
        self.assertTrue(ids.is_arch_node_id(arch_id))


class SlugCollision(unittest.TestCase):
    """Two candidates deriving one slug would claim one note path, and the
    duplicate would enter the fingerprint's manifest term. Refuse, naming
    both, rather than silently disambiguating."""

    def _colliding(self):
        return [_candidate("component:src/auth", "Auth Layer"),
                _candidate("component:src/authz", "Auth  Layer")]

    def test_a_collision_is_refused(self):
        with self.assertRaises(allocate.SlugCollisionError):
            allocate.allocate(PROJECT_ID, self._colliding(), DECIDED_AT,
                              mint_hex=_counting_hex())

    def test_the_error_names_the_slug_and_both_candidates(self):
        with self.assertRaises(allocate.SlugCollisionError) as caught:
            allocate.allocate(PROJECT_ID, self._colliding(), DECIDED_AT,
                              mint_hex=_counting_hex())
        message = str(caught.exception)
        self.assertIn("auth-layer", message)
        self.assertIn("component:src/auth", message)
        self.assertIn("component:src/authz", message)

    def test_nothing_is_allocated_when_a_collision_is_refused(self):
        """The refusal must precede minting: a partially built result would
        leave identities the caller might still commit."""
        minted = []

        def recording_hex():
            minted.append(1)
            return "%032x" % len(minted)

        with self.assertRaises(allocate.SlugCollisionError):
            allocate.allocate(PROJECT_ID, self._colliding(), DECIDED_AT,
                              mint_hex=recording_hex)
        self.assertEqual(minted, [])

    def test_the_same_candidate_key_twice_is_refused(self):
        duplicate = [_candidate("component:auth", "Auth Layer"),
                     _candidate("component:auth", "Auth Layer")]
        with self.assertRaises(allocate.SlugCollisionError):
            allocate.allocate(PROJECT_ID, duplicate, DECIDED_AT,
                              mint_hex=_counting_hex())


def _counting_hex():
    """A deterministic stand-in for secrets.token_hex(16): the hex enters no
    fingerprint term, so a test may pin it without pinning behavior."""
    state_ = {"n": 0}

    def mint():
        state_["n"] += 1
        return "%032x" % state_["n"]

    return mint


if __name__ == "__main__":
    unittest.main()
