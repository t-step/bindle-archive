"""Unit tests for structural_graph.graphset."""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import graphset

BINDING_A = "repository-binding:" + "0" * 31 + "1"
BINDING_B = "repository-binding:" + "0" * 31 + "2"


def doc_for(binding_id, capability="contains", status="observed"):
    return {
        "schema_version": 1,
        "binding_id": binding_id,
        "source_commit": "a" * 40,
        "provider": {"name": "reference-json", "version": "1.0.0"},
        "capabilities": [capability],
        "root": "",
        "coverage": [
            {"path_prefix": "", "capability": capability, "status": status}
        ],
        "files": [{"path": "src/app.py"}],
        "symbols": [
            {"id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py"}
        ],
        "edges": [],
    }


def config():
    return {
        "schema_version": 1,
        "repositories": [
            {"alias": "a", "binding_id": BINDING_A, "provider": "github"},
            {"alias": "b", "binding_id": BINDING_B, "provider": "github"},
        ],
    }


class TestSetLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, doc):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc))
        return path

    def test_both_bindings_load(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(result["bindings"][BINDING_A]["status"], "loaded")
        self.assertEqual(result["bindings"][BINDING_B]["status"], "loaded")

    def test_same_path_in_two_bindings_stays_distinct(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertIn(BINDING_A + "::src/app.py", result["facts"]["files"])
        self.assertIn(BINDING_B + "::src/app.py", result["facts"]["files"])
        self.assertEqual(len(result["facts"]["files"]), 2)

    def test_same_symbol_id_in_two_bindings_stays_distinct(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(len(result["facts"]["symbols"]), 2)

    def test_one_binding_unavailable_does_not_invalidate_the_other(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: os.path.join(self.tmp, "missing.json"),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(result["bindings"][BINDING_A]["status"], "loaded")
        self.assertEqual(result["bindings"][BINDING_B]["status"], "unavailable")
        self.assertEqual(len(result["facts"]["files"]), 1)

    def test_configured_binding_with_no_document_is_unavailable(self):
        paths = {BINDING_A: self._write("a.json", doc_for(BINDING_A))}
        result = graphset.load_set(config(), paths)
        self.assertEqual(result["bindings"][BINDING_B]["status"], "unavailable")

    def test_results_are_deterministic(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        first = graphset.load_set(config(), paths)
        second = graphset.load_set(config(), paths)
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )


class TestAggregateCoverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, doc):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc))
        return path

    def test_all_observed_aggregates_to_observed(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "contains", "src/app.py"), "observed"
        )

    def test_one_unsupported_degrades_to_partial_never_zero(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write(
                "b.json", doc_for(BINDING_B, status="unsupported")
            ),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "contains", "src/app.py"), "partial"
        )

    def test_one_partial_parse_failure_degrades_to_partial(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write(
                "b.json", doc_for(BINDING_B, status="partial_parse_failure")
            ),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "contains", "src/app.py"), "partial"
        )

    def test_unavailable_binding_degrades_to_partial(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: os.path.join(self.tmp, "missing.json"),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "contains", "src/app.py"), "partial"
        )

    def test_capability_no_binding_declares_is_unknown(self):
        paths = {BINDING_A: self._write("a.json", doc_for(BINDING_A))}
        result = graphset.load_set(config(), paths)
        self.assertEqual(
            graphset.aggregate_coverage(result, "calls", "src/app.py"), "unknown"
        )


if __name__ == "__main__":
    unittest.main()
