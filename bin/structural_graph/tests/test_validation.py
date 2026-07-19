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


class TestUnhashableFieldValues(unittest.TestCase):
    """Non-hashable *values* inside otherwise well-shaped elements.

    _field_shape_findings only verifies elements are the right container
    type (dict, or str for capabilities) -- it never inspects a dict's
    values. id/source/target/capability all end up tested with `in` against
    a validator-built set(), and set membership hashes the operand: a list
    or dict there raises TypeError before this module gets a chance to
    report it as a finding. This must never happen -- validators return
    finding lists and never raise.
    """

    def test_non_hashable_coverage_capability_list_does_not_raise(self):
        doc = minimal_document()
        doc["coverage"][0]["capability"] = ["contains"]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_hashable_coverage_capability_dict_does_not_raise(self):
        doc = minimal_document()
        doc["coverage"][0]["capability"] = {"contains": True}
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_hashable_symbol_id_list_does_not_raise(self):
        doc = minimal_document()
        doc["symbols"][0]["id"] = ["not", "hashable"]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_hashable_symbol_id_dict_does_not_raise(self):
        doc = minimal_document()
        doc["symbols"][0]["id"] = {"not": "hashable"}
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_hashable_edge_source_list_does_not_raise(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "calls", "source": ["x"], "target": "sym-1"}]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_hashable_edge_source_dict_does_not_raise(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "calls", "source": {"x": 1}, "target": "sym-1"}]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_hashable_edge_target_list_does_not_raise(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "calls", "source": "sym-1", "target": ["x"]}]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_hashable_edge_target_dict_does_not_raise(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "calls", "source": "sym-1", "target": {"x": 1}}]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_string_hashable_symbol_id_int_reported(self):
        # The guard is about type, not just hashability: an int id is
        # perfectly hashable but is still not the string type the schema
        # requires, and must be reported rather than silently accepted.
        doc = minimal_document()
        doc["symbols"][0]["id"] = 42
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_string_hashable_edge_source_int_reported(self):
        doc = minimal_document()
        doc["edges"] = [{"type": "calls", "source": 42, "target": "sym-1"}]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_string_hashable_coverage_capability_int_reported(self):
        doc = minimal_document()
        doc["coverage"][0]["capability"] = 42
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_non_hashable_symbol_id_excluded_from_ids_so_edge_is_dangling(self):
        # Documented consequence of the fix: a symbol whose id is non-string
        # never enters `ids`, so a well-shaped edge that names the same
        # string the id would have been correctly reports as dangling
        # rather than silently resolving against an id that was dropped.
        doc = minimal_document()
        doc["symbols"][0]["id"] = ["sym-1"]
        doc["edges"] = [{"type": "calls", "source": "sym-1", "target": "sym-1"}]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_DANGLING_EDGE_ENDPOINT", codes(found))

    def test_findings_never_carry_a_value_key_for_unhashable_fields(self):
        doc = minimal_document()
        doc["symbols"][0]["id"] = ["not", "hashable"]
        doc["coverage"][0]["capability"] = {"nested": True}
        doc["edges"] = [{"type": "calls", "source": {"x": 1}, "target": ["y"]}]
        for found in validation.validate_document(doc):
            self.assertNotIn("value", found)


class TestCoveragePathPrefixShape(unittest.TestCase):
    """coverage[].path_prefix must be a string before it reaches coverage.py.

    path_prefix never feeds a set -- it feeds string concatenation and
    .startswith() in structural_graph.coverage -- so it was missed by the
    isinstance guards added for capability/id/source/target, which exist
    because *those* fields feed set membership. Same bug class (unguarded
    scalar field value type), different mechanism: TypeError from `+`
    instead of from hashing. Reported here as #227's review finding.
    """

    def test_none_path_prefix_reported(self):
        doc = minimal_document()
        doc["coverage"][0]["path_prefix"] = None
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_int_path_prefix_reported(self):
        doc = minimal_document()
        doc["coverage"][0]["path_prefix"] = 5
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_list_path_prefix_reported(self):
        doc = minimal_document()
        doc["coverage"][0]["path_prefix"] = ["src"]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_dict_path_prefix_reported(self):
        doc = minimal_document()
        doc["coverage"][0]["path_prefix"] = {"src": True}
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_path_prefix_finding_names_the_field_and_index(self):
        doc = minimal_document()
        doc["coverage"][0]["path_prefix"] = None
        found = validation.validate_document(doc)
        shape_findings = [
            f
            for f in found
            if f["code"] == "E_SG_MALFORMED_FIELD_SHAPE"
            and f["field"] == "coverage[].path_prefix"
        ]
        self.assertEqual([f["index"] for f in shape_findings], [0])

    def test_validate_document_never_raises_on_non_string_path_prefix(self):
        doc = minimal_document()
        doc["coverage"][0]["path_prefix"] = None
        try:
            validation.validate_document(doc)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("validate_document raised %r" % (exc,))

    def test_findings_never_carry_a_value_key_for_path_prefix(self):
        doc = minimal_document()
        doc["coverage"][0]["path_prefix"] = {"nested": True}
        for found in validation.validate_document(doc):
            self.assertNotIn("value", found)


