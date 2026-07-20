"""Unit tests for architecture.state — the notes-home state layout, the
note-path grammar, and the project_id hard abort (#228)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import canonical
from architecture import state
from context_graph import config as cg_config
from context_graph import lock as cg_lock

PROJECT_ID = "project:" + "a" * 32
OTHER_PROJECT_ID = "project:" + "c" * 32
NOTES_HOME = os.path.join("/nowhere", "vault")
SLUG = "bindle"


class TestStateLayout(unittest.TestCase):
    """#228 frozen: state is rooted at the NOTES HOME and namespaced by
    project_slug, never a bare `.bindle/`, which would share one identity
    authority across projects."""

    def test_architecture_dir_is_a_sibling_of_the_context_dir(self):
        arch = state.architecture_dir(NOTES_HOME, SLUG)
        context = cg_config.context_dir(NOTES_HOME, SLUG)
        self.assertEqual(os.path.dirname(arch), os.path.dirname(context))
        self.assertNotEqual(arch, context)

    def test_architecture_dir_is_under_the_project_dir(self):
        project = cg_config.project_dir(NOTES_HOME, SLUG)
        self.assertEqual(
            state.architecture_dir(NOTES_HOME, SLUG),
            os.path.join(project, ".bindle", "architecture"),
        )

    def test_every_state_file_lives_in_the_architecture_dir(self):
        arch = state.architecture_dir(NOTES_HOME, SLUG)
        paths = {
            "config": state.config_path(NOTES_HOME, SLUG),
            "judgments": state.judgments_path(NOTES_HOME, SLUG),
            "index": state.index_path(NOTES_HOME, SLUG),
            "apply_state": state.apply_state_path(NOTES_HOME, SLUG),
            "observations": state.observations_path(NOTES_HOME, SLUG),
        }
        for label, path in paths.items():
            with self.subTest(file=label):
                self.assertEqual(os.path.dirname(path), arch)

    def test_state_filenames_are_the_frozen_names(self):
        self.assertEqual(
            os.path.basename(state.config_path(NOTES_HOME, SLUG)), "config.json")
        self.assertEqual(
            os.path.basename(state.judgments_path(NOTES_HOME, SLUG)),
            "judgments.jsonl")
        self.assertEqual(
            os.path.basename(state.index_path(NOTES_HOME, SLUG)), "index.json")
        self.assertEqual(
            os.path.basename(state.apply_state_path(NOTES_HOME, SLUG)),
            "apply-state.json")

    def test_a_different_project_slug_gets_a_different_authority(self):
        self.assertNotEqual(
            state.judgments_path(NOTES_HOME, "bindle"),
            state.judgments_path(NOTES_HOME, "other-project"),
        )

    def test_the_notes_home_root_is_never_assumed(self):
        # The notes home is user-relocatable (possibly Obsidian-synced), so
        # every path helper takes it as a parameter and none of them reads
        # an environment variable or a hard-coded ~/.bindle.
        relocated = state.config_path(os.path.join("/elsewhere", "notes"), SLUG)
        self.assertTrue(relocated.startswith(os.path.join("/elsewhere", "notes")))


class TestNotePathGrammar(unittest.TestCase):
    """#228 frozen: the note path derives from the creation-event slug and is
    NEVER recomputed from the current name. F1-F4 populate this pre-frozen
    tree and may not invent sibling roots."""

    def test_codebase_map_is_a_single_note_at_the_root(self):
        self.assertEqual(
            state.format_note_path("arch_codebase_map", None), "Codebase Map.md")

    def test_component_notes_live_under_components(self):
        self.assertEqual(
            state.format_note_path("arch_component", "auth-service"),
            "Components/auth-service.md",
        )

    def test_round_trip_recovers_projection_type_and_slug(self):
        parsed = state.parse_note_path("Components/auth-service.md")
        self.assertEqual(parsed["projection_type"], "arch_component")
        self.assertEqual(parsed["slug"], "auth-service")

    def test_every_frozen_subtree_parses(self):
        for subtree in state.NOTE_SUBTREES:
            with self.subTest(subtree=subtree):
                parsed = state.parse_note_path("%s/thing.md" % (subtree,))
                self.assertEqual(parsed["slug"], "thing")

    def test_a_sibling_root_is_rejected(self):
        # F1-F4 may not invent sibling roots.
        with self.assertRaises(state.MalformedNotePathError):
            state.parse_note_path("Invented Root/thing.md")

    MALFORMED = (
        ("empty string", ""),
        ("not a string", None),
        ("absolute path", "/Components/thing.md"),
        ("parent traversal", "Components/../../escape.md"),
        ("bare parent traversal", "../thing.md"),
        ("backslash separator", "Components\\thing.md"),
        ("no extension", "Components/thing"),
        ("wrong extension", "Components/thing.txt"),
        ("nested below the subtree", "Components/sub/thing.md"),
        ("uppercase slug", "Components/Thing.md"),
        ("underscore slug", "Components/a_thing.md"),
        ("space in slug", "Components/a thing.md"),
        ("leading hyphen slug", "Components/-thing.md"),
        ("trailing hyphen slug", "Components/thing-.md"),
        ("empty slug", "Components/.md"),
        ("trailing newline", "Components/thing.md\n"),
        ("unknown root file", "Some Other.md"),
    )

    def test_malformed_note_paths_are_rejected(self):
        for label, value in self.MALFORMED:
            with self.subTest(case=label):
                with self.assertRaises(state.MalformedNotePathError):
                    state.parse_note_path(value)

    def test_format_rejects_an_unknown_projection_type(self):
        with self.assertRaises(ValueError):
            state.format_note_path("arch_not_a_type", "thing")

    def test_format_rejects_a_malformed_slug(self):
        for bad in ("Thing", "a thing", "a_thing", "-thing", "thing-", ""):
            with self.subTest(slug=bad):
                with self.assertRaises(ValueError):
                    state.format_note_path("arch_component", bad)

    def test_the_path_is_not_derived_from_the_identity_hex(self):
        # Path-derived-from-arch_id was explicitly rejected: the path comes
        # from the creation-event slug so a human can read the vault.
        self.assertNotIn(
            "a" * 32, state.format_note_path("arch_component", "auth-service"))


class TestProjectIdHardAbort(unittest.TestCase):
    """#228 frozen: config.json carries project_id and a mismatch is a HARD
    ABORT. Copying a notes-home directory to seed a second project would
    otherwise leave judgments full of another project's identities."""

    def test_matching_project_id_returns_quietly(self):
        self.assertIsNone(
            state.require_project_id({"project_id": PROJECT_ID}, PROJECT_ID,
                                     "config.json"))

    def test_mismatched_project_id_raises(self):
        with self.assertRaises(state.ProjectIdMismatchError):
            state.require_project_id({"project_id": OTHER_PROJECT_ID},
                                     PROJECT_ID, "config.json")

    def test_missing_project_id_raises(self):
        with self.assertRaises(state.ProjectIdMismatchError):
            state.require_project_id({}, PROJECT_ID, "config.json")

    def test_the_abort_is_an_exception_not_a_return_value(self):
        # Unlike apply.py's soft {"ok": False, "findings": [...]}, this one
        # raises: a caller must not be able to ignore a return value and
        # keep going with a foreign project's identity authority.
        self.assertTrue(issubclass(state.ProjectIdMismatchError, Exception))
        self.assertTrue(issubclass(state.ProjectIdMismatchError,
                                   state.ArchStateError))

    def test_the_error_carries_structured_findings(self):
        with self.assertRaises(state.ProjectIdMismatchError) as caught:
            state.require_project_id({"project_id": OTHER_PROJECT_ID},
                                     PROJECT_ID, "config.json")
        findings = caught.exception.findings
        self.assertEqual([f["code"] for f in findings],
                         ["E_ARCH_PROJECT_ID_MISMATCH"])
        self.assertIn(OTHER_PROJECT_ID, findings[0]["message"])
        self.assertIn(PROJECT_ID, findings[0]["message"])
        self.assertEqual(caught.exception.source, "config.json")

    def test_findings_use_the_shared_four_key_shape(self):
        with self.assertRaises(state.ProjectIdMismatchError) as caught:
            state.require_project_id({}, PROJECT_ID, "index.json")
        for finding in caught.exception.findings:
            self.assertEqual(
                set(finding), {"code", "message", "index", "field"})


