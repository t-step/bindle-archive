"""Reading judgments.jsonl back with its integrity rules (#228).

#228 freezes the recovery story that `append_line_atomic`'s durability-but-
not-crash-atomicity leaves open: a torn TRAILING line is truncated-and-
reported, corruption anywhere else HARD ABORTS, and records fold
last-write-wins by FILE ORDER.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import canonical
from architecture import judgments

PROJECT_ID = "project:" + "a" * 32
OTHER_PROJECT_ID = "project:" + "c" * 32
ARCH_ID = "arch-node:" + PROJECT_ID + ":" + "b" * 32
OTHER_ARCH_ID = "arch-node:" + PROJECT_ID + ":" + "d" * 32


def _judgment_body(**overrides):
    body = {
        "schema_version": 1,
        "kind": "identity_allocation",
        "project_id": PROJECT_ID,
        "decided_at": "2026-07-20T12:00:00Z",
        "arch_id": ARCH_ID,
    }
    body.update(overrides)
    return body


def _record(**overrides):
    return canonical.stamp(_judgment_body(**overrides))


def _line(record):
    return json.dumps(record, sort_keys=True) + "\n"


class _LogCase(unittest.TestCase):
    """Writes raw bytes rather than fixtures: a torn log is defined by its
    missing trailing newline, which no .json fixture can carry."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "judgments.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return text

    def codes(self, findings):
        return [f["code"] for f in findings]


class TestEmptyAuthority(_LogCase):
    """An absent or empty log is a legitimate empty authority: a fresh
    project mints its first identity against it."""

    def test_missing_file_reads_as_no_records(self):
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["truncate_offset"])

    def test_zero_byte_file_reads_as_no_records(self):
        self.write("")
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["findings"], [])


class TestFileOrder(_LogCase):
    def test_records_are_returned_in_file_order(self):
        first = _record(arch_id=ARCH_ID)
        second = _record(arch_id=OTHER_ARCH_ID)
        self.write(_line(first) + _line(second))
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(
            [r["arch_id"] for r in result["records"]], [ARCH_ID, OTHER_ARCH_ID])
        self.assertEqual(result["findings"], [])


class TestTornTail(_LogCase):
    """#228: a torn TRAILING line is truncated-and-reported, never silently
    skipped — silently skipping drops every identity after the tear."""

    def test_torn_tail_keeps_prior_records_and_reports(self):
        good = _line(_record())
        torn = json.dumps(_record(arch_id=OTHER_ARCH_ID))[:40]
        self.write(good + torn)
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(len(result["records"]), 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["truncate_offset"], len(good.encode("utf-8")))
        self.assertEqual(
            self.codes(result["findings"]), ["E_ARCH_JUDGMENTS_TORN_TAIL"])

    def test_reader_does_not_repair_the_log(self):
        good = _line(_record())
        text = self.write(good + json.dumps(_record(arch_id=OTHER_ARCH_ID))[:40])
        judgments.load_judgments(self.path, PROJECT_ID)
        with open(self.path, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), text)

    def test_unterminated_but_intact_tail_is_kept_and_reported(self):
        good = _line(_record())
        intact = json.dumps(_record(arch_id=OTHER_ARCH_ID), sort_keys=True)
        self.write(good + intact)
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(len(result["records"]), 2)
        self.assertFalse(result["truncated"])
        self.assertEqual(
            self.codes(result["findings"]),
            ["E_ARCH_JUDGMENTS_UNTERMINATED_TAIL"])

    def test_terminated_final_line_is_not_a_torn_tail(self):
        self.write(_line(_record()) + "{not json}\n")
        with self.assertRaises(judgments.JudgmentsCorruptError) as raised:
            judgments.load_judgments(self.path, PROJECT_ID)
        self.assertIn(
            "E_ARCH_JUDGMENTS_UNPARSEABLE_LINE", self.codes(raised.exception.findings))


