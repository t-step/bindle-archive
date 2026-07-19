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