def _valid_config():
    return {
        "schema_version": 1,
        "projection_schema_version": 1,
        "project_id": PROJECT_ID,
        "project_slug": SLUG,
        "bindings": [{"binding_id": "repository-binding:" + "d" * 32,
                      "alias": "bindle"}],
        "caps": {"max_nodes": 40, "over_cap_behavior": "report"},
        "thresholds": {"high": 0.9, "low": 0.4},
        "exclusions": ["vendor/**"],
        "diff_size_confirmation_limit": 20,
    }


class TestConfigValidation(unittest.TestCase):
    def test_a_valid_config_has_no_findings(self):
        self.assertEqual(state.validate_config(_valid_config()), [])

    def test_missing_required_field_is_a_finding(self):
        for field in ("schema_version", "project_id", "project_slug",
                      "bindings", "caps", "thresholds",
                      "diff_size_confirmation_limit"):
            with self.subTest(field=field):
                doc = _valid_config()
                del doc[field]
                codes = [f["code"] for f in state.validate_config(doc)]
                self.assertIn("E_ARCH_CONFIG_MISSING_FIELD", codes)

    def test_unknown_top_level_field_is_a_finding(self):
        doc = _valid_config()
        doc["surprise"] = True
        codes = [f["code"] for f in state.validate_config(doc)]
        self.assertIn("E_ARCH_CONFIG_UNKNOWN_FIELD", codes)

    def test_malformed_project_id_is_a_finding(self):
        doc = _valid_config()
        doc["project_id"] = "a" * 32
        codes = [f["code"] for f in state.validate_config(doc)]
        self.assertIn("E_ARCH_CONFIG_MALFORMED_PROJECT_ID", codes)

    def test_silent_over_cap_behavior_is_rejected(self):
        # Silent enforcement and silent non-enforcement are BOTH forbidden:
        # a lowered cap binds new creation only and existing over-cap nodes
        # must be reported, never retro-staled.
        for bad in ("enforce", "ignore", "delete"):
            with self.subTest(behavior=bad):
                doc = _valid_config()
                doc["caps"]["over_cap_behavior"] = bad
                codes = [f["code"] for f in state.validate_config(doc)]
                self.assertIn("E_ARCH_CONFIG_BAD_OVER_CAP_BEHAVIOR", codes)

    def test_duplicate_binding_id_is_a_finding(self):
        doc = _valid_config()
        doc["bindings"].append(dict(doc["bindings"][0], alias="dupe"))
        codes = [f["code"] for f in state.validate_config(doc)]
        self.assertIn("E_ARCH_CONFIG_DUPLICATE_BINDING", codes)

    def test_thresholds_must_be_ordered_and_in_range(self):
        for high, low in ((0.4, 0.9), (1.5, 0.4), (0.9, -0.1)):
            with self.subTest(high=high, low=low):
                doc = _valid_config()
                doc["thresholds"] = {"high": high, "low": low}
                codes = [f["code"] for f in state.validate_config(doc)]
                self.assertIn("E_ARCH_CONFIG_BAD_THRESHOLDS", codes)

    def test_wrong_schema_version_is_a_finding(self):
        doc = _valid_config()
        doc["schema_version"] = 2
        codes = [f["code"] for f in state.validate_config(doc)]
        self.assertIn("E_ARCH_CONFIG_BAD_SCHEMA_VERSION", codes)


