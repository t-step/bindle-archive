import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import config


class TestProjectIdentity(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()

    def test_allocate_project_id_matches_pattern(self):
        pid = config.allocate_project_id()
        self.assertRegex(pid, r"^project:[0-9a-f]{32}$")

    def test_init_project_creates_config_with_no_repositories(self):
        cfg, created = config.init_project(self.notes_home, "myproj")
        self.assertTrue(created)
        self.assertEqual(cfg["repositories"], [])
        self.assertEqual(cfg["project_slug"], "myproj")
        self.assertRegex(cfg["project_id"], r"^project:[0-9a-f]{32}$")

    def test_init_project_rerun_is_byte_identical_zero_writes(self):
        config.init_project(self.notes_home, "myproj")
        path = config.config_path(self.notes_home, "myproj")
        before = open(path, "rb").read()
        before_mtime = os.stat(path).st_mtime_ns
        cfg2, created2 = config.init_project(self.notes_home, "myproj")
        after = open(path, "rb").read()
        after_mtime = os.stat(path).st_mtime_ns
        self.assertFalse(created2)
        self.assertEqual(before, after)
        self.assertEqual(before_mtime, after_mtime)

    def test_init_project_failure_leaves_no_partial_file(self):
        path = config.config_path(self.notes_home, "myproj")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        with self.assertRaises(config.ConfigInvalidError):
            config.init_project(self.notes_home, "myproj")
        # the malformed original is untouched, not replaced or emptied
        with open(path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "{not valid json")

    def test_init_project_concurrent_threads_persist_one_id(self):
        results = []
        errors = []

        def worker():
            try:
                cfg, created = config.init_project(self.notes_home, "raceproj")
                results.append((cfg["project_id"], created))
            except Exception as e:  # noqa: BLE001 - captured for assertion
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 4)
        self.assertEqual(len({r[0] for r in results}), 1)
        self.assertEqual([r[1] for r in results].count(True), 1)

    def test_project_slug_is_independent_of_project_id(self):
        cfg, _ = config.init_project(self.notes_home, "old-slug")
        original_id = cfg["project_id"]
        # simulate a slug rename: same notes_home, config lives at the
        # project-slug directory, so re-reading under the OLD slug still
        # returns the same id (identity is not derived from the slug path).
        reread = config.load_config(config.config_path(self.notes_home, "old-slug"))
        self.assertEqual(reread["project_id"], original_id)

    def test_init_project_at_new_notes_home_path_preserves_existing_config(self):
        cfg, _ = config.init_project(self.notes_home, "movable")
        original_id = cfg["project_id"]
        # "notes-directory movement" = re-resolving the same tree at a new
        # path (e.g. after a mv); config.py never depends on notes_home's
        # own identity, only on what's on disk at the resolved path.
        moved = tempfile.mkdtemp()
        os.rename(self.notes_home, os.path.join(moved, "moved-tree"))
        moved_home = os.path.join(moved, "moved-tree")
        reread, created = config.init_project(moved_home, "movable")
        self.assertFalse(created)
        self.assertEqual(reread["project_id"], original_id)

    def test_init_on_existing_malformed_project_id_raises_without_writing(self):
        path = config.config_path(self.notes_home, "badid")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bad_cfg = {"schema_version": 1, "project_id": "project:not-hex",
                   "project_slug": "badid", "repositories": []}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bad_cfg, f)
        before = open(path, "r", encoding="utf-8").read()
        with self.assertRaises(config.ConfigInvalidError) as ctx:
            config.init_project(self.notes_home, "badid")
        codes = {f["code"] for f in ctx.exception.findings}
        self.assertIn("E_CONFIG_MALFORMED_PROJECT_ID", codes)
        after = open(path, "r", encoding="utf-8").read()
        self.assertEqual(before, after)

    def test_structural_and_shared_findings_reject_repo_shaped_project_id(self):
        cfg = {"schema_version": 1, "project_id": "project:thomas-estep/bindle",
               "project_slug": "x", "repositories": []}
        findings = config.all_findings(cfg)
        codes = {f["code"] for f in findings}
        self.assertIn("E_CONFIG_PROJECT_ID_REPO_SHAPED", codes)

    def test_config_path_is_under_notes_home(self):
        path = config.config_path(self.notes_home, "myproj")
        self.assertTrue(path.startswith(self.notes_home + os.sep))
        self.assertIn(os.path.join(".bindle", "context"), path)

    def test_finding_always_has_index_and_field_keys(self):
        # a zero-index/field-arg finding (e.g. ConfigMissingError's shape)
        # must still carry both keys, defaulting to None, matching
        # validation._finding's shape exactly.
        finding = config._finding("E_SOME_CODE", "some message")
        self.assertIn("index", finding)
        self.assertIn("field", finding)
        self.assertIsNone(finding["index"])
        self.assertIsNone(finding["field"])
        # a field-only kwarg (e.g. E_CONFIG_SCHEMA_VERSION_UNSUPPORTED) still
        # gets an index key defaulted to None.
        finding2 = config._finding("E_OTHER", "msg", field="schema_version")
        self.assertEqual(finding2["field"], "schema_version")
        self.assertIsNone(finding2["index"])

    def test_all_findings_rejects_non_dict_top_level_shape(self):
        findings = config.all_findings([1, 2, 3])
        self.assertTrue(findings)
        codes = {f["code"] for f in findings}
        self.assertIn("E_CONFIG_MALFORMED_SHAPE", codes)

    def test_all_findings_rejects_non_list_repositories(self):
        cfg = {"schema_version": 1, "project_id": "project:" + ("a" * 32),
               "project_slug": "y", "repositories": "not-a-list"}
        findings = config.all_findings(cfg)
        self.assertTrue(findings)
        codes = {f["code"] for f in findings}
        self.assertIn("E_CONFIG_MALFORMED_SHAPE", codes)

    def test_all_findings_rejects_non_dict_repository_entry(self):
        cfg = {"schema_version": 1, "project_id": "project:" + ("a" * 32),
               "project_slug": "y", "repositories": ["not-a-dict"]}
        findings = config.all_findings(cfg)
        self.assertTrue(findings)
        codes = {f["code"] for f in findings}
        self.assertIn("E_CONFIG_MALFORMED_SHAPE", codes)

    def test_init_project_on_malformed_shape_raises_config_invalid_without_writing(self):
        path = config.config_path(self.notes_home, "malformed")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        before = open(path, "r", encoding="utf-8").read()
        with self.assertRaises(config.ConfigInvalidError) as ctx:
            config.init_project(self.notes_home, "malformed")
        codes = {f["code"] for f in ctx.exception.findings}
        self.assertIn("E_CONFIG_MALFORMED_SHAPE", codes)
        # the malformed original is untouched, not replaced or emptied
        after = open(path, "r", encoding="utf-8").read()
        self.assertEqual(before, after)


