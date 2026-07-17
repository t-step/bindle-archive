import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCHEMA_DIR = os.path.join(REPO_ROOT, "schemas", "context-graph", "v1")
TESTDATA_DIR = os.path.join(REPO_ROOT, "testdata", "context-graph", "v1")

OBJECT_SCHEMA_MAP = {
    "config": "config.schema.json",
    "nodes": "node.schema.json",
    "edges": "edge.schema.json",
    "proposals": "proposal.schema.json",
    "candidates": "candidate.schema.json",
    "judgments": "judgment.schema.json",
}


def _load_schema(name):
    with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed (test-only dependency; skipped locally)")
class TestSchemaConformance(unittest.TestCase):
    """Every schema-and-native-classified invariant must agree between the
    native validator (bin/context_graph/validation.py, already exercised by
    every fixture-manifest run) and a real off-the-shelf JSON Schema
    validator over the same fixture corpus — never a hand-rolled schema
    engine (design section 11).

    This test only asserts schema conformance for fixtures the manifest
    marks `expect_valid: true`. Many fixtures are intentionally INVALID via
    native-only invariants (cross-object checks, hashing, uniqueness — see
    schemas/context-graph/v1/invariant-coverage.json's `native-only`
    classifications) that JSON Schema literally cannot express: an
    individual object drawn from one of those bundles can still be
    perfectly schema-valid on its own even though the bundle as a whole is
    native-invalid. Blanket-checking every fixture (valid and invalid
    alike) therefore produces false failures on those bundles — that is a
    bug in this test's design, not a real corpus defect. The useful
    direction to test here is "does the schema wrongly reject something the
    native validator considers fully valid," not "does the schema also
    reject everything native rejects" — fully testing schema-and-native
    agreement per schema-representable invariant (asserting the schema also
    rejects the specific `schema-and-native`-classified invalid fixtures) is
    a reasonable follow-up for a later task, not something this test
    attempts.
    """

    @classmethod
    def setUpClass(cls):
        cls.schemas = {key: _load_schema(name) for key, name in OBJECT_SCHEMA_MAP.items()}
        cls.expect_valid_by_path = cls._load_expect_valid_map()

    @classmethod
    def _load_expect_valid_map(cls):
        """Build path -> expect_valid from manifest.json, restricted to
        entries that represent a single bundle's overall valid/invalid
        status (assertion == "validate", each with its own "path"). Entries
        with other assertion kinds (candidate_key_distinct,
        candidate_key_equals, dependency_fingerprint_equals,
        dependency_fingerprint_distinct, canonicalization) reference
        multiple bundles via "with" and don't map one path to one
        valid/invalid verdict, so they're deliberately excluded here — any
        bundle file not found in the resulting lookup is skipped by the
        test, not assumed valid."""
        manifest_path = os.path.join(TESTDATA_DIR, "manifest.json")
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        mapping = {}
        for entry in manifest["fixtures"]:
            if entry.get("assertion") != "validate":
                continue
            path = entry.get("path")
            if path is None:
                continue
            full_path = os.path.normpath(os.path.join(TESTDATA_DIR, path))
            mapping[full_path] = entry["expect_valid"]
        return mapping

    def _bundles(self):
        for path in glob.glob(os.path.join(TESTDATA_DIR, "*", "*.json")):
            if os.path.basename(path) == "manifest.json":
                continue
            if "canonicalization" in path:
                continue
            with open(path, encoding="utf-8") as fh:
                try:
                    yield path, json.load(fh)
                except ValueError:
                    continue

    def test_every_object_in_every_bundle_matches_its_schema(self):
        checked = 0
        skipped = 0
        for path, bundle in self._bundles():
            expect_valid = self.expect_valid_by_path.get(os.path.normpath(path))
            if expect_valid is not True:
                # expect_valid is False (intentionally-invalid bundle, often
                # invalid only via a native-only invariant) or None (no
                # simple valid/invalid manifest entry for this path) — skip
                # schema-conformance assertion rather than failing or
                # silently assuming valid.
                skipped += 1
                continue
            for key, schema in self.schemas.items():
                value = bundle.get(key)
                if value is None:
                    continue
                items = value if isinstance(value, list) else [value]
                for item in items:
                    try:
                        jsonschema.validate(item, schema)
                        checked += 1
                    except jsonschema.ValidationError as exc:
                        self.fail("%s: %s object failed schema conformance: %s" % (path, key, exc))
        self.assertGreater(checked, 0, "no objects were checked — fixture corpus is empty")
        self.assertGreater(skipped, 0, "expected at least one non-expect_valid:true bundle to be skipped")


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed (test-only dependency; skipped locally)")
class TestInvariantCoverageCompleteness(unittest.TestCase):
    def test_every_finding_code_is_classified(self):
        from context_graph.validation import FINDING_CODES

        with open(os.path.join(SCHEMA_DIR, "invariant-coverage.json"), encoding="utf-8") as fh:
            coverage = json.load(fh)
        classified = {entry["code"] for entry in coverage["invariants"]}
        self.assertEqual(set(FINDING_CODES), classified)

    def test_schema_only_documentation_is_empty_or_justified(self):
        with open(os.path.join(SCHEMA_DIR, "invariant-coverage.json"), encoding="utf-8") as fh:
            coverage = json.load(fh)
        schema_only = [
            e for e in coverage["invariants"]
            if e["classification"] == "schema-only-documentation"
        ]
        for entry in schema_only:
            self.assertIn(
                "justification", entry,
                "schema-only-documentation entry %r needs explicit justification" % (entry["code"],),
            )


