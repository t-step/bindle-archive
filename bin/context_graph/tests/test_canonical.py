import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import canonical


class TestNormalizeBasisEntry(unittest.TestCase):
    def test_valid_entry_normalizes(self):
        entry = {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"}
        self.assertEqual(canonical.normalize_basis_entry(entry), entry)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry({"kind": "mystery"})

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry(
                {"kind": "evidence_pointer", "location": "entry_evidence",
                 "pointer": "#42", "extra": "nope"}
            )

    def test_missing_required_field_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry({"kind": "evidence_pointer", "pointer": "#42"})

    def test_explicit_null_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry(
                {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": None}
            )

    def test_non_string_value_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry(
                {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": 42}
            )

    def test_bad_enum_value_rejected(self):
        with self.assertRaises(ValueError):
            canonical.normalize_basis_entry(
                {"kind": "evidence_pointer", "location": "nowhere", "pointer": "#42"}
            )


class TestCanonicalBasisBytes(unittest.TestCase):
    def test_order_irrelevant_and_duplicates_collapse(self):
        e1 = {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"}
        e2 = {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"}
        forward = canonical.canonical_basis_bytes([e1, e2])
        reversed_ = canonical.canonical_basis_bytes([e2, e1])
        with_dup = canonical.canonical_basis_bytes([e1, e1, e2])
        self.assertEqual(forward, reversed_)
        self.assertEqual(forward, with_dup)

    def test_matches_independently_verified_vector(self):
        basis = [
            {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
            {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
            {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"},
        ]
        expected = (
            b'[{"kind":"evidence_pointer","location":"entry_evidence","pointer":"#42"},'
            b'{"kind":"evidence_pointer","location":"tension_side","pointer":"#7"}]'
        )
        self.assertEqual(canonical.canonical_basis_bytes(basis), expected)


class TestCandidateKey(unittest.TestCase):
    SOURCE = "context-node:bindle:11111111111111111111111111111111"
    TARGET = "context-node:bindle:22222222222222222222222222222222"

    def test_matches_independently_verified_vector(self):
        basis = [
            {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
            {"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#42"},
            {"kind": "evidence_pointer", "location": "tension_side", "pointer": "#7"},
        ]
        key = canonical.candidate_key(self.SOURCE, "depends_on", self.TARGET, basis)
        # exact pinned digest, independently computed during planning
        self.assertEqual(
            key,
            "candidate:sha256:67c682361434354688cd98af8ce68bdb0ac1a01badcf4fece"
            "cf9d85614750059",
        )

    def test_empty_basis_vector(self):
        key = canonical.candidate_key(self.SOURCE, "depends_on", self.TARGET, [])
        self.assertEqual(
            key,
            "candidate:sha256:696846d2e541fc02e069434fe7c101a19ea2bc4950ed66bd"
            "9038f6626fd68204",
        )

    def test_changed_basis_changes_key(self):
        k1 = canonical.candidate_key(
            self.SOURCE, "depends_on", self.TARGET,
            [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#1"}],
        )
        k2 = canonical.candidate_key(
            self.SOURCE, "depends_on", self.TARGET,
            [{"kind": "evidence_pointer", "location": "entry_evidence", "pointer": "#2"}],
        )
        self.assertNotEqual(k1, k2)

    def test_contradicts_reversed_pair_same_key(self):
        k1 = canonical.candidate_key(self.SOURCE, "contradicts", self.TARGET, [])
        k2 = canonical.candidate_key(self.TARGET, "contradicts", self.SOURCE, [])
        self.assertEqual(k1, k2)

    def test_key_format(self):
        key = canonical.candidate_key(self.SOURCE, "contradicts", self.TARGET, [])
        self.assertTrue(key.startswith("candidate:sha256:"))
        self.assertEqual(len(key), len("candidate:sha256:") + 64)


class TestAnchorPrimitives(unittest.TestCase):
    """Reproduces docs/design/2026-07-16-context-graph-schema.md section
    10.2's worked byte-exact example exactly — independently re-derived
    during planning and confirmed to match all three pinned digests."""

    PROJECT_ID = "project:5f56c9b95c41c298f70d6dd4e5db8c2a"
    MAP_PATH = "projects/bindle/map.md"
    SECTION = "decisions"
    ENTRY_KIND = "decision"
    ENTRY_BYTES = "\n".join(
        [
            "### Separate release intent, artifact, and publication authority "
            "(2026-07, settled)",
            "why: three failure modes were collapsing into one review step.",
            "so: release-captain recommends, package-release-integrity gates, "
            "a human publishes.",
            "revisit-when: a provider ships one safe end-to-end release action.",
            "evidence: sessions/2026-07-15-release-captain.md",
        ]
    ).encode("utf-8")

    def test_entry_bytes_length_matches_design(self):
        self.assertEqual(len(self.ENTRY_BYTES), 346)

    def test_entry_fingerprint_matches_design(self):
        fp = canonical.entry_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND,
            self.ENTRY_BYTES,
        )
        self.assertEqual(
            fp,
            "sha256:37730a28d9968e38cb25da0b1a98b7c4e13c43a2b661ca2b6cd3daf884"
            "b8e681",
        )

    def test_anchor_candidate_key_matches_design(self):
        fp = canonical.entry_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND,
            self.ENTRY_BYTES,
        )
        key = canonical.anchor_candidate_key(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND, fp
        )
        self.assertEqual(
            key,
            "anchor-candidate:sha256:de5f2e3ead19bcb905dfd0ac06898c12c71bb1a7d"
            "112de386363490e54197933",
        )

    def test_dependency_fingerprint_matches_design(self):
        fp = canonical.entry_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND,
            self.ENTRY_BYTES,
        )
        dep = canonical.anchor_dependency_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND, fp
        )
        self.assertEqual(
            dep,
            "sha256:f579dbeb232f6f18724ea3322132105aed41dc8b799d98dc79ab49513"
            "3224e5f",
        )

    def test_candidate_key_and_dependency_fingerprint_never_collide(self):
        fp = canonical.entry_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND,
            self.ENTRY_BYTES,
        )
        key = canonical.anchor_candidate_key(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND, fp
        )
        dep = canonical.anchor_dependency_fingerprint(
            self.PROJECT_ID, self.MAP_PATH, self.SECTION, self.ENTRY_KIND, fp
        )
        self.assertNotEqual(key.split(":", 1)[1], dep)


if __name__ == "__main__":
    unittest.main()