def _valid_node():
    return {
        "arch_id": "arch-node:%s:%s" % (PROJECT_ID, "b" * 32),
        "project_id": PROJECT_ID,
        "note_path": "Components/auth-service.md",
        "binding_ids": ["repository-binding:" + "d" * 32],
        "projection_type": "arch_component",
        "projection_schema_version": 1,
        "provider_name": "reference",
        "provider_version": "1.0.0",
        "source_commits": [{"binding_id": "repository-binding:" + "d" * 32,
                            "commit": "e" * 40}],
        "source_paths": ["bin/architecture/state.py"],
        "source_symbols": [],
        "per_binding_status": [{"binding_id": "repository-binding:" + "d" * 32,
                                "status": "available"}],
        "per_binding_coverage": [{"binding_id": "repository-binding:" + "d" * 32,
                                  "fact_class": "symbols",
                                  "coverage": "observed"}],
        "confidence": "high",
        "projection_status": "current",
        "prior_names": [],
        "merged_from": [],
        "split_into": [],
        "superseded_by": [],
        "last_projected_at": "2026-07-20T00:00:00Z",
    }


def _valid_index():
    return {
        "schema_version": 1,
        "projection_schema_version": 1,
        "project_id": PROJECT_ID,
        "nodes": [_valid_node()],
        "references": [{"arch_id": _valid_node()["arch_id"],
                        "context_id": "context-node:bindle:" + "f" * 32}],
    }