class TestSymbolNameShape(unittest.TestCase):
    """symbols[].name must be a string before it reaches document.py.

    name is an anchor field (schema.ANCHOR_FIELDS): document._anchor_findings
    feeds it to redaction.redact, which silently reports "no match" on a
    non-string value instead of catching a secret. Without this guard a
    secret hidden in a list-shaped name produced no E_SG_UNNORMALIZABLE_ANCHOR
    and the document loaded instead of failing closed -- #227's review
    finding. Same bug class as coverage[].path_prefix above, different field.
    """

    def test_list_name_reported(self):
        doc = minimal_document()
        doc["symbols"][0]["name"] = ["ghp_" + "A" * 36]
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_int_name_reported(self):
        doc = minimal_document()
        doc["symbols"][0]["name"] = 42
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_dict_name_reported(self):
        doc = minimal_document()
        doc["symbols"][0]["name"] = {"nested": True}
        found = validation.validate_document(doc)
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(found))

    def test_missing_name_not_reported(self):
        # Absence, unlike a wrong type, is not a shape violation: with no
        # string present there is nothing a secret could hide inside.
        doc = minimal_document()
        del doc["symbols"][0]["name"]
        found = validation.validate_document(doc)
        self.assertEqual(found, [])

    def test_name_finding_names_the_field_and_index(self):
        doc = minimal_document()
        doc["symbols"][0]["name"] = ["not-a-string"]
        found = validation.validate_document(doc)
        shape_findings = [
            f
            for f in found
            if f["code"] == "E_SG_MALFORMED_FIELD_SHAPE"
            and f["field"] == "symbols[].name"
        ]
        self.assertEqual([f["index"] for f in shape_findings], [0])

    def test_validate_document_never_raises_on_non_string_name(self):
        doc = minimal_document()
        doc["symbols"][0]["name"] = ["not-a-string"]
        try:
            validation.validate_document(doc)
        except Exception as exc:  # pragma: no cover - documents a non-raise
            self.fail("validate_document raised %r" % (exc,))

    def test_findings_never_carry_a_value_key_for_name(self):
        doc = minimal_document()
        doc["symbols"][0]["name"] = ["ghp_" + "A" * 36]
        for found in validation.validate_document(doc):
            self.assertNotIn("value", found)


