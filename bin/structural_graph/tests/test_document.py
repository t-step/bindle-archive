"""Unit tests for structural_graph.document."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from structural_graph import document

BINDING = "repository-binding:" + "0" * 31 + "1"
OTHER_BINDING = "repository-binding:" + "0" * 31 + "2"


def minimal_document():
    return {
        "schema_version": 1,
        "binding_id": BINDING,
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


def config(checkout=None):
    repo = {"alias": "main", "binding_id": BINDING, "provider": "github"}
    if checkout:
        repo["local_checkout_path"] = checkout
    return {"schema_version": 1, "repositories": [repo]}


class TestFailClosedOrder(unittest.TestCase):
    def test_unsupported_version_short_circuits_all_other_checks(self):
        doc = minimal_document()
        doc["schema_version"] = 99
        doc["symbols"][0]["kind"] = "also-invalid"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "unsupported_version")
        self.assertEqual(
            [f["code"] for f in result["findings"]],
            ["E_SG_UNSUPPORTED_SCHEMA_VERSION"],
        )
        self.assertIsNone(result["facts"])

    def test_structural_violation_is_malformed(self):
        doc = minimal_document()
        doc["symbols"][0]["kind"] = "gadget"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIsNone(result["facts"])


class TestNonDictDocument(unittest.TestCase):
    """A non-dict document (list, int, string, None) is legal JSON that
    json.load will happily hand to load_object. Before the fix, the version
    gate substituted an empty dict for it, reported a missing schema_version,
    and mislabeled the document "unsupported_version" -- a corrupt document
    is not one that merely needs a version migration. validate_document's
    dedicated "document is not a JSON object" finding is the accurate one.
    #227's review finding.
    """

    def test_list_document_is_malformed_not_unsupported_version(self):
        result = document.load_object([1, 2, 3], config())
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(
            [f["code"] for f in result["findings"]], ["E_SG_MISSING_FIELD"]
        )
        self.assertIsNone(result["facts"])

    def test_int_document_is_malformed_not_unsupported_version(self):
        result = document.load_object(42, config())
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(
            [f["code"] for f in result["findings"]], ["E_SG_MISSING_FIELD"]
        )

    def test_string_document_is_malformed_not_unsupported_version(self):
        result = document.load_object("hello", config())
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(
            [f["code"] for f in result["findings"]], ["E_SG_MISSING_FIELD"]
        )

    def test_none_document_is_malformed_not_unsupported_version(self):
        result = document.load_object(None, config())
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(
            [f["code"] for f in result["findings"]], ["E_SG_MISSING_FIELD"]
        )

    def test_non_dict_document_never_raises(self):
        for doc in ([1, 2, 3], 42, "hello", None, True, 3.14):
            try:
                document.load_object(doc, config())
            except Exception as exc:  # pragma: no cover - documents a non-raise
                self.fail("load_object raised %r on %r" % (exc, doc))


class TestBindingResolution(unittest.TestCase):
    def test_malformed_binding_id_is_malformed(self):
        doc = minimal_document()
        doc["binding_id"] = "not-a-binding"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_BINDING_ID", [f["code"] for f in result["findings"]]
        )

    def test_foreign_binding_id_is_deconfigured(self):
        doc = minimal_document()
        doc["binding_id"] = OTHER_BINDING
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "deconfigured")
        self.assertIn(
            "E_SG_BINDING_NOT_CONFIGURED", [f["code"] for f in result["findings"]]
        )


class TestCoverageIntegration(unittest.TestCase):
    def test_coverage_gap_is_malformed(self):
        doc = minimal_document()
        doc["coverage"] = []
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn("E_SG_COVERAGE_GAP", [f["code"] for f in result["findings"]])


class TestRedactionIntegration(unittest.TestCase):
    def test_unnormalizable_anchor_makes_document_malformed(self):
        doc = minimal_document()
        doc["files"][0]["path"] = "/etc/passwd"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_fact_outside_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = "pkg"
        doc["coverage"] = [
            {"path_prefix": "pkg", "capability": "contains", "status": "observed"}
        ]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )

    def test_incidental_string_is_redacted_and_the_fact_survives(self):
        doc = minimal_document()
        doc["diagnostics"] = [
            {"message": "could not open " + "/Users" + "/jane/repo/x.py"}
        ]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "loaded")
        self.assertNotIn("jane", json.dumps(result["facts"]))
        self.assertIn(
            "[redacted:home-path]", result["facts"]["diagnostics"][0]["message"]
        )
        self.assertEqual(len(result["facts"]["files"]), 1)

    def test_secret_in_a_symbol_name_anchor_is_malformed(self):
        doc = minimal_document()
        doc["symbols"][0]["name"] = "ghp_" + "A" * 36
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )

    def test_secret_in_a_list_shaped_symbol_name_is_malformed(self):
        # A non-string name bypasses redaction.redact's pattern match (it
        # no-ops on anything but a string), so this only fails closed if
        # validation.py's symbols[].name type-check catches the shape first.
        doc = minimal_document()
        doc["symbols"][0]["name"] = ["ghp_" + "A" * 36]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_secret_in_an_edge_endpoint_anchor_is_malformed(self):
        doc = minimal_document()
        doc["symbols"].append(
            {
                "id": "/Users" + "/jane/x",
                "name": "other",
                "kind": "function",
                "path": "src/app.py",
            }
        )
        doc["edges"] = [
            {"type": "calls", "source": "sym-1", "target": "/Users" + "/jane/x"}
        ]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )

    def test_no_finding_carries_an_unredacted_secret(self):
        doc = minimal_document()
        doc["files"][0]["path"] = "/Users" + "/jane/repo/x.py"
        result = document.load_object(doc, config())
        self.assertNotIn("jane", json.dumps(result["findings"]))


class TestMalformedRoot(unittest.TestCase):
    """A non-string root must fail the document closed, not load.

    document.py used to default a falsy root to "" with
    `doc.get("root") or ""` before checking it, which folded every falsy
    malformed value (0, False, [], {}, None) into the same value the
    legal empty-string root produces -- the document loaded with the
    malformed value smuggled straight into facts["root"] untouched.
    #227's review finding.
    """

    def test_empty_string_root_still_loads(self):
        doc = minimal_document()
        doc["root"] = ""
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["facts"]["root"], "")

    def test_zero_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = 0
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_false_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = False
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_empty_list_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = []
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_empty_dict_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = {}
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_none_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = None
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_truthy_non_string_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = ["x"]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])


class TestMalformedProvider(unittest.TestCase):
    """A malformed provider must fail the document closed, not load.

    Before the fix, validation.py only checked that "provider" was present,
    never its shape: a string or list provider passed straight through into
    facts["provider"] with status="loaded". #227 Task 7 carried finding
    (Task 5's review).
    """

    def test_string_provider_is_malformed(self):
        doc = minimal_document()
        doc["provider"] = "not-a-dict"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_list_provider_is_malformed(self):
        doc = minimal_document()
        doc["provider"] = ["a", "b"]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_MALFORMED_FIELD_SHAPE", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_valid_provider_still_loads(self):
        doc = minimal_document()
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(
            result["facts"]["provider"], {"name": "reference-json", "version": "1.0.0"}
        )


class TestFreshness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git_repo(self):
        env = dict(os.environ)
        for var in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_COMMON_DIR",
        ):
            env.pop(var, None)
        subprocess.check_call(["git", "-C", self.tmp, "init", "-q"], env=env)
        subprocess.check_call(
            ["git", "-C", self.tmp, "config", "user.email", "t@example.com"], env=env
        )
        subprocess.check_call(
            ["git", "-C", self.tmp, "config", "user.name", "t"], env=env
        )
        with open(os.path.join(self.tmp, "f.txt"), "w") as handle:
            handle.write("x\n")
        subprocess.check_call(["git", "-C", self.tmp, "add", "f.txt"], env=env)
        subprocess.check_call(
            ["git", "-C", self.tmp, "commit", "-q", "-m", "init"], env=env
        )
        return subprocess.check_output(
            ["git", "-C", self.tmp, "rev-parse", "HEAD"], env=env
        ).decode().strip()

    def test_no_checkout_is_freshness_unknown(self):
        result = document.load_object(minimal_document(), config())
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["freshness"], "freshness_unknown")

    def test_matching_commit_is_current(self):
        head = self._git_repo()
        doc = minimal_document()
        doc["source_commit"] = head
        result = document.load_object(doc, config(checkout=self.tmp))
        self.assertEqual(result["freshness"], "current")

    def test_differing_commit_is_stale_but_still_loads(self):
        self._git_repo()
        doc = minimal_document()
        doc["source_commit"] = "b" * 40
        result = document.load_object(doc, config(checkout=self.tmp))
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["freshness"], "stale")
        self.assertIsNotNone(result["facts"])


class TestFileLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_absent_file_is_unavailable(self):
        result = document.load(os.path.join(self.tmp, "nope.json"), config())
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["facts"])

    def test_unparseable_file_is_malformed(self):
        path = os.path.join(self.tmp, "bad.json")
        with open(path, "w") as handle:
            handle.write("{not json")
        result = document.load(path, config())
        self.assertEqual(result["status"], "malformed")

    def test_valid_file_loads(self):
        path = os.path.join(self.tmp, "good.json")
        with open(path, "w") as handle:
            handle.write(json.dumps(minimal_document()))
        result = document.load(path, config())
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["facts"]["binding_id"], BINDING)

    def test_load_writes_nothing(self):
        path = os.path.join(self.tmp, "good.json")
        with open(path, "w") as handle:
            handle.write(json.dumps(minimal_document()))
        before = sorted(os.listdir(self.tmp))
        document.load(path, config())
        self.assertEqual(sorted(os.listdir(self.tmp)), before)


if __name__ == "__main__":
    unittest.main()
