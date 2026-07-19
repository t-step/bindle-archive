"""Unit tests for structural_graph.schema."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import schema


class TestVocabularies(unittest.TestCase):
    def test_supported_versions_contains_current(self):
        self.assertIn(schema.SCHEMA_VERSION, schema.SUPPORTED_SCHEMA_VERSIONS)

    def test_symbol_kinds_have_other_escape(self):
        self.assertIn("other", schema.SYMBOL_KINDS)

    def test_vocabularies_are_unique_nonempty_tuples(self):
        for name in (
            "SUPPORTED_SCHEMA_VERSIONS",
            "SYMBOL_KINDS",
            "EDGE_TYPES",
            "CAPABILITIES",
            "COVERAGE_STATUSES",
            "DOCUMENT_STATUSES",
            "FRESHNESS_STATES",
            "ANCHOR_FIELDS",
        ):
            value = getattr(schema, name)
            self.assertIsInstance(value, tuple, name)
            self.assertTrue(value, name)
            self.assertEqual(len(value), len(set(value)), name)

    def test_coverage_statuses_are_the_three_frozen_values(self):
        self.assertEqual(
            schema.COVERAGE_STATUSES,
            ("observed", "unsupported", "partial_parse_failure"),
        )


class TestIsAnchor(unittest.TestCase):
    def test_file_path_is_an_anchor(self):
        self.assertTrue(schema.is_anchor("files[].path"))

    def test_edge_endpoints_are_anchors(self):
        self.assertTrue(schema.is_anchor("edges[].source"))
        self.assertTrue(schema.is_anchor("edges[].target"))

    def test_coverage_prefix_is_an_anchor(self):
        self.assertTrue(schema.is_anchor("coverage[].path_prefix"))

    def test_diagnostics_are_not_anchors(self):
        self.assertFalse(schema.is_anchor("diagnostics[].message"))

    def test_optional_observations_are_never_anchors(self):
        self.assertFalse(
            schema.is_anchor("optional_provider_observations.routes[].path")
        )

    def test_unknown_field_is_not_an_anchor(self):
        self.assertFalse(schema.is_anchor("nope[].nothing"))


if __name__ == "__main__":
    unittest.main()