class TestIndexValidation(unittest.TestCase):
    def test_a_valid_index_has_no_findings(self):
        self.assertEqual(state.validate_index(_valid_index()), [])

    def test_node_arch_id_must_be_well_formed(self):
        doc = _valid_index()
        doc["nodes"][0]["arch_id"] = "context-node:bindle:" + "b" * 32
        codes = [f["code"] for f in state.validate_index(doc)]
        self.assertIn("E_ARCH_INDEX_MALFORMED_ARCH_ID", codes)

    def test_node_arch_id_must_embed_the_index_project_id(self):
        # A copied notes home is exactly the scenario the hard abort exists
        # for; the index schema catches it structurally too.
        doc = _valid_index()
        doc["nodes"][0]["arch_id"] = "arch-node:%s:%s" % (
            OTHER_PROJECT_ID, "b" * 32)
        codes = [f["code"] for f in state.validate_index(doc)]
        self.assertIn("E_ARCH_INDEX_FOREIGN_PROJECT_ID", codes)

    def test_frozen_enums_are_closed(self):
        cases = (
            ("projection_type", "arch_invented", "E_ARCH_INDEX_BAD_ENUM"),
            ("confidence", "very-high", "E_ARCH_INDEX_BAD_ENUM"),
            ("projection_status", "deleted", "E_ARCH_INDEX_BAD_ENUM"),
        )
        for field, bad, code in cases:
            with self.subTest(field=field):
                doc = _valid_index()
                doc["nodes"][0][field] = bad
                self.assertIn(code, [f["code"] for f in state.validate_index(doc)])

    def test_per_binding_status_and_coverage_enums_are_closed(self):
        doc = _valid_index()
        doc["nodes"][0]["per_binding_status"][0]["status"] = "gone"
        self.assertIn("E_ARCH_INDEX_BAD_ENUM",
                      [f["code"] for f in state.validate_index(doc)])
        doc = _valid_index()
        doc["nodes"][0]["per_binding_coverage"][0]["coverage"] = "zero"
        self.assertIn("E_ARCH_INDEX_BAD_ENUM",
                      [f["code"] for f in state.validate_index(doc)])

    def test_a_partial_parse_failure_is_representable(self):
        # A provider that advertises a fact class but fails to parse a
        # subtree must read as PARTIAL, never as an observed zero.
        doc = _valid_index()
        doc["nodes"][0]["per_binding_coverage"][0]["coverage"] = (
            "partial_parse_failure")
        self.assertEqual(state.validate_index(doc), [])

    def test_superseded_requires_a_successor(self):
        doc = _valid_index()
        doc["nodes"][0]["projection_status"] = "superseded"
        codes = [f["code"] for f in state.validate_index(doc)]
        self.assertIn("E_ARCH_INDEX_SUPERSEDED_WITHOUT_SUCCESSOR", codes)

    def test_note_path_must_satisfy_the_grammar(self):
        doc = _valid_index()
        doc["nodes"][0]["note_path"] = "../escape.md"
        codes = [f["code"] for f in state.validate_index(doc)]
        self.assertIn("E_ARCH_INDEX_MALFORMED_NOTE_PATH", codes)

    def test_duplicate_arch_id_is_a_finding(self):
        doc = _valid_index()
        doc["nodes"].append(_valid_node())
        codes = [f["code"] for f in state.validate_index(doc)]
        self.assertIn("E_ARCH_INDEX_DUPLICATE_NODE", codes)

    def test_a_reference_is_not_a_context_graph_edge(self):
        # References point AT context identities; they are never edges in
        # the #140 graph and carry no relationship vocabulary.
        doc = _valid_index()
        doc["references"][0]["relationship"] = "supports"
        codes = [f["code"] for f in state.validate_index(doc)]
        self.assertIn("E_ARCH_INDEX_UNKNOWN_FIELD", codes)

    def test_a_reference_target_must_be_a_context_identity(self):
        doc = _valid_index()
        doc["references"][0]["context_id"] = _valid_node()["arch_id"]
        codes = [f["code"] for f in state.validate_index(doc)]
        self.assertIn("E_ARCH_INDEX_MALFORMED_REFERENCE", codes)


