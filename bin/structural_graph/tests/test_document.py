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
from structural_graph import schema

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


class TestPathAnchorSecretScan(unittest.TestCase):
    """A relative path only fails normalize_path's *shape* check (absolute,
    drive letter, traversal, query string, out-of-root) -- it has no
    opinion on the path's *content*. Anchors are exempt from redaction (it
    would break the references that point at them), so a relative path
    that carries a secret needs the same fail-closed secret scan the other
    anchors (symbols[].id, symbols[].name, edges[].source/target) already
    get. #227 review finding: files[].path, symbols[].path, and
    coverage[].path_prefix were left out of that scan.
    """

    def test_secret_in_a_file_path_anchor_is_malformed(self):
        doc = minimal_document()
        doc["files"][0]["path"] = "src/" + "ghp_" + "A" * 36 + "/app.py"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_secret_in_a_symbol_path_anchor_is_malformed(self):
        doc = minimal_document()
        doc["symbols"][0]["path"] = "src/" + "sk-" + "A" * 24 + "/app.py"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_secret_in_a_coverage_path_prefix_anchor_is_malformed(self):
        doc = minimal_document()
        doc["coverage"].append(
            {
                "path_prefix": "src/" + "AKIA" + "1234567890ABCDEF",
                "capability": "contains",
                "status": "observed",
            }
        )
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])

    def test_ordinary_relative_path_still_loads_clean(self):
        doc = minimal_document()
        doc["files"][0]["path"] = "src/app.py"
        doc["symbols"][0]["path"] = "src/app.py"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["facts"]["files"][0]["path"], "src/app.py")


class TestRootAnchorSecretScan(unittest.TestCase):
    """root is the eighth entry in schema.ANCHOR_FIELDS and, until this
    fix, the one the secret scan never reached: _anchor_findings hand-listed
    the fields it scanned instead of deriving them from the registry, and
    root was never added to that list across four review rounds. A root of
    "src/ghp_..." normalizes cleanly (normalize_path only judges a path's
    *shape*) and is exempt from redaction as an anchor, so without this scan
    it would land in facts with the secret intact. #227.
    """

    def test_secret_in_root_is_malformed(self):
        doc = minimal_document()
        doc["root"] = "src/" + "ghp_" + "A" * 36  # private-ok: not a real credential
        doc["files"] = []
        doc["symbols"] = []
        doc["edges"] = []
        doc["coverage"] = [
            {
                "path_prefix": doc["root"],
                "capability": "contains",
                "status": "observed",
            }
        ]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertIn(
            "E_SG_UNNORMALIZABLE_ANCHOR", [f["code"] for f in result["findings"]]
        )
        self.assertIsNone(result["facts"])
        self.assertNotIn("ghp_", json.dumps(result["findings"]))


