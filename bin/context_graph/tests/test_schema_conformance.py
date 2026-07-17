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
    engine (design section 11)."""

    @classmethod
    def setUpClass(cls):
        cls.schemas = {key: _load_schema(name) for key, name in OBJECT_SCHEMA_MAP.items()}

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
        for path, bundle in self._bundles():
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


if __name__ == "__main__":
    unittest.main()