def _valid_apply_state():
    return {
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "status": "in_progress",
        "started_at": "2026-07-20T00:00:00Z",
        "writes": [
            {"order": 0, "path": "Components/auth-service.md",
             "before_hash": None, "after_hash": "sha256:" + "a" * 64,
             "state": "pending"},
        ],
    }


class TestApplyStateValidation(unittest.TestCase):
    def test_a_valid_apply_state_has_no_findings(self):
        self.assertEqual(state.validate_apply_state(_valid_apply_state()), [])

    def test_a_new_file_has_a_null_before_hash(self):
        doc = _valid_apply_state()
        doc["writes"][0]["before_hash"] = None
        self.assertEqual(state.validate_apply_state(doc), [])

    def test_write_order_must_be_dense_and_ascending(self):
        # Deterministic write ordering is what makes resume reconcilable;
        # a gap or a repeat makes "advance after each write" ambiguous.
        doc = _valid_apply_state()
        doc["writes"].append(dict(doc["writes"][0], order=2,
                                  path="Components/other.md"))
        codes = [f["code"] for f in state.validate_apply_state(doc)]
        self.assertIn("E_ARCH_APPLY_STATE_BAD_ORDER", codes)

    def test_duplicate_path_is_a_finding(self):
        doc = _valid_apply_state()
        doc["writes"].append(dict(doc["writes"][0], order=1))
        codes = [f["code"] for f in state.validate_apply_state(doc)]
        self.assertIn("E_ARCH_APPLY_STATE_DUPLICATE_PATH", codes)

    def test_hashes_must_be_prefixed_digests(self):
        doc = _valid_apply_state()
        doc["writes"][0]["after_hash"] = "a" * 64
        codes = [f["code"] for f in state.validate_apply_state(doc)]
        self.assertIn("E_ARCH_APPLY_STATE_MALFORMED_HASH", codes)

    def test_an_empty_write_list_is_a_finding(self):
        # A semantic no-op writes zero bytes and creates NO apply-state at
        # all, so an apply-state with no writes can only be corruption.
        doc = _valid_apply_state()
        doc["writes"] = []
        codes = [f["code"] for f in state.validate_apply_state(doc)]
        self.assertIn("E_ARCH_APPLY_STATE_EMPTY", codes)

    def test_status_and_write_state_enums_are_closed(self):
        doc = _valid_apply_state()
        doc["status"] = "finished"
        self.assertIn("E_ARCH_APPLY_STATE_BAD_ENUM",
                      [f["code"] for f in state.validate_apply_state(doc)])
        doc = _valid_apply_state()
        doc["writes"][0]["state"] = "maybe"
        self.assertIn("E_ARCH_APPLY_STATE_BAD_ENUM",
                      [f["code"] for f in state.validate_apply_state(doc)])

    def test_apply_state_carries_no_semantic_field(self):
        # apply-state.json is recovery metadata ONLY. Losing it may never
        # change what the projection means, so an arch_id or a decision has
        # no place in it -- recovery must never become a semantic authority.
        doc = _valid_apply_state()
        doc["writes"][0]["arch_id"] = _valid_node()["arch_id"]
        codes = [f["code"] for f in state.validate_apply_state(doc)]
        self.assertIn("E_ARCH_APPLY_STATE_UNKNOWN_FIELD", codes)


def _judgment_body(**overrides):
    body = {
        "schema_version": 1,
        "kind": "identity_allocation",
        "arch_id": _valid_node()["arch_id"],
        "project_id": PROJECT_ID,
        "decided_at": "2026-07-20T00:00:00Z",
        "payload": {"note_path": "Components/auth-service.md"},
    }
    body.update(overrides)
    return body


def _valid_judgment(**overrides):
    return canonical.stamp(_judgment_body(**overrides))


