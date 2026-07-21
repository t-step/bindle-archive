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

    def test_each_loaded_binding_carries_its_source_commit(self):
        """Two consumers need the commit and neither can reach the
        document: the architecture planner digests it into the plan
        fingerprint, and architecture apply records it as each projected
        node's provenance. While it was dropped here, the fingerprint term
        read None for every binding and no node ever carried a commit."""
        paths = {BINDING_A: self._write("a.json", doc_for(BINDING_A))}
        result = graphset.load_set(config(), paths)
        self.assertEqual("a" * 40,
                         result["bindings"][BINDING_A]["source_commit"])

    def test_an_unavailable_binding_reports_no_source_commit(self):
        """No document, so no commit to claim. A placeholder here would be
        provenance asserted for a binding that never loaded."""
        paths = {BINDING_A: os.path.join(self.tmp, "missing.json")}
        result = graphset.load_set(config(), paths)
        self.assertIsNone(
            result["bindings"][BINDING_A].get("source_commit"))

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


def duplicate_config():
    return {
        "schema_version": 1,
        "repositories": [
            {"alias": "a", "binding_id": BINDING_A, "provider": "github"},
            {"alias": "b", "binding_id": BINDING_A, "provider": "github"},
        ],
    }


class TestDuplicateBindingIdIsCallerError(unittest.TestCase):
    """A config with two repositories sharing a binding_id is caller error.

    context_graph.validation already rejects this shape at config-validation
    time (E_CONFIG_DUPLICATE_BINDING_ID), so a validated config can never
    reach load_set with a duplicate. load_set's own precondition is that the
    config is already valid; a duplicate reaching it anyway is a malformed
    argument from the caller, not untrusted document content, so it raises
    rather than silently collapsing the second entry into the first.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, doc):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc))
        return path

    def test_duplicate_binding_id_raises_instead_of_collapsing(self):
        paths = {BINDING_A: self._write("a.json", doc_for(BINDING_A))}
        with self.assertRaises(ValueError):
            graphset.load_set(duplicate_config(), paths)

    def test_ordinary_valid_config_still_loads_unchanged(self):
        paths = {
            BINDING_A: self._write("a.json", doc_for(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(sorted(result["bindings"]), [BINDING_A, BINDING_B])
        self.assertEqual(result["bindings"][BINDING_A]["status"], "loaded")
        self.assertEqual(result["bindings"][BINDING_B]["status"], "loaded")
        self.assertEqual(len(result["facts"]["files"]), 2)
        self.assertEqual(result["findings"], [])


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


class TestIdlessSymbolDoesNotCrashTheSet(unittest.TestCase):
    """A symbol with no id must be a finding, never a KeyError.

    load_set keys its merged symbol table on item["id"]. A document whose
    symbol carried no id once reached status "loaded" with no findings, and
    that unguarded subscript then raised on it -- untrusted document
    content producing an exception, which this package rules out. The fix
    is upstream in validation, so the document never reaches the merge.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, doc):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc))
        return path

    def _idless(self, binding_id):
        doc = doc_for(binding_id)
        del doc["symbols"][0]["id"]
        return doc

    def test_set_load_reports_instead_of_raising(self):
        paths = {
            BINDING_A: self._write("a.json", self._idless(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(result["bindings"][BINDING_A]["status"], "malformed")
        self.assertIn(
            "E_SG_MISSING_FIELD",
            [f["code"] for f in result["findings"]],
        )

    def test_the_healthy_binding_survives_the_malformed_one(self):
        # FC-4: one binding failing to load leaves the others intact.
        paths = {
            BINDING_A: self._write("a.json", self._idless(BINDING_A)),
            BINDING_B: self._write("b.json", doc_for(BINDING_B)),
        }
        result = graphset.load_set(config(), paths)
        self.assertEqual(result["bindings"][BINDING_B]["status"], "loaded")
        self.assertEqual(
            sorted(result["facts"]["symbols"]), [BINDING_B + "::sym-1"]
        )

    def test_set_level_finding_is_binding_qualified(self):
        paths = {BINDING_A: self._write("a.json", self._idless(BINDING_A))}
        result = graphset.load_set(config(), paths)
        for found in result["findings"]:
            self.assertEqual(found["binding_id"], BINDING_A)
            self.assertEqual(
                sorted(found.keys()),
                ["binding_id", "code", "field", "index", "message"],
            )


if __name__ == "__main__":
    unittest.main()
