"""Conformance tests binding the hand-rolled validator to the JSON Schema.

jsonschema is test-only and optional; these tests skip when it is absent and
run under the pre-commit hook, which injects it.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import schema as sg_schema
from structural_graph import validation

try:
    import jsonschema

    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
SCHEMA_DIR = os.path.join(REPO_ROOT, "schemas", "structural-graph", "v1")


def load_json(name):
    with open(os.path.join(SCHEMA_DIR, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


class TestInvariantCoverage(unittest.TestCase):
    def test_every_finding_code_is_classified(self):
        coverage = load_json("invariant-coverage.json")
        classified = set(coverage["codes"])
        self.assertEqual(classified, set(validation.FINDING_CODES))

    def test_every_classification_is_a_known_value(self):
        coverage = load_json("invariant-coverage.json")
        for code, value in coverage["codes"].items():
            self.assertIn(value, ("schema-and-native", "native-only"), code)


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
class TestSchemaMirrorsVocabularies(unittest.TestCase):
    def setUp(self):
        self.document_schema = load_json("document.schema.json")

    def test_schema_version_is_pinned(self):
        self.assertEqual(
            self.document_schema["properties"]["schema_version"]["const"],
            sg_schema.SCHEMA_VERSION,
        )

    def test_symbol_kinds_mirror_exactly(self):
        enum = self.document_schema["properties"]["symbols"]["items"]["properties"][
            "kind"
        ]["enum"]
        self.assertEqual(tuple(enum), sg_schema.SYMBOL_KINDS)

    def test_edge_types_mirror_exactly(self):
        enum = self.document_schema["properties"]["edges"]["items"]["properties"][
            "type"
        ]["enum"]
        self.assertEqual(tuple(enum), sg_schema.EDGE_TYPES)

    def test_capabilities_mirror_exactly(self):
        enum = self.document_schema["properties"]["capabilities"]["items"]["enum"]
        self.assertEqual(tuple(enum), sg_schema.CAPABILITIES)

    def test_coverage_statuses_mirror_exactly(self):
        enum = self.document_schema["properties"]["coverage"]["items"]["properties"][
            "status"
        ]["enum"]
        self.assertEqual(tuple(enum), sg_schema.COVERAGE_STATUSES)


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
class TestSchemaRejectsWhatNativeRejects(unittest.TestCase):
    def setUp(self):
        self.validator = jsonschema.Draft7Validator(load_json("document.schema.json"))

    def _doc(self):
        return {
            "schema_version": 1,
            "binding_id": "repository-binding:" + "0" * 31 + "1",
            "source_commit": "a" * 40,
            "provider": {"name": "reference-json", "version": "1.0.0"},
            "capabilities": ["contains"],
            "root": "",
            "coverage": [
                {"path_prefix": "", "capability": "contains", "status": "observed"}
            ],
            "files": [{"path": "src/app.py"}],
            "symbols": [
                {
                    "id": "sym-1",
                    "name": "app",
                    "kind": "module",
                    "path": "src/app.py",
                }
            ],
            "edges": [],
        }

    def test_valid_document_passes_schema(self):
        self.assertEqual(list(self.validator.iter_errors(self._doc())), [])

    def test_unknown_symbol_kind_rejected(self):
        doc = self._doc()
        doc["symbols"][0]["kind"] = "gadget"
        self.assertTrue(list(self.validator.iter_errors(doc)))

    def test_unknown_top_level_field_rejected(self):
        doc = self._doc()
        doc["surprise"] = True
        self.assertTrue(list(self.validator.iter_errors(doc)))

    def test_malformed_commit_rejected(self):
        doc = self._doc()
        doc["source_commit"] = "nope"
        self.assertTrue(list(self.validator.iter_errors(doc)))


if __name__ == "__main__":
    unittest.main()
