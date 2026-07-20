"""Fixture-corpus conformance for the four architecture state files (#228).

Two assertions over one corpus. The NATIVE half runs unconditionally: every
fixture's findings must equal the manifest's `expect_codes` exactly, so a
validator that stops producing a code, or starts producing an extra one, is
caught. The SCHEMA half needs `jsonschema` (a test-only, optional
dependency, so it skips when absent) and cross-checks the hand-rolled
validator against a real off-the-shelf engine.

The schema half asserts BOTH directions, which the context-graph original
deliberately does not: a fixture the native validator accepts must be
schema-valid, AND a fixture rejected solely by `schema-and-native` codes
must be schema-INVALID. That second direction is only sound because
schemas/architecture/v1/invariant-coverage.json classifies each code —
cross-object, uniqueness, ordering, and hashing invariants are
`native-only` because draft-07 cannot state them, and a fixture invalid
only via one of those is legitimately schema-valid on its own.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import state

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCHEMA_DIR = os.path.join(REPO_ROOT, "schemas", "architecture", "v1")
TESTDATA_DIR = os.path.join(REPO_ROOT, "testdata", "architecture", "v1")

SCHEMA_FOR_TYPE = {
    "config": "config.schema.json",
    "index": "index.schema.json",
    "judgment": "judgment.schema.json",
    "apply-state": "apply-state.schema.json",
}

VALIDATOR_FOR_TYPE = {
    "config": state.validate_config,
    "index": state.validate_index,
    "judgment": state.validate_judgment,
    "apply-state": state.validate_apply_state,
}


def _load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _manifest():
    return _load_json(os.path.join(TESTDATA_DIR, "manifest.json"))


def _coverage():
    return _load_json(os.path.join(SCHEMA_DIR, "invariant-coverage.json"))["codes"]


class TestNativeConformance(unittest.TestCase):
    """The native validators against the whole corpus. No optional
    dependency, so this half always runs."""

    def setUp(self):
        self.manifest = _manifest()
        self.coverage = _coverage()

    def test_the_corpus_is_not_empty(self):
        self.assertTrue(self.manifest["fixtures"])

    def test_every_fixture_produces_exactly_its_expected_codes(self):
        for entry in self.manifest["fixtures"]:
            with self.subTest(fixture=entry["id"], path=entry["path"]):
                document = _load_json(os.path.join(TESTDATA_DIR, entry["path"]))
                validate = VALIDATOR_FOR_TYPE[entry["document_type"]]
                codes = sorted({f["code"] for f in validate(document)})
                self.assertEqual(codes, sorted(entry["expect_codes"]))

    def test_expect_valid_agrees_with_the_findings(self):
        for entry in self.manifest["fixtures"]:
            with self.subTest(fixture=entry["id"]):
                self.assertEqual(entry["expect_valid"], not entry["expect_codes"])

    def test_every_expected_code_is_classified(self):
        for entry in self.manifest["fixtures"]:
            for code in entry["expect_codes"]:
                with self.subTest(code=code):
                    self.assertIn(code, self.coverage)

    def test_every_classified_code_has_a_known_classification(self):
        for code, classification in self.coverage.items():
            with self.subTest(code=code):
                self.assertIn(classification, ("schema-and-native", "native-only"))

    def test_every_document_type_is_covered_by_a_fixture(self):
        seen = {entry["document_type"] for entry in self.manifest["fixtures"]}
        self.assertEqual(seen, set(SCHEMA_FOR_TYPE))

    def test_every_document_type_has_a_valid_and_an_invalid_fixture(self):
        for document_type in SCHEMA_FOR_TYPE:
            verdicts = {entry["expect_valid"]
                        for entry in self.manifest["fixtures"]
                        if entry["document_type"] == document_type}
            with self.subTest(document_type=document_type):
                self.assertEqual(verdicts, {True, False})

    def test_every_manifest_path_exists_and_every_fixture_is_in_the_manifest(self):
        listed = {entry["path"] for entry in self.manifest["fixtures"]}
        for path in listed:
            with self.subTest(path=path):
                self.assertTrue(os.path.exists(os.path.join(TESTDATA_DIR, path)))
        on_disk = set()
        for dirpath, _dirnames, filenames in os.walk(TESTDATA_DIR):
            for name in filenames:
                if not name.endswith(".json") or name == "manifest.json":
                    continue
                full = os.path.join(dirpath, name)
                on_disk.add(os.path.relpath(full, TESTDATA_DIR))
        self.assertEqual(on_disk, listed)


@unittest.skipUnless(
    HAVE_JSONSCHEMA,
    "jsonschema not installed (test-only dependency; skipped locally)")
class TestSchemaConformance(unittest.TestCase):
    def setUp(self):
        self.manifest = _manifest()
        self.coverage = _coverage()
        self.schemas = {key: _load_json(os.path.join(SCHEMA_DIR, name))
                        for key, name in SCHEMA_FOR_TYPE.items()}

    def _is_schema_valid(self, document, schema):
        try:
            jsonschema.validate(document, schema)
        except jsonschema.ValidationError:
            return False
        return True

    def test_every_schema_is_itself_a_valid_draft07_schema(self):
        for key, schema in self.schemas.items():
            with self.subTest(schema=key):
                jsonschema.Draft7Validator.check_schema(schema)

    def test_natively_valid_fixtures_are_schema_valid(self):
        for entry in self.manifest["fixtures"]:
            if not entry["expect_valid"]:
                continue
            with self.subTest(fixture=entry["id"], path=entry["path"]):
                document = _load_json(os.path.join(TESTDATA_DIR, entry["path"]))
                self.assertTrue(
                    self._is_schema_valid(
                        document, self.schemas[entry["document_type"]]),
                    "%s is native-valid but schema-invalid" % (entry["path"],))

    def test_schema_representable_failures_are_also_schema_invalid(self):
        for entry in self.manifest["fixtures"]:
            codes = entry["expect_codes"]
            if not codes:
                continue
            if any(self.coverage[code] == "native-only" for code in codes):
                # Invalid only via an invariant draft-07 cannot state, so
                # the document is legitimately schema-valid on its own.
                continue
            with self.subTest(fixture=entry["id"], path=entry["path"]):
                document = _load_json(os.path.join(TESTDATA_DIR, entry["path"]))
                self.assertFalse(
                    self._is_schema_valid(
                        document, self.schemas[entry["document_type"]]),
                    "%s is rejected natively by %s but passes its schema"
                    % (entry["path"], codes))

    def test_a_native_only_fixture_really_is_schema_valid(self):
        # Guards the classification itself: if a `native-only` code became
        # schema-expressible, the skip above would be silently over-broad.
        checked = 0
        for entry in self.manifest["fixtures"]:
            codes = entry["expect_codes"]
            if not codes or not all(
                    self.coverage[code] == "native-only" for code in codes):
                continue
            document = _load_json(os.path.join(TESTDATA_DIR, entry["path"]))
            with self.subTest(fixture=entry["id"], path=entry["path"]):
                self.assertTrue(
                    self._is_schema_valid(
                        document, self.schemas[entry["document_type"]]),
                    "%s is classified native-only but its schema rejects it"
                    % (entry["path"],))
            checked += 1
        self.assertTrue(checked, "no native-only fixture in the corpus")


if __name__ == "__main__":
    unittest.main()