class TestHardAbort(_LogCase):
    """#228: corruption anywhere but the tail HARD ABORTS — the authority is
    damaged and the run must not guess."""

    def test_unparseable_interior_line_aborts(self):
        self.write(_line(_record()) + "{torn\n" + _line(_record(arch_id=OTHER_ARCH_ID)))
        with self.assertRaises(judgments.JudgmentsCorruptError) as raised:
            judgments.load_judgments(self.path, PROJECT_ID)
        findings = raised.exception.findings
        self.assertEqual(
            self.codes(findings), ["E_ARCH_JUDGMENTS_UNPARSEABLE_LINE"])
        self.assertEqual(findings[0]["index"], 1)

    def test_checksum_mismatch_aborts(self):
        tampered = _record()
        tampered["decided_at"] = "2026-07-20T13:00:00Z"
        self.write(_line(tampered) + _line(_record(arch_id=OTHER_ARCH_ID)))
        with self.assertRaises(judgments.JudgmentsCorruptError) as raised:
            judgments.load_judgments(self.path, PROJECT_ID)
        codes = self.codes(raised.exception.findings)
        self.assertIn("E_ARCH_JUDGMENTS_INVALID_RECORD", codes)
        self.assertIn("E_ARCH_JUDGMENT_CHECKSUM_MISMATCH", codes)

    def test_schema_invalid_record_aborts(self):
        self.write(_line(_record(kind="observed_fact")))
        with self.assertRaises(judgments.JudgmentsCorruptError) as raised:
            judgments.load_judgments(self.path, PROJECT_ID)
        codes = self.codes(raised.exception.findings)
        self.assertIn("E_ARCH_JUDGMENTS_INVALID_RECORD", codes)
        self.assertIn("E_ARCH_JUDGMENT_BAD_KIND", codes)

    def test_json_scalar_line_aborts(self):
        self.write("42\n" + _line(_record()))
        with self.assertRaises(judgments.JudgmentsCorruptError):
            judgments.load_judgments(self.path, PROJECT_ID)


class TestBlankLines(_LogCase):
    """A blank interior line is unparseable JSON, so the frozen rule aborts
    on it. context_graph.ledger skips blanks; this log is machine-written
    only, so a blank between records means something wrote it wrong."""

    def test_interior_blank_line_aborts(self):
        self.write(_line(_record()) + "\n" + _line(_record(arch_id=OTHER_ARCH_ID)))
        with self.assertRaises(judgments.JudgmentsCorruptError) as raised:
            judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(
            self.codes(raised.exception.findings), ["E_ARCH_JUDGMENTS_BLANK_LINE"])

    def test_trailing_blank_line_is_ignored(self):
        self.write(_line(_record()) + "\n")
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["findings"], [])


class TestForeignProject(_LogCase):
    """The guarded scenario is a COPIED notes home: the log is full of
    another project's identities and a caller must not be able to ignore
    a return value."""

    def test_foreign_project_id_record_raises(self):
        foreign = canonical.stamp({
            "schema_version": 1,
            "kind": "naming",
            "project_id": OTHER_PROJECT_ID,
            "decided_at": "2026-07-20T12:00:00Z",
        })
        self.write(_line(_record()) + _line(foreign))
        with self.assertRaises(judgments.ProjectIdMismatchError) as raised:
            judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(raised.exception.found, OTHER_PROJECT_ID)
        self.assertEqual(raised.exception.expected, PROJECT_ID)


class TestDuplicateAppend(_LogCase):
    """stamp() is idempotent, so a duplicated append is an exact record_id
    repeat — reported, not fatal, and a no-op once folded."""

    def test_duplicate_record_id_is_reported(self):
        line = _line(_record())
        self.write(line + line)
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(
            self.codes(result["findings"]), ["E_ARCH_JUDGMENTS_DUPLICATE_RECORD"])


class TestFold(unittest.TestCase):
    """#228: records fold last-write-wins by FILE ORDER for a given arch_id;
    decided_at is audit only, so a clock skew cannot reorder meaning."""

    def test_empty_log_folds_to_nothing(self):
        folded = judgments.fold_judgments([])
        self.assertEqual(folded["by_arch_id"], {})
        self.assertEqual(folded["latest_by_kind"], {})
        self.assertEqual(folded["unkeyed"], [])

    def test_records_are_grouped_per_arch_id_in_file_order(self):
        first = _record(kind="naming", decided_at="2026-07-20T10:00:00Z")
        second = _record(kind="naming", decided_at="2026-07-20T11:00:00Z")
        other = _record(arch_id=OTHER_ARCH_ID)
        folded = judgments.fold_judgments([first, second, other])
        self.assertEqual(folded["by_arch_id"][ARCH_ID], [first, second])
        self.assertEqual(folded["by_arch_id"][OTHER_ARCH_ID], [other])

    def test_file_order_wins_over_an_earlier_decided_at(self):
        first = _record(kind="naming", decided_at="2026-07-20T11:00:00Z")
        second = _record(kind="naming", decided_at="2026-07-20T09:00:00Z")
        folded = judgments.fold_judgments([first, second])
        self.assertEqual(folded["latest_by_kind"][ARCH_ID]["naming"], second)

    def test_a_later_kind_does_not_erase_an_earlier_one(self):
        allocation = _record(kind="identity_allocation")
        naming = _record(kind="naming", decided_at="2026-07-20T13:00:00Z")
        folded = judgments.fold_judgments([allocation, naming])
        latest = folded["latest_by_kind"][ARCH_ID]
        self.assertEqual(latest["identity_allocation"], allocation)
        self.assertEqual(latest["naming"], naming)

    def test_records_naming_no_single_node_are_unkeyed(self):
        merge = canonical.stamp({
            "schema_version": 1,
            "kind": "merge",
            "project_id": PROJECT_ID,
            "decided_at": "2026-07-20T12:00:00Z",
        })
        folded = judgments.fold_judgments([_record(), merge])
        self.assertEqual(folded["unkeyed"], [merge])
        self.assertEqual(list(folded["by_arch_id"]), [ARCH_ID])

    def test_an_exact_duplicate_append_folds_to_a_no_op(self):
        record = _record()
        folded = judgments.fold_judgments([record, dict(record)])
        self.assertEqual(folded["by_arch_id"][ARCH_ID], [record])