class TestRootShape(unittest.TestCase):
    """root must be a string before it reaches document.py.

    root is a top-level anchor, not a list element: document.py used to
    default a missing/falsy root to "" with `doc.get("root") or ""` before
    checking it, which folded every falsy malformed value (0, False, [],
    {}, None) into the same value the legal empty-string root produces --
    the E_SG_UNNORMALIZABLE_ANCHOR guard downstream could not tell them
    apart. #227's review finding. Same bug class as coverage[].path_prefix
    and symbols[].name above, different mechanism: truthiness coercion
    instead of an unguarded set/string operation.
    """

    def test_empty_string_root_is_legal(self):
        doc = minimal_document()
        doc["root"] = ""
        self.assertEqual(validation.validate_document(doc), [])

    def test_zero_root_reported(self):
        doc = minimal_document()
        doc["root"] = 0
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc)))

    def test_false_root_reported(self):
        doc = minimal_document()
        doc["root"] = False
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc)))

    def test_empty_list_root_reported(self):
        doc = minimal_document()
        doc["root"] = []
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc)))

    def test_empty_dict_root_reported(self):
        doc = minimal_document()
        doc["root"] = {}
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc)))

    def test_none_root_reported(self):
        doc = minimal_document()
        doc["root"] = None
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc)))

    def test_truthy_non_string_root_reported(self):
        doc = minimal_document()
        doc["root"] = ["x"]
        self.assertIn("E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc)))

    def test_missing_root_is_missing_field_not_malformed_field_shape(self):
        # Absence is already E_SG_MISSING_FIELD from the required-fields
        # check; the type check must not also fire and double-report it.
        doc = minimal_document()
        del doc["root"]
        found_codes = codes(validation.validate_document(doc))
        self.assertIn("E_SG_MISSING_FIELD", found_codes)
        self.assertNotIn("E_SG_MALFORMED_FIELD_SHAPE", found_codes)

    def test_root_finding_names_the_field(self):
        doc = minimal_document()
        doc["root"] = None
        found = validation.validate_document(doc)
        shape_findings = [
            f
            for f in found
            if f["code"] == "E_SG_MALFORMED_FIELD_SHAPE" and f["field"] == "root"
        ]
        self.assertEqual([f["index"] for f in shape_findings], [None])

    def test_findings_never_carry_a_value_key_for_root(self):
        doc = minimal_document()
        doc["root"] = {}
        for found in validation.validate_document(doc):
            self.assertNotIn("value", found)


class TestProviderShape(unittest.TestCase):
    """provider must be an object with string name/version before it reaches
    document.py.

    Task 5's review found provider was never shape-checked here -- only its
    presence was required. `doc["provider"] = "not-a-dict"` and
    `doc["provider"] = ["a", "b"]` both reached status="loaded" with the
    malformed value passed straight into facts["provider"]. The JSON Schema
    in schemas/structural-graph/v1/document.schema.json does constrain
    provider to an object with required string name/version, so a silent
    native validator here would let the schema reject documents the native
    validator accepts -- the exact divergence invariant-coverage.json exists
    to prevent. #227 Task 7 carried finding.
    """

    def test_valid_provider_has_no_finding(self):
        doc = minimal_document()
        self.assertEqual(validation.validate_document(doc), [])

    def test_string_provider_reported(self):
        doc = minimal_document()
        doc["provider"] = "not-a-dict"
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc))
        )

    def test_list_provider_reported(self):
        doc = minimal_document()
        doc["provider"] = ["a", "b"]
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc))
        )

    def test_missing_name_reported(self):
        doc = minimal_document()
        doc["provider"] = {"version": "1.0.0"}
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc))
        )

    def test_non_string_name_reported(self):
        doc = minimal_document()
        doc["provider"] = {"name": 42, "version": "1.0.0"}
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc))
        )

    def test_missing_version_reported(self):
        doc = minimal_document()
        doc["provider"] = {"name": "reference-json"}
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc))
        )

    def test_non_string_version_reported(self):
        doc = minimal_document()
        doc["provider"] = {"name": "reference-json", "version": 1}
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", codes(validation.validate_document(doc))
        )

    def test_missing_provider_is_missing_field_not_malformed_field_shape(self):
        # Absence is already E_SG_MISSING_FIELD from the required-fields
        # check; the type check must not also fire and double-report it.
        doc = minimal_document()
        del doc["provider"]
        found_codes = codes(validation.validate_document(doc))
        self.assertIn("E_SG_MISSING_FIELD", found_codes)
        self.assertNotIn("E_SG_MALFORMED_FIELD_SHAPE", found_codes)

    def test_provider_finding_names_the_field(self):
        doc = minimal_document()
        doc["provider"] = "nope"
        found = validation.validate_document(doc)
        shape_findings = [
            f
            for f in found
            if f["code"] == "E_SG_MALFORMED_FIELD_SHAPE" and f["field"] == "provider"
        ]
        self.assertEqual([f["index"] for f in shape_findings], [None])

    def test_findings_never_carry_a_value_key_for_provider(self):
        doc = minimal_document()
        doc["provider"] = ["a", "b"]
        for found in validation.validate_document(doc):
            self.assertNotIn("value", found)


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