class TestJudgmentValidation(unittest.TestCase):
    def test_a_valid_judgment_has_no_findings(self):
        self.assertEqual(state.validate_judgment(_valid_judgment()), [])

    def test_the_kind_enum_is_closed(self):
        record = dict(_valid_judgment(), kind="vibes")
        codes = [f["code"] for f in state.validate_judgment(record)]
        self.assertIn("E_ARCH_JUDGMENT_BAD_KIND", codes)

    def test_every_frozen_kind_is_accepted(self):
        for kind in state.JUDGMENT_KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(state.validate_judgment(_valid_judgment(kind=kind)),
                                 [])

    def test_identity_allocation_must_name_its_arch_id(self):
        body = _judgment_body()
        del body["arch_id"]
        codes = [f["code"]
                 for f in state.validate_judgment(canonical.stamp(body))]
        self.assertIn("E_ARCH_JUDGMENT_MISSING_ARCH_ID", codes)

    def test_a_tampered_record_fails_its_checksum(self):
        record = dict(_valid_judgment(), decided_at="2026-07-21T00:00:00Z")
        codes = [f["code"] for f in state.validate_judgment(record)]
        self.assertIn("E_ARCH_JUDGMENT_CHECKSUM_MISMATCH", codes)

    def test_a_foreign_arch_id_is_a_finding(self):
        record = _valid_judgment(
            arch_id="arch-node:%s:%s" % (OTHER_PROJECT_ID, "b" * 32))
        codes = [f["code"] for f in state.validate_judgment(record)]
        self.assertIn("E_ARCH_JUDGMENT_FOREIGN_PROJECT_ID", codes)

    def test_the_envelope_is_required(self):
        for field in ("record_id", "checksum"):
            with self.subTest(field=field):
                record = _valid_judgment()
                del record[field]
                codes = [f["code"] for f in state.validate_judgment(record)]
                self.assertIn("E_ARCH_JUDGMENT_MISSING_FIELD", codes)

    def test_an_observation_field_has_no_place_in_a_decision(self):
        # DECISIONS ONLY: an observed provider fact must never be written
        # here merely because a projection ran.
        record = dict(_valid_judgment(), source_commit="e" * 40)
        codes = [f["code"] for f in state.validate_judgment(record)]
        self.assertIn("E_ARCH_JUDGMENT_UNKNOWN_FIELD", codes)


class TestStateWritesNothing(unittest.TestCase):
    """Slice 2 is path + schema + validate only: no module in it may write,
    append to, or create a file at runtime."""

    def test_no_filesystem_mutation_helpers_are_imported(self):
        import architecture.state as module

        source_path = module.__file__
        with open(source_path, "r") as handle:
            source = handle.read()
        for forbidden in ("open(", "makedirs", "write_atomic",
                          "append_line_atomic", "os.replace"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)


class TestCrossSurfaceLockCoversArchitecture(unittest.TestCase):
    """#228 PT28, from the architecture side: the one project lock sits
    above this surface's directory, so a context apply and an architecture
    apply cannot interleave. Slice 4 ships the contract; acquisition in the
    architecture projection loop is child D's."""

    def test_the_project_lock_sits_above_the_architecture_dir(self):
        adir = state.architecture_dir(NOTES_HOME, SLUG)
        lpath = cg_lock.lock_path(cg_config.project_dir(NOTES_HOME, SLUG))
        self.assertTrue(
            adir.startswith(os.path.dirname(lpath) + os.sep),
            "%r must live under the lock's directory %r"
            % (adir, os.path.dirname(lpath)))

    def test_the_lock_is_not_inside_either_surface(self):
        lpath = cg_lock.lock_path(cg_config.project_dir(NOTES_HOME, SLUG))
        self.assertFalse(
            lpath.startswith(state.architecture_dir(NOTES_HOME, SLUG) + os.sep))
        self.assertFalse(
            lpath.startswith(cg_config.context_dir(NOTES_HOME, SLUG) + os.sep))

    def test_architecture_operations_are_acquirable(self):
        for operation in ("arch_init", "arch_config",
                          "arch_confirm", "arch_apply"):
            with self.subTest(operation=operation):
                self.assertIn(operation, cg_lock.VALID_OPERATIONS)


if __name__ == "__main__":
    unittest.main()
