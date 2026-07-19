"""Unit tests for structural_graph.validation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import validation


def minimal_document():
    """A structurally valid document, used as the base for mutation."""
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
            {"id": "sym-1", "name": "app", "kind": "module", "path": "src/app.py"}
        ],
        "edges": [],
    }


def codes(findings):
    return [f["code"] for f in findings]


class TestValidDocument(unittest.TestCase):
    def test_minimal_document_has_no_findings(self):
        self.assertEqual(validation.validate_document(minimal_document()), [])


class TestFindingShape(unittest.TestCase):
    def test_finding_has_exactly_the_house_keys(self):
        doc = minimal_document()
        del doc["source_commit"]
        found = validation.validate_document(doc)[0]
        self.assertEqual(
            sorted(found.keys()), ["code", "field", "index", "message"]
        )

    def test_no_finding_carries_a_value_key(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "wildly-invalid"
        for found in validation.validate_document(doc):
            self.assertNotIn("value", found)

    def test_every_emitted_code_is_registered(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "nope"
        doc["edges"] = [{"type": "nope", "source": "sym-1", "target": "sym-2"}]
        for found in validation.validate_document(doc):
            self.assertIn(found["code"], validation.FINDING_CODES)


class TestShapeFindings(unittest.TestCase):
    def test_missing_schema_version(self):
        doc = minimal_document()
        del doc["schema_version"]
        self.assertIn("E_SG_MISSING_SCHEMA_VERSION", codes(validation.validate_document(doc)))

    def test_unsupported_schema_version(self):
        doc = minimal_document()
        doc["schema_version"] = 99
        self.assertIn(
            "E_SG_UNSUPPORTED_SCHEMA_VERSION", codes(validation.validate_document(doc))
        )

    def test_missing_required_field(self):
        doc = minimal_document()
        del doc["binding_id"]
        self.assertIn("E_SG_MISSING_FIELD", codes(validation.validate_document(doc)))

    def test_unknown_top_level_field_rejected(self):
        doc = minimal_document()
        doc["surprise"] = True
        self.assertIn("E_SG_UNKNOWN_FIELD", codes(validation.validate_document(doc)))

    def test_malformed_commit(self):
        doc = minimal_document()
        doc["source_commit"] = "not-a-sha"
        self.assertIn("E_SG_MALFORMED_COMMIT", codes(validation.validate_document(doc)))


class TestVocabularyFindings(unittest.TestCase):
    def test_unknown_symbol_kind(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "gadget"
        self.assertIn(
            "E_SG_UNKNOWN_SYMBOL_KIND", codes(validation.validate_document(doc))
        )

    def test_unknown_edge_type(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "teleports", "source": "sym-1", "target": "sym-1"}]
        self.assertIn("E_SG_UNKNOWN_EDGE_TYPE", codes(validation.validate_document(doc)))

    def test_unknown_capability(self):
        doc = minimal_document()
        doc["capabilities"] = ["telepathy"]
        self.assertIn("E_SG_UNKNOWN_CAPABILITY", codes(validation.validate_document(doc)))

    def test_unknown_coverage_status(self):
        doc = minimal_document()
        doc["coverage"][0]["status"] = "vibes"
        self.assertIn(
            "E_SG_UNKNOWN_COVERAGE_STATUS", codes(validation.validate_document(doc))
        )


class TestReferentialFindings(unittest.TestCase):
    def test_duplicate_symbol_id(self):
        doc = minimal_document()
        doc["symbols"].append(
            {"id": "sym-1", "name": "dup", "kind": "function", "path": "src/app.py"}
        )
        self.assertIn(
            "E_SG_DUPLICATE_SYMBOL_ID", codes(validation.validate_document(doc))
        )

    def test_dangling_edge_endpoint(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "calls", "source": "sym-1", "target": "ghost"}]
        self.assertIn(
            "E_SG_DANGLING_EDGE_ENDPOINT", codes(validation.validate_document(doc))
        )

    def test_coverage_declares_unadvertised_capability(self):
        doc = minimal_document()
        doc["coverage"].append(
            {"path_prefix": "", "capability": "calls", "status": "observed"}
        )
        self.assertIn(
            "E_SG_COVERAGE_UNDECLARED_CAPABILITY",
            codes(validation.validate_document(doc)),
        )


class TestMalformedFieldShape(unittest.TestCase):
    def test_non_list_symbols_reports_and_does_not_raise(self):
        doc = minimal_document()
        doc["symbols"] = "not-a-list"
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_list_edges_reports_and_does_not_raise(self):
        doc = minimal_document()
        doc["edges"] = "not-a-list"
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_list_coverage_reports_and_does_not_raise(self):
        doc = minimal_document()
        doc["coverage"] = "oops"
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_list_files_reports_and_does_not_raise(self):
        doc = minimal_document()
        doc["files"] = "oops"
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_list_capabilities_reports_and_does_not_raise(self):
        doc = minimal_document()
        doc["capabilities"] = "oops"
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_dict_symbol_elements_reported_individually(self):
        doc = minimal_document()
        doc["symbols"] = [1, 2, 3]
        found = validation.validate_document(doc)
        shape_findings = [
            f for f in found if f["code"] == "E_SG_MALFORMED_FIELD_SHAPE"
        ]
        self.assertEqual([f["index"] for f in shape_findings], [0, 1, 2])

    def test_non_dict_edge_elements_reported(self):
        doc = minimal_document()
        doc["edges"] = ["not-a-dict"]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_dict_coverage_elements_reported(self):
        doc = minimal_document()
        doc["coverage"] = [1, 2, 3]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_string_capability_element_reported(self):
        doc = minimal_document()
        doc["capabilities"] = [1, 2]
        found = validation.validate_document(doc)
        shape_findings = [
            f for f in found if f["code"] == "E_SG_MALFORMED_FIELD_SHAPE"
        ]
        self.assertEqual(len(shape_findings), 2)

    def test_malformed_field_does_not_suppress_checks_on_other_fields(self):
        doc = minimal_document()
        doc["symbols"] = "not-a-list"
        doc["edges"] = [{"type": "nope", "source": "sym-1", "target": "sym-1"}]
        found_codes = codes(validation.validate_document(doc))
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", found_codes)
        self.assertIn("E_SG_UNKNOWN_EDGE_TYPE", found_codes)

    def test_malformed_field_alongside_valid_field_both_checked(self):
        doc = minimal_document()
        doc["coverage"] = "oops"
        doc["symbols"][0]["kind"] = "gadget"
        found_codes = codes(validation.validate_document(doc))
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", found_codes)
        self.assertIn("E_SG_UNKNOWN_SYMBOL_KIND", found_codes)

    def test_validate_document_never_raises_on_non_list_symbols(self):
        doc = minimal_document()
        doc["symbols"] = "not-a-list"
        try:
            validation.validate_document(doc)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("validate_document raised %r" % (exc,))

    def test_validate_document_never_raises_on_int_list_symbols(self):
        doc = minimal_document()
        doc["symbols"] = [1, 2, 3]
        try:
            validation.validate_document(doc)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("validate_document raised %r" % (exc,))

    def test_validate_document_never_raises_on_non_list_coverage(self):
        doc = minimal_document()
        doc["coverage"] = "oops"
        try:
            validation.validate_document(doc)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("validate_document raised %r" % (exc,))


class TestMissingVsDuplicateSymbolId(unittest.TestCase):
    def test_two_symbols_missing_id_are_not_reported_as_duplicates(self):
        doc = minimal_document()
        doc["symbols"] = [
            {"name": "a", "kind": "module", "path": "src/a.py"},
            {"name": "b", "kind": "module", "path": "src/b.py"},
        ]
        doc["edges"] = []
        found = validation.validate_document(doc)
        self.assertNotIn("E_SG_DUPLICATE_SYMBOL_ID", codes(found))

    def test_genuinely_duplicated_id_is_still_reported(self):
        doc = minimal_document()
        doc["symbols"].append(
            {"id": "sym-1", "name": "dup", "kind": "function", "path": "src/app.py"}
        )
        found = validation.validate_document(doc)
        self.assertIn("E_SG_DUPLICATE_SYMBOL_ID", codes(found))

    def test_edge_referencing_missing_symbol_id_is_dangling(self):
        doc = minimal_document()
        doc["symbols"] = [{"name": "a", "kind": "module", "path": "src/a.py"}]
        doc["edges"] = [{"type": "calls", "source": None, "target": None}]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_DANGLING_EDGE_ENDPOINT", codes(found))


class TestDeterminism(unittest.TestCase):
    def test_findings_are_stable_across_runs(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "gadget"
        doc["capabilities"] = ["telepathy"]
        first = validation.validate_document(doc)
        second = validation.validate_document(doc)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
