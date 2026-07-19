"""Conformance tests binding the hand-rolled validator to the JSON Schema.

jsonschema is test-only and optional; these tests skip when it is absent and
run under the pre-commit hook, which injects it.
"""

import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import document
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
CORPUS_DIR = os.path.join(REPO_ROOT, "testdata", "structural-graph", "v1")


def load_json(name):
    with open(os.path.join(SCHEMA_DIR, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def schema_and_native_codes():
    """Codes invariant-coverage.json says the JSON Schema can also reject."""
    codes = load_json("invariant-coverage.json")["codes"]
    return set(code for code, value in codes.items() if value == "schema-and-native")


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


BINDING_ID = "repository-binding:" + "0" * 31 + "1"
CONFIG = {
    "schema_version": 1,
    "repositories": [
        {"alias": "main", "binding_id": BINDING_ID, "provider": "github"}
    ],
}


def valid_doc():
    """A minimal document both the schema and the native validator accept."""
    return {
        "schema_version": 1,
        "binding_id": BINDING_ID,
        "source_commit": "a" * 40,
        "provider": {"name": "reference-json", "version": "1.0.0"},
        "capabilities": ["contains"],
        "root": "",
        "coverage": [
            {"path_prefix": "", "capability": "contains", "status": "observed"}
        ],
        "files": [{"path": "src/app.py"}],
        "symbols": [
            {"id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py"}
        ],
        "edges": [],
    }


def _drop(key):
    def mutate(doc):
        del doc[key]

    return mutate


def _set(key, value):
    def mutate(doc):
        doc[key] = value

    return mutate


def _set_in(key, index, subkey, value):
    def mutate(doc):
        doc[key][index][subkey] = value

    return mutate


# One demonstration per code classified "schema-and-native": a mutation of
# valid_doc that the JSON Schema rejects AND the native validator reports
# under that code. The classification claims both halves, so both are
# asserted -- an entry that only demonstrated one half would let a code be
# classified schema-and-native on the strength of a claim nothing tested.
SCHEMA_AND_NATIVE_CASES = {
    "E_SG_MISSING_SCHEMA_VERSION": _drop("schema_version"),
    "E_SG_UNSUPPORTED_SCHEMA_VERSION": _set("schema_version", 99),
    "E_SG_MISSING_FIELD": _drop("files"),
    "E_SG_UNKNOWN_FIELD": _set("surprise", True),
    "E_SG_MALFORMED_BINDING_ID": _set("binding_id", "not-a-binding-id"),
    "E_SG_MALFORMED_COMMIT": _set("source_commit", "nope"),
    "E_SG_MALFORMED_FIELD_SHAPE": _set("root", 5),
    "E_SG_UNKNOWN_SYMBOL_KIND": _set_in("symbols", 0, "kind", "gadget"),
    "E_SG_UNKNOWN_EDGE_TYPE": _set(
        "edges", [{"type": "frobnicates", "source": "sym-1", "target": "sym-1"}]
    ),
    "E_SG_UNKNOWN_CAPABILITY": _set("capabilities", ["telepathy"]),
    "E_SG_UNKNOWN_COVERAGE_STATUS": _set_in("coverage", 0, "status", "maybe"),
}

# The mirror image: one demonstration per code classified "native-only" --
# a document the JSON Schema accepts and only the native validator faults.
# Without these, "native-only" would be an unfalsifiable label.
NATIVE_ONLY_CASES = {
    "E_SG_COVERAGE_UNDECLARED_CAPABILITY": _set_in(
        "coverage", 0, "capability", "calls"
    ),
    "E_SG_DUPLICATE_SYMBOL_ID": _set(
        "symbols",
        [
            {"id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py"},
            {"id": "sym-1", "name": "dup", "kind": "module", "path": "src/app.py"},
        ],
    ),
    "E_SG_DANGLING_EDGE_ENDPOINT": _set(
        "edges", [{"type": "calls", "source": "sym-1", "target": "ghost"}]
    ),
    "E_SG_COVERAGE_GAP": _set_in("coverage", 0, "path_prefix", "src"),
    "E_SG_COVERAGE_OVERLAP": _set(
        "coverage",
        [
            {"path_prefix": "", "capability": "contains", "status": "observed"},
            {"path_prefix": "", "capability": "contains", "status": "observed"},
        ],
    ),
    "E_SG_UNNORMALIZABLE_ANCHOR": _set_in(
        "files", 0, "path", "~jane/repo/app.py"
    ),
    "E_SG_BINDING_NOT_CONFIGURED": _set(
        "binding_id", "repository-binding:" + "0" * 31 + "9"
    ),
}


def native_codes(doc):
    return set(f["code"] for f in document.load_object(doc, CONFIG)["findings"])


class TestClassificationIsDemonstrated(unittest.TestCase):
    """invariant-coverage.json's two classes must each be demonstrated.

    The design spec claims every classified code is backed by a case that
    actually exhibits the claimed behavior. These tests are what make that
    claim true rather than asserted: a code added to the file with no case
    here fails, and so does a case here for a code the file does not list.
    """

    def test_schema_and_native_codes_all_have_a_case(self):
        self.assertEqual(set(SCHEMA_AND_NATIVE_CASES), schema_and_native_codes())

    def test_native_only_codes_all_have_a_case(self):
        classified = load_json("invariant-coverage.json")["codes"]
        native_only = set(
            code for code, value in classified.items() if value == "native-only"
        )
        self.assertEqual(set(NATIVE_ONLY_CASES), native_only)


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
class TestSchemaRejectsWhatNativeRejects(unittest.TestCase):
    def setUp(self):
        self.validator = jsonschema.Draft7Validator(load_json("document.schema.json"))

    def test_valid_document_passes_schema(self):
        self.assertEqual(list(self.validator.iter_errors(valid_doc())), [])

    def test_valid_document_passes_native(self):
        self.assertEqual(document.load_object(valid_doc(), CONFIG)["status"], "loaded")

    def test_schema_and_native_cases_are_rejected_by_both(self):
        for code, mutate in sorted(SCHEMA_AND_NATIVE_CASES.items()):
            with self.subTest(code=code):
                doc = valid_doc()
                mutate(doc)
                self.assertTrue(
                    list(self.validator.iter_errors(doc)),
                    "schema accepted a document classified schema-and-native",
                )
                self.assertIn(code, native_codes(doc))

    def test_native_only_cases_are_accepted_by_the_schema(self):
        for code, mutate in sorted(NATIVE_ONLY_CASES.items()):
            with self.subTest(code=code):
                doc = valid_doc()
                mutate(doc)
                self.assertEqual(
                    list(self.validator.iter_errors(doc)),
                    [],
                    "schema rejected a document classified native-only",
                )
                self.assertIn(code, native_codes(doc))


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
class TestCorpusConformsToSchema(unittest.TestCase):
    """Every committed fixture document is validated against the schema.

    The acceptance criterion is that the corpus be committed *and*
    schema-validated, so this globs the fixtures off disk rather than
    trusting a hand-maintained list -- a fixture added to a category
    directory is covered the moment it lands.

    Which fixtures are meant to fail is derived, not restated: a fixture
    whose manifest expect_codes include any code classified
    "schema-and-native" must be rejected, and every other document must be
    accepted. That keeps this test and invariant-coverage.json from
    drifting into separate stories about the same corpus.
    """

    def setUp(self):
        self.validator = jsonschema.Draft7Validator(load_json("document.schema.json"))
        manifest = read_json(os.path.join(CORPUS_DIR, "manifest.json"))
        self.expected_invalid = set()
        rejectable = schema_and_native_codes()
        for entry in manifest["fixtures"]:
            path = entry.get("path")
            if path and set(entry.get("expect_codes") or []) & rejectable:
                self.expected_invalid.add(os.path.normpath(path))

    def _documents(self):
        # One category level deep: fixtures live in category directories
        # under the corpus root, and manifest.json sits at the root itself
        # and is not an interchange document.
        return sorted(glob.glob(os.path.join(CORPUS_DIR, "*", "*.json")))

    def test_corpus_is_not_empty(self):
        self.assertTrue(self._documents())

    def test_every_document_matches_its_expected_schema_verdict(self):
        for path in self._documents():
            rel = os.path.normpath(os.path.relpath(path, CORPUS_DIR))
            with self.subTest(fixture=rel):
                errors = list(self.validator.iter_errors(read_json(path)))
                if rel in self.expected_invalid:
                    self.assertTrue(
                        errors, "fixture is expected to violate the schema"
                    )
                else:
                    self.assertEqual(
                        errors, [], "fixture is expected to satisfy the schema"
                    )


if __name__ == "__main__":
    unittest.main()