class TestAppend(_LogCase):
    """The write side of the same envelope: one atomic append per decision,
    stamped so a reader can verify it."""

    def test_appended_record_reads_back(self):
        judgments.append_judgment(self.path, _judgment_body())
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["findings"], [])

    def test_append_stamps_an_unstamped_body(self):
        stamped = judgments.append_judgment(self.path, _judgment_body())
        self.assertTrue(canonical.verify_checksum(stamped))
        self.assertEqual(stamped["record_id"], canonical.judgment_record_id(stamped))

    def test_append_creates_the_architecture_directory(self):
        nested = os.path.join(self.tmp, "projects", "p", ".bindle",
                              "architecture", "judgments.jsonl")
        judgments.append_judgment(nested, _judgment_body())
        self.assertTrue(os.path.exists(nested))

    def test_append_never_rewrites_earlier_records(self):
        judgments.append_judgment(self.path, _judgment_body())
        judgments.append_judgment(
            self.path, _judgment_body(arch_id=OTHER_ARCH_ID, kind="naming"))
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual(
            [r["arch_id"] for r in result["records"]], [ARCH_ID, OTHER_ARCH_ID])

    def test_append_refuses_an_invalid_record(self):
        with self.assertRaises(judgments.JudgmentsCorruptError):
            judgments.append_judgment(self.path, _judgment_body(kind="observed_fact"))
        self.assertFalse(os.path.exists(self.path))


class TestIdentityCommitOrdering(_LogCase):
    """#228 (frozen): THE IDENTITY COMMIT IS ONE ATOMIC APPEND THAT PRECEDES
    ANY FILE WRITE. Appending after the writes would force recovery to read
    arch_id out of apply-state.json (making recovery metadata a semantic
    authority) or out of the note (forbidden)."""

    def test_the_append_precedes_the_write(self):
        calls = []
        original = judgments.atomic_io.append_line_atomic

        def tracking_append(path, line_obj):
            calls.append("append")
            return original(path, line_obj)

        with unittest.mock.patch.object(
                judgments.atomic_io, "append_line_atomic", tracking_append):
            judgments.commit_identity_then(
                self.path, _judgment_body(), lambda: calls.append("write"))
        self.assertEqual(calls, ["append", "write"])

    def test_a_failed_append_never_reaches_the_write(self):
        calls = []

        def failing_append(path, line_obj):
            raise OSError("Simulated ENOSPC")

        with unittest.mock.patch.object(
                judgments.atomic_io, "append_line_atomic", failing_append):
            with self.assertRaises(OSError):
                judgments.commit_identity_then(
                    self.path, _judgment_body(), lambda: calls.append("write"))
        self.assertEqual(calls, [])

    def test_a_crash_in_the_write_leaves_the_identity_recorded(self):
        def crashing_write():
            raise OSError("Simulated crash after the identity commit")

        with self.assertRaises(OSError):
            judgments.commit_identity_then(
                self.path, _judgment_body(), crashing_write)
        result = judgments.load_judgments(self.path, PROJECT_ID)
        self.assertEqual([r["arch_id"] for r in result["records"]], [ARCH_ID])

    def test_it_returns_the_stamped_record(self):
        stamped = judgments.commit_identity_then(
            self.path, _judgment_body(), lambda: None)
        self.assertTrue(canonical.verify_checksum(stamped))


if __name__ == "__main__":
    unittest.main()
