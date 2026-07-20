"""Unit tests for architecture.canonical — the judgments-record envelope:
record_id, checksum, and the canonical payload they are taken over (#228)."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import canonical

PROJECT_ID = "project:" + "a" * 32
ARCH_ID = "arch-node:%s:%s" % (PROJECT_ID, "b" * 32)


def _record():
    return {
        "schema_version": 1,
        "kind": "identity_allocation",
        "arch_id": ARCH_ID,
        "project_id": PROJECT_ID,
        "decided_at": "2026-07-20T00:00:00Z",
        "payload": {"note_path": "Components/auth-service.md",
                    "slug": "auth-service"},
    }


class TestRecordId(unittest.TestCase):
    def test_record_id_is_content_derived_and_stable(self):
        self.assertEqual(canonical.judgment_record_id(_record()),
                         canonical.judgment_record_id(_record()))

    def test_record_id_has_the_frozen_shape(self):
        record_id = canonical.judgment_record_id(_record())
        self.assertTrue(record_id.startswith("arch-judgment:sha256:"))
        digest = record_id.split(":")[-1]
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower())

    def test_key_order_does_not_change_the_record_id(self):
        record = _record()
        reordered = dict(reversed(list(record.items())))
        self.assertEqual(canonical.judgment_record_id(record),
                         canonical.judgment_record_id(reordered))

    def test_any_payload_change_changes_the_record_id(self):
        record = _record()
        mutated = _record()
        mutated["payload"]["slug"] = "auth-svc"
        self.assertNotEqual(canonical.judgment_record_id(record),
                            canonical.judgment_record_id(mutated))

    def test_record_id_ignores_an_existing_record_id_and_checksum(self):
        # record_id is taken over the record MINUS record_id and checksum,
        # so computing it on an already-stamped record reproduces the same
        # value rather than folding the stamp into itself.
        record = _record()
        expected = canonical.judgment_record_id(record)
        stamped = dict(record, record_id="arch-judgment:sha256:" + "0" * 64,
                       checksum="sha256:" + "0" * 64)
        self.assertEqual(canonical.judgment_record_id(stamped), expected)

    def test_distinct_kinds_get_distinct_record_ids(self):
        record = _record()
        other = dict(record, kind="stale")
        self.assertNotEqual(canonical.judgment_record_id(record),
                            canonical.judgment_record_id(other))


class TestChecksum(unittest.TestCase):
    def test_checksum_has_the_frozen_shape(self):
        checksum = canonical.judgment_checksum(canonical.stamp(_record()))
        self.assertTrue(checksum.startswith("sha256:"))
        self.assertEqual(len(checksum.split(":")[-1]), 64)

    def test_checksum_covers_the_record_id(self):
        # The checksum is taken over the record minus `checksum` only, so a
        # tampered record_id does not verify.
        stamped = canonical.stamp(_record())
        tampered = dict(stamped, record_id="arch-judgment:sha256:" + "0" * 64)
        self.assertFalse(canonical.verify_checksum(tampered))

    def test_checksum_verifies_a_stamped_record(self):
        self.assertTrue(canonical.verify_checksum(canonical.stamp(_record())))

    def test_any_field_change_breaks_verification(self):
        for field, value in (("kind", "stale"),
                             ("arch_id", "arch-node:%s:%s" % (PROJECT_ID,
                                                              "c" * 32)),
                             ("decided_at", "2026-07-21T00:00:00Z"),
                             ("schema_version", 2)):
            with self.subTest(field=field):
                tampered = dict(canonical.stamp(_record()), **{field: value})
                self.assertFalse(canonical.verify_checksum(tampered))

    def test_a_nested_payload_change_breaks_verification(self):
        stamped = canonical.stamp(_record())
        stamped["payload"]["slug"] = "tampered"
        self.assertFalse(canonical.verify_checksum(stamped))

    def test_key_order_does_not_break_verification(self):
        stamped = canonical.stamp(_record())
        reordered = dict(reversed(list(stamped.items())))
        self.assertTrue(canonical.verify_checksum(reordered))

    def test_a_record_without_a_checksum_does_not_verify(self):
        self.assertFalse(canonical.verify_checksum(_record()))

    def test_verify_never_raises_on_junk(self):
        for junk in (None, "", 3, [], {}, {"checksum": None},
                     {"checksum": "sha256:nope"}):
            with self.subTest(value=junk):
                self.assertFalse(canonical.verify_checksum(junk))


class TestStamp(unittest.TestCase):
    def test_stamp_adds_both_envelope_fields(self):
        stamped = canonical.stamp(_record())
        self.assertIn("record_id", stamped)
        self.assertIn("checksum", stamped)

    def test_stamp_does_not_mutate_its_argument(self):
        record = _record()
        canonical.stamp(record)
        self.assertNotIn("record_id", record)
        self.assertNotIn("checksum", record)

    def test_stamp_is_deterministic(self):
        self.assertEqual(canonical.stamp(_record()), canonical.stamp(_record()))

    def test_restamping_is_idempotent(self):
        once = canonical.stamp(_record())
        self.assertEqual(canonical.stamp(once), once)


class TestDomainSeparation(unittest.TestCase):
    """The two digests are taken with distinct domain tags so a record_id
    digest can never be mistaken for -- or collide with -- a checksum."""

    def test_record_id_and_checksum_digests_differ(self):
        stamped = canonical.stamp(_record())
        self.assertNotEqual(stamped["record_id"].split(":")[-1],
                            stamped["checksum"].split(":")[-1])

    def test_canonical_bytes_are_compact_and_sorted(self):
        payload = canonical.canonical_record_bytes(_record())
        self.assertIsInstance(payload, bytes)
        text = payload.decode("utf-8")
        self.assertNotIn(", ", text)
        self.assertNotIn(": ", text)
        self.assertEqual(json.loads(text), _record())

    def test_canonical_bytes_honor_the_exclusion_set(self):
        stamped = canonical.stamp(_record())
        without = canonical.canonical_record_bytes(
            stamped, exclude=("record_id", "checksum"))
        self.assertEqual(json.loads(without.decode("utf-8")), _record())


if __name__ == "__main__":
    unittest.main()