class TestAnchorRegistryDriftGuard(unittest.TestCase):
    """schema.ANCHOR_FIELDS is meant to be the single source of truth for
    what document.py's anchor secret scan covers (#227 structural fix,
    following four rounds of one-field-at-a-time patches). This test
    enumerates the registry itself -- not a hand-copied list of its current
    members -- and builds a document with a secret sitting at each entry's
    value(s), so a future field added to ANCHOR_FIELDS without matching
    scan coverage fails this suite instead of shipping unpoliced.
    """

    SECRET = "ghp_" + "A" * 36  # private-ok: not a real credential

    @classmethod
    def _inject_secret(cls, field):
        """Return a document with a secret at every value `field` names.

        Mirrors document._anchor_values's own dotted-path parsing (a
        top-level scalar, or "<collection>[].<key>") so a newly registered
        field is exercised without touching this method -- except where the
        schema's own cross-field invariants (coverage must tile root; an
        edge endpoint must resolve to a real symbol id) would otherwise get
        the document rejected by validate_document or coverage tiling
        before the anchor scan is ever reached. Those two collections are
        special-cased by name, not by which key is under test, so a new
        anchor key added to either one is still handled here unchanged.
        """
        doc = minimal_document()
        if field == "root":
            doc["root"] = cls.SECRET
            doc["files"] = []
            doc["symbols"] = []
            doc["edges"] = []
            doc["coverage"] = [
                {
                    "path_prefix": cls.SECRET,
                    "capability": "contains",
                    "status": "observed",
                }
            ]
            return doc
        collection, key = field.split("[].", 1)
        if collection == "coverage":
            entry = {
                "path_prefix": "",
                "capability": "contains",
                "status": "observed",
            }
            entry[key] = cls.SECRET
            doc["coverage"].append(entry)
            return doc
        if collection == "edges":
            entry = {"type": "calls", "source": "sym-1", "target": "sym-1"}
            entry[key] = cls.SECRET
            doc["symbols"].append(
                {
                    "id": cls.SECRET,
                    "name": "other",
                    "kind": "function",
                    "path": "src/app.py",
                }
            )
            doc["edges"].append(entry)
            return doc
        doc[collection][0][key] = cls.SECRET
        return doc

    def test_every_registered_anchor_field_is_secret_scanned(self):
        for field in schema.ANCHOR_FIELDS:
            with self.subTest(field=field):
                doc = self._inject_secret(field)
                result = document.load_object(doc, config())
                self.assertEqual(
                    result["status"],
                    "malformed",
                    "%s: secret anchor loaded instead of failing closed" % field,
                )
                self.assertTrue(
                    any(
                        found["code"] == "E_SG_UNNORMALIZABLE_ANCHOR"
                        and found["field"] == field
                        for found in result["findings"]
                    ),
                    "%s: no E_SG_UNNORMALIZABLE_ANCHOR finding for this field"
                    % field,
                )
                self.assertNotIn("ghp_", json.dumps(result["findings"]))

    def test_ordinary_document_still_loads_clean(self):
        result = document.load_object(minimal_document(), config())
        self.assertEqual(result["status"], "loaded")


class TestPrivacyFixtureRegressions(unittest.TestCase):
    """Mirrors testdata/structural-graph/v1/privacy/*.json at the unit level.

    The regression target is context_graph.evidence._classify_local_path,
    which rejects an unsafe absolute path and then echoes the raw value
    straight back into its own "rejected" result. structural_graph.redaction
    exists to make that impossible here: an anchor that cannot be
    normalized fails the document closed with a static message, and an
    incidental secret is scrubbed while the fact it names survives.
    """

    def test_absolute_path_anchor_is_malformed_and_finding_carries_no_value(self):
        # This path is both an absolute path (normalize_path shape check)
        # and a home-path secret (anchor secret scan, #227), so it now
        # legitimately produces two E_SG_UNNORMALIZABLE_ANCHOR findings
        # instead of one -- dedup by code the same way
        # check-structural-graph-fixtures.py's assert_load_status does,
        # rather than asserting an exact count of a code that can fire more
        # than once for independent reasons on the same value.
        doc = minimal_document()
        doc["files"][0]["path"] = "/Users" + "/jane/repo/src/app.py"
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(
            sorted(set(f["code"] for f in result["findings"])),
            ["E_SG_UNNORMALIZABLE_ANCHOR"],
        )
        self.assertIsNone(result["facts"])
        self.assertNotIn("jane", json.dumps(result["findings"]))

    def test_bearer_token_in_diagnostic_is_scrubbed_and_fact_survives(self):
        doc = minimal_document()
        doc["diagnostics"] = [
            {
                "message": "auth failed with ghp_"
                + "A" * 36
                + " reading "
                + "/Users"
                + "/jane/repo"
            }
        ]
        result = document.load_object(doc, config())
        self.assertEqual(result["status"], "loaded")
        blob = json.dumps(result["facts"])
        self.assertNotIn("ghp_" + "A" * 36, blob)
        self.assertNotIn("jane", blob)
        message = result["facts"]["diagnostics"][0]["message"]
        self.assertIn("[redacted:token]", message)
        self.assertIn("[redacted:home-path]", message)
        self.assertEqual(len(result["facts"]["files"]), 1)


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