_CODE_PREFIX_TO_KEY = {
    "E_CONFIG": "config",
    "E_NODE": "nodes",
    "E_EDGE": "edges",
    "E_CANDIDATE": "candidates",
    "E_JUDGMENT": "judgments",
}


def _object_kind_for_code(code):
    for prefix, key in _CODE_PREFIX_TO_KEY.items():
        if code.startswith(prefix + "_"):
            return key
    raise AssertionError("no object-kind mapping for finding code %r" % (code,))


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed (test-only dependency; skipped locally)")
class TestBidirectionalSchemaNativeConformance(unittest.TestCase):
    """The reverse direction TestSchemaConformance's docstring calls out as a
    follow-up (issue #200): for every finding code classified
    `schema-and-native` in invariant-coverage.json, JSON Schema validation
    must also REJECT the specific object the native validator flags for it
    -- not just fail to over-reject valid fixtures (that's the other test).

    This targets the *specific object* a finding's `index` and code prefix
    point at (e.g. `bundle["nodes"][index]` for an `E_NODE_*` code), never
    the whole bundle -- a bundle can carry both the offending object and
    other, unrelated valid objects (see fixture 54: a reserved-kind node
    coexists with an edge that's only native-invalid via a cross-object,
    non-schema-representable invariant). Blanket bundle-level rejection
    would conflate the two and defeat the point of "the *responsible*
    object genuinely fails schema validation."
    """

    @classmethod
    def setUpClass(cls):
        cls.schemas = {key: _load_schema(name) for key, name in OBJECT_SCHEMA_MAP.items()}
        with open(os.path.join(SCHEMA_DIR, "invariant-coverage.json"), encoding="utf-8") as fh:
            coverage = json.load(fh)
        cls.schema_and_native_codes = {
            entry["code"] for entry in coverage["invariants"]
            if entry["classification"] == "schema-and-native"
        }
        with open(os.path.join(TESTDATA_DIR, "manifest.json"), encoding="utf-8") as fh:
            cls.manifest = json.load(fh)

    def test_schema_rejects_the_responsible_object_for_every_schema_and_native_code(self):
        from context_graph.validation import validate_bundle

        covered = set()
        for entry in self.manifest["fixtures"]:
            if entry.get("assertion") != "validate":
                # Only "validate" entries point at a single standalone bundle
                # file meant for validate_bundle(); other assertion kinds
                # (candidate_key_equals, canonicalization, ...) point at
                # partial fixtures that aren't full bundles.
                continue
            path = entry.get("path")
            if path is None:
                continue
            full_path = os.path.normpath(os.path.join(TESTDATA_DIR, path))
            with open(full_path, encoding="utf-8") as fh:
                bundle = json.load(fh)

            for finding in validate_bundle(bundle):
                code = finding["code"]
                if code not in self.schema_and_native_codes:
                    continue
                key = _object_kind_for_code(code)
                if key == "config":
                    obj = bundle.get("config")
                else:
                    index = finding["index"]
                    items = bundle.get(key) or []
                    if index is None or index >= len(items):
                        continue
                    obj = items[index]
                if obj is None:
                    continue

                with self.assertRaises(
                    jsonschema.ValidationError,
                    msg=(
                        "%s: expected JSON Schema to reject the %s object "
                        "(index=%r) responsible for %s, but it validated"
                        % (full_path, key, finding.get("index"), code)
                    ),
                ):
                    jsonschema.validate(obj, self.schemas[key])
                covered.add(code)

        missing = self.schema_and_native_codes - covered
        self.assertFalse(
            missing,
            "no fixture exercised a JSON Schema rejection for "
            "schema-and-native code(s): %s" % (sorted(missing),),
        )


if __name__ == "__main__":
    unittest.main()
