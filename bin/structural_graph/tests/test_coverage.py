"""Unit tests for structural_graph.coverage."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import coverage


def codes(findings):
    return [f["code"] for f in findings]


class TestTilingFindings(unittest.TestCase):
    def test_single_root_entry_per_capability_tiles(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {"path_prefix": "", "capability": "calls", "status": "unsupported"},
        ]
        self.assertEqual(
            coverage.tiling_findings("", ["contains", "calls"], entries), []
        )

    def test_nested_override_is_allowed(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {
                "path_prefix": "vendor",
                "capability": "contains",
                "status": "partial_parse_failure",
            },
        ]
        self.assertEqual(coverage.tiling_findings("", ["contains"], entries), [])

    def test_missing_root_entry_is_a_gap(self):
        entries = [
            {"path_prefix": "src", "capability": "contains", "status": "observed"}
        ]
        self.assertIn(
            "E_SG_COVERAGE_GAP",
            codes(coverage.tiling_findings("", ["contains"], entries)),
        )

    def test_capability_with_no_entry_at_all_is_a_gap(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"}
        ]
        self.assertIn(
            "E_SG_COVERAGE_GAP",
            codes(coverage.tiling_findings("", ["contains", "calls"], entries)),
        )

    def test_duplicate_prefix_for_one_capability_is_an_overlap(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {"path_prefix": "", "capability": "contains", "status": "unsupported"},
        ]
        self.assertIn(
            "E_SG_COVERAGE_OVERLAP",
            codes(coverage.tiling_findings("", ["contains"], entries)),
        )

    def test_same_prefix_for_different_capabilities_is_not_an_overlap(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {"path_prefix": "", "capability": "calls", "status": "observed"},
            {"path_prefix": "vendor", "capability": "contains", "status": "unsupported"},
            {"path_prefix": "vendor", "capability": "calls", "status": "unsupported"},
        ]
        self.assertEqual(
            coverage.tiling_findings("", ["contains", "calls"], entries), []
        )

    def test_entry_outside_root_is_a_gap(self):
        entries = [
            {"path_prefix": "pkg", "capability": "contains", "status": "observed"},
            {"path_prefix": "other", "capability": "contains", "status": "observed"},
        ]
        self.assertIn(
            "E_SG_COVERAGE_GAP",
            codes(coverage.tiling_findings("pkg", ["contains"], entries)),
        )

    def test_nonempty_root_tiles_from_its_own_prefix(self):
        entries = [
            {"path_prefix": "pkg", "capability": "contains", "status": "observed"}
        ]
        self.assertEqual(coverage.tiling_findings("pkg", ["contains"], entries), [])

    def test_triple_duplicate_prefix_reports_two_overlaps(self):
        # N-1 overlaps for N duplicates at one prefix: the first occurrence
        # establishes the prefix, each later occurrence at the same prefix
        # is a distinct overlap against it. Untested by inspection until now
        # (#227 review finding, minor).
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {"path_prefix": "vendor", "capability": "contains", "status": "observed"},
            {"path_prefix": "vendor", "capability": "contains", "status": "unsupported"},
            {
                "path_prefix": "vendor",
                "capability": "contains",
                "status": "partial_parse_failure",
            },
        ]
        found = coverage.tiling_findings("", ["contains"], entries)
        overlaps = [f for f in found if f["code"] == "E_SG_COVERAGE_OVERLAP"]
        self.assertEqual([f["index"] for f in overlaps], [2, 3])


class TestDoesNotRaiseOnMalformedDocumentContent(unittest.TestCase):
    """#227 review finding: coverage.py is called directly by its own tests,

    bypassing validate_document, so these entries and capabilities arrive
    without the shape guarantee validate_document would normally have
    already enforced. The contract under test is narrower than "never
    raise on anything": these functions must not raise on a malformed
    *value* inside an otherwise well-formed entries list or capabilities
    list -- a None path_prefix, a capability that's a list instead of a
    string. validation.py owns the finding for a non-string path_prefix
    (see test_validation.py); this module only has to survive it. A
    malformed *argument* (entries or capabilities of the wrong type
    outright) is caller error and is out of scope here -- see the
    contract note in coverage.py's module docstring.
    """

    def test_status_for_does_not_raise_on_none_path_prefix(self):
        entries = [{"path_prefix": None, "capability": "contains", "status": "observed"}]
        try:
            result = coverage.status_for(entries, "contains", "src/app.py")
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("status_for raised %r" % (exc,))
        self.assertIsNone(result)

    def test_status_for_does_not_raise_on_int_path_prefix(self):
        entries = [{"path_prefix": 5, "capability": "contains", "status": "observed"}]
        try:
            coverage.status_for(entries, "contains", "src/app.py")
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("status_for raised %r" % (exc,))

    def test_status_for_does_not_raise_on_list_path_prefix(self):
        entries = [
            {"path_prefix": ["src"], "capability": "contains", "status": "observed"}
        ]
        try:
            coverage.status_for(entries, "contains", "src/app.py")
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("status_for raised %r" % (exc,))

    def test_status_for_does_not_raise_on_dict_path_prefix(self):
        entries = [
            {"path_prefix": {"a": 1}, "capability": "contains", "status": "observed"}
        ]
        try:
            coverage.status_for(entries, "contains", "src/app.py")
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("status_for raised %r" % (exc,))

    def test_tiling_findings_does_not_raise_on_none_path_prefix(self):
        entries = [{"path_prefix": None, "capability": "contains", "status": "observed"}]
        try:
            coverage.tiling_findings("src/app.py", ["contains"], entries)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("tiling_findings raised %r" % (exc,))

    def test_tiling_findings_does_not_raise_on_int_path_prefix(self):
        entries = [{"path_prefix": 5, "capability": "contains", "status": "observed"}]
        try:
            coverage.tiling_findings("src/app.py", ["contains"], entries)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("tiling_findings raised %r" % (exc,))

    def test_tiling_findings_does_not_raise_on_list_path_prefix(self):
        entries = [
            {"path_prefix": ["src"], "capability": "contains", "status": "observed"}
        ]
        try:
            coverage.tiling_findings("src/app.py", ["contains"], entries)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("tiling_findings raised %r" % (exc,))

    def test_tiling_findings_does_not_raise_on_dict_path_prefix(self):
        entries = [
            {"path_prefix": {"a": 1}, "capability": "contains", "status": "observed"}
        ]
        try:
            coverage.tiling_findings("src/app.py", ["contains"], entries)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("tiling_findings raised %r" % (exc,))

    def test_tiling_findings_does_not_raise_on_unhashable_capability(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"}
        ]
        try:
            coverage.tiling_findings("", ["contains", ["nested"]], entries)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("tiling_findings raised %r" % (exc,))

    def test_tiling_findings_does_not_raise_on_incomparable_capabilities(self):
        entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"}
        ]
        try:
            coverage.tiling_findings("", ["contains", 5], entries)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("tiling_findings raised %r" % (exc,))


class TestStatusFor(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {
                "path_prefix": "vendor",
                "capability": "contains",
                "status": "partial_parse_failure",
            },
            {
                "path_prefix": "vendor/deep",
                "capability": "contains",
                "status": "unsupported",
            },
        ]

    def test_root_status_applies_by_default(self):
        self.assertEqual(
            coverage.status_for(self.entries, "contains", "src/app.py"), "observed"
        )

    def test_longest_prefix_wins(self):
        self.assertEqual(
            coverage.status_for(self.entries, "contains", "vendor/lib.py"),
            "partial_parse_failure",
        )
        self.assertEqual(
            coverage.status_for(self.entries, "contains", "vendor/deep/x.py"),
            "unsupported",
        )

    def test_prefix_matches_on_segment_boundary_only(self):
        self.assertEqual(
            coverage.status_for(self.entries, "contains", "vendorish/x.py"),
            "observed",
        )

    def test_undeclared_capability_is_none_not_a_status(self):
        self.assertIsNone(coverage.status_for(self.entries, "calls", "src/app.py"))


if __name__ == "__main__":
    unittest.main()