class TestRepositoryBindingCrud(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        config.init_project(self.notes_home, "proj")

    def test_add_repository_creates_binding(self):
        cfg, entry = config.add_repository(
            self.notes_home, "proj", alias="main", provider="github",
            coordinates="thomas-estep/bindle")
        self.assertEqual(len(cfg["repositories"]), 1)
        self.assertRegex(entry["binding_id"], r"^repository-binding:[0-9a-f]{32}$")
        self.assertEqual(entry["alias"], "main")

    def test_add_multiple_repositories(self):
        config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        cfg, _ = config.add_repository(self.notes_home, "proj", alias="b", provider="github")
        self.assertEqual([r["alias"] for r in cfg["repositories"]], ["a", "b"])

    def test_add_repository_with_default_flag(self):
        cfg, entry = config.add_repository(
            self.notes_home, "proj", alias="a", provider="github", is_default=True)
        self.assertTrue(entry["default_for_bare_references"])
        defaults = [r for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(len(defaults), 1)

    def test_second_default_via_add_unsets_first(self):
        config.add_repository(self.notes_home, "proj", alias="a", provider="github", is_default=True)
        cfg, _ = config.add_repository(
            self.notes_home, "proj", alias="b", provider="github", is_default=True)
        defaults = [r["alias"] for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(defaults, ["b"])

    def test_two_defaults_rejected_by_validation(self):
        cfg = {
            "schema_version": 1, "project_id": config.allocate_project_id(),
            "project_slug": "x", "repositories": [
                {"alias": "a", "binding_id": config.allocate_binding_id(),
                 "provider": "github", "default_for_bare_references": True},
                {"alias": "b", "binding_id": config.allocate_binding_id(),
                 "provider": "github", "default_for_bare_references": True},
            ]}
        codes = {f["code"] for f in config.all_findings(cfg)}
        self.assertIn("E_CONFIG_MULTIPLE_DEFAULT", codes)

    def test_zero_defaults_is_valid(self):
        cfg, _ = config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        self.assertEqual(config.all_findings(cfg), [])

    def test_update_repository_coordinates_preserves_binding_id(self):
        _, entry = config.add_repository(
            self.notes_home, "proj", alias="a", provider="github",
            coordinates="old-owner/old-repo")
        binding_id = entry["binding_id"]
        cfg, updated = config.update_repository(
            self.notes_home, "proj", binding_id, coordinates="new-owner/new-repo")
        self.assertEqual(updated["binding_id"], binding_id)
        self.assertEqual(updated["coordinates"], "new-owner/new-repo")

    def test_update_repository_local_checkout_path_preserves_binding_id(self):
        _, entry = config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        binding_id = entry["binding_id"]
        cfg, updated = config.update_repository(
            self.notes_home, "proj", binding_id, local_checkout_path="/new/path")
        self.assertEqual(updated["binding_id"], binding_id)
        self.assertEqual(updated["local_checkout_path"], "/new/path")

    def test_update_repository_default_true_unsets_others(self):
        _, a = config.add_repository(self.notes_home, "proj", alias="a", provider="github",
                                      is_default=True)
        _, b = config.add_repository(self.notes_home, "proj", alias="b", provider="github")
        cfg, _ = config.update_repository(self.notes_home, "proj", b["binding_id"], default=True)
        defaults = [r["alias"] for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(defaults, ["b"])

    def test_update_repository_default_false_unsets_only_that_one(self):
        _, a = config.add_repository(self.notes_home, "proj", alias="a", provider="github",
                                      is_default=True)
        cfg, _ = config.update_repository(self.notes_home, "proj", a["binding_id"], default=False)
        defaults = [r for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(defaults, [])

    def test_update_repository_unknown_binding_raises(self):
        with self.assertRaises(config.BindingNotFoundError):
            config.update_repository(self.notes_home, "proj",
                                      "repository-binding:" + "0" * 32, alias="x")

    def test_remove_repository_preserves_project_id(self):
        before = config.load_config(config.config_path(self.notes_home, "proj"))
        _, entry = config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        cfg, removed = config.remove_repository(self.notes_home, "proj", entry["binding_id"])
        self.assertEqual(cfg["project_id"], before["project_id"])
        self.assertEqual(cfg["repositories"], [])
        self.assertEqual(removed["binding_id"], entry["binding_id"])

    def test_remove_repository_unknown_binding_raises(self):
        with self.assertRaises(config.BindingNotFoundError):
            config.remove_repository(self.notes_home, "proj", "repository-binding:" + "1" * 32)

    def test_set_default_sets_unique_default(self):
        _, a = config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        cfg, _ = config.set_default(self.notes_home, "proj", a["binding_id"])
        defaults = [r["alias"] for r in cfg["repositories"] if r.get("default_for_bare_references")]
        self.assertEqual(defaults, ["a"])

    def test_duplicate_alias_rejected_on_add(self):
        config.add_repository(self.notes_home, "proj", alias="dup", provider="github")
        with self.assertRaises(config.ConfigInvalidError) as ctx:
            config.add_repository(self.notes_home, "proj", alias="dup", provider="github")
        codes = {f["code"] for f in ctx.exception.findings}
        self.assertIn("E_CONFIG_DUPLICATE_ALIAS", codes)

    def test_duplicate_binding_id_rejected_by_validation(self):
        dup = config.allocate_binding_id()
        cfg = {
            "schema_version": 1, "project_id": config.allocate_project_id(),
            "project_slug": "x", "repositories": [
                {"alias": "a", "binding_id": dup, "provider": "github"},
                {"alias": "b", "binding_id": dup, "provider": "github"},
            ]}
        codes = {f["code"] for f in config.all_findings(cfg)}
        self.assertIn("E_CONFIG_DUPLICATE_BINDING_ID", codes)

    def test_mutating_on_invalid_existing_config_raises_without_mutating(self):
        path = config.config_path(self.notes_home, "proj")
        cfg = config.load_config(path)
        cfg["project_id"] = "project:not-hex"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        before = open(path, "r", encoding="utf-8").read()
        with self.assertRaises(config.ConfigInvalidError):
            config.add_repository(self.notes_home, "proj", alias="a", provider="github")
        after = open(path, "r", encoding="utf-8").read()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
