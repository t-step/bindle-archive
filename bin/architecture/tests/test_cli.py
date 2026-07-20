"""Tests for bin/architecture-projection.py (issue #374 child D, slice D5).

These drive the CLI as a REAL SUBPROCESS rather than calling `main()`
in-process. That is deliberate and costs the process spawns: the whole
point of this slice is that `bin/architecture/` had zero production callers
and was only ever exercised by importing it from a test. An in-process
`main([...])` call would repeat exactly that mistake one layer up -- it
would not prove the file is executable, that its shebang works, that
`sys.path` bootstrapping resolves the package from an arbitrary working
directory, or that the exit code reaches a shell.

The `sys.path` case has teeth here specifically: the domain package is
`bin/architecture/` and a regular package shadows a sibling module of the
same name, which is why the CLI is NOT named `bin/architecture.py`. A test
that imported it would silently import the package instead.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import state

REPO_BIN = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".."))
CLI = os.path.join(REPO_BIN, "architecture-projection.py")
SLUG = "bindle"


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class CliTestCase(unittest.TestCase):

    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)

    def run_cli(self, *args, **kwargs):
        """Run from a working directory that is NOT the repo, so a CLI that
        only worked because of an implicit cwd on sys.path would fail."""
        cwd = kwargs.pop("cwd", self.notes_home)
        proc = subprocess.run(
            [sys.executable, CLI] + list(args),
            cwd=cwd, capture_output=True, text=True)
        return proc

    def run_json(self, *args):
        proc = self.run_cli(*args)
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            self.fail("stdout was not JSON.\nstdout=%r\nstderr=%r"
                      % (proc.stdout, proc.stderr))
        return proc, payload

    def init(self, *extra):
        return self.run_json("init", "--notes-home", self.notes_home,
                             "--project", SLUG, *extra)


class InitCommandTests(CliTestCase):

    def test_init_exits_zero(self):
        proc, _ = self.init()
        self.assertEqual(0, proc.returncode, proc.stderr)

    def test_init_reports_created_and_a_valid_config(self):
        _, payload = self.init()
        self.assertTrue(payload["created"])
        self.assertEqual([], state.validate_config(payload["config"]))

    def test_init_writes_the_config_to_disk(self):
        self.init()
        self.assertTrue(os.path.isfile(
            state.config_path(self.notes_home, SLUG)))

    def test_init_is_idempotent_across_separate_processes(self):
        """Two real invocations, not two calls in one interpreter -- the
        lock and the zero-write guarantee both concern separate runs."""
        _, first = self.init()
        path = state.config_path(self.notes_home, SLUG)
        before = _read_bytes(path)
        proc, second = self.init()
        self.assertEqual(0, proc.returncode)
        self.assertFalse(second["created"])
        self.assertEqual(first["config"]["project_id"],
                         second["config"]["project_id"])
        self.assertEqual(before, _read_bytes(path))

    def test_init_honors_max_nodes(self):
        _, payload = self.init("--max-nodes", "7")
        self.assertEqual(7, payload["config"]["caps"]["max_nodes"])

    def test_init_rejects_a_zero_cap_as_a_usage_error(self):
        proc = self.run_cli("init", "--notes-home", self.notes_home,
                            "--project", SLUG, "--max-nodes", "0")
        self.assertEqual(2, proc.returncode)

    def test_init_rejects_an_out_of_range_threshold_as_a_usage_error(self):
        proc = self.run_cli("init", "--notes-home", self.notes_home,
                            "--project", SLUG, "--threshold-high", "1.5")
        self.assertEqual(2, proc.returncode)

    def test_init_renders_findings_not_a_traceback_on_a_bad_slug(self):
        proc, payload = self.run_json(
            "init", "--notes-home", self.notes_home, "--project", "Not A Slug")
        self.assertEqual(1, proc.returncode)
        self.assertEqual(["E_ARCH_CONFIG_MALFORMED_PROJECT_SLUG"],
                         [f["code"] for f in payload["findings"]])
        self.assertNotIn("Traceback", proc.stderr)

    def test_init_renders_findings_not_a_traceback_on_a_broken_config(self):
        path = state.config_path(self.notes_home, SLUG)
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        proc, payload = self.init()
        self.assertEqual(1, proc.returncode)
        self.assertEqual(["E_ARCH_CONFIG_UNREADABLE"],
                         [f["code"] for f in payload["findings"]])
        self.assertNotIn("Traceback", proc.stderr)

    def test_text_format_is_not_json(self):
        proc = self.run_cli("init", "--notes-home", self.notes_home,
                            "--project", SLUG, "--format", "text")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("created architecture projection", proc.stdout)
        self.assertRaises(ValueError, json.loads, proc.stdout)


class ConfigCommandTests(CliTestCase):

    def test_status_before_init_reports_missing(self):
        proc, payload = self.run_json(
            "config", "status", "--notes-home", self.notes_home,
            "--project", SLUG)
        self.assertEqual(1, proc.returncode)
        self.assertEqual(["E_ARCH_CONFIG_MISSING"],
                         [f["code"] for f in payload["findings"]])

    def test_status_after_init_reports_the_config(self):
        self.init()
        proc, payload = self.run_json(
            "config", "status", "--notes-home", self.notes_home,
            "--project", SLUG)
        self.assertEqual(0, proc.returncode)
        self.assertEqual(SLUG, payload["config"]["project_slug"])

    def test_status_reports_no_lock_holder_when_idle(self):
        self.init()
        _, payload = self.run_json(
            "config", "status", "--notes-home", self.notes_home,
            "--project", SLUG)
        self.assertIsNone(payload["lock"])

    def test_validate_before_init_exits_one(self):
        proc, payload = self.run_json(
            "config", "validate", "--notes-home", self.notes_home,
            "--project", SLUG)
        self.assertEqual(1, proc.returncode)
        self.assertEqual(["E_ARCH_CONFIG_MISSING"],
                         [f["code"] for f in payload["findings"]])

    def test_validate_after_init_exits_zero_with_no_findings(self):
        self.init()
        proc, payload = self.run_json(
            "config", "validate", "--notes-home", self.notes_home,
            "--project", SLUG)
        self.assertEqual(0, proc.returncode)
        self.assertEqual([], payload["findings"])

    def test_validate_reports_a_hand_corrupted_config(self):
        self.init()
        path = state.config_path(self.notes_home, SLUG)
        with open(path, encoding="utf-8") as handle:
            cfg = json.load(handle)
        del cfg["thresholds"]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle)
        proc, payload = self.run_json(
            "config", "validate", "--notes-home", self.notes_home,
            "--project", SLUG)
        self.assertEqual(1, proc.returncode)
        self.assertIn("E_ARCH_CONFIG_MISSING_FIELD",
                      [f["code"] for f in payload["findings"]])

    def test_validate_writes_nothing(self):
        self.init()
        path = state.config_path(self.notes_home, SLUG)
        before = _read_bytes(path)
        before_mtime = os.stat(path).st_mtime_ns
        self.run_cli("config", "validate", "--notes-home", self.notes_home,
                     "--project", SLUG)
        self.assertEqual(before, _read_bytes(path))
        self.assertEqual(before_mtime, os.stat(path).st_mtime_ns)


BINDING = "repository-binding:" + "0" * 31 + "1"


class PreviewCommandTests(CliTestCase):

    def write_graph(self):
        doc = {
            "schema_version": 1,
            "binding_id": BINDING,
            "source_commit": "a" * 40,
            "provider": {"name": "reference-json", "version": "1.0.0"},
            "capabilities": ["contains"],
            "root": "",
            "coverage": [{"path_prefix": "", "capability": "contains",
                          "status": "observed"}],
            "files": [{"path": "src/app.py"}],
            "symbols": [{"id": "sym-1", "name": "app", "kind": "module",
                         "path": "src/app.py"}],
            "edges": [],
        }
        path = os.path.join(self.notes_home, "graph.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        return path

    def configured(self):
        self.init()
        self.run_json("config", "add-binding", "--notes-home",
                      self.notes_home, "--project", SLUG, "--alias", "main",
                      "--binding-id", BINDING)
        return self.write_graph()

    def preview(self, graph):
        return self.run_json(
            "preview", "--notes-home", self.notes_home, "--project", SLUG,
            "--graph", "%s=%s" % (BINDING, graph),
            "--decided-at", "2026-07-20T00:00:00Z")

    def test_preview_exits_zero_and_plans(self):
        proc, payload = self.preview(self.configured())
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["entries"])

    def test_preview_prints_a_fingerprint(self):
        _, payload = self.preview(self.configured())
        self.assertTrue(payload["fingerprint"].startswith("arch-plan:sha256:"))

    def test_two_cli_previews_agree_on_the_fingerprint(self):
        """Across two real processes, which is how preview and apply will
        actually be invoked."""
        graph = self.configured()
        _, first = self.preview(graph)
        _, second = self.preview(graph)
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_preview_writes_nothing_to_the_notes_home(self):
        graph = self.configured()
        before = _read_bytes(state.config_path(self.notes_home, SLUG))
        self.preview(graph)
        self.assertEqual(
            before, _read_bytes(state.config_path(self.notes_home, SLUG)))
        self.assertFalse(os.path.exists(
            state.index_path(self.notes_home, SLUG)))
        self.assertFalse(os.path.exists(
            state.judgments_path(self.notes_home, SLUG)))

    def test_preview_before_init_is_a_findings_list(self):
        proc, payload = self.run_json(
            "preview", "--notes-home", self.notes_home, "--project", SLUG)
        self.assertEqual(1, proc.returncode)
        self.assertEqual(["E_ARCH_PREVIEW_CONFIG_MISSING"],
                         [f["code"] for f in payload["findings"]])
        self.assertNotIn("Traceback", proc.stderr)

    def test_a_malformed_graph_argument_is_a_usage_finding(self):
        self.configured()
        proc, payload = self.run_json(
            "preview", "--notes-home", self.notes_home, "--project", SLUG,
            "--graph", "no-equals-sign")
        self.assertEqual(1, proc.returncode)
        self.assertEqual(["E_USAGE"],
                         [f["code"] for f in payload["findings"]])

    def test_text_format_shows_the_plan_not_just_ok(self):
        """A successful preview carries `findings: []`, which the generic
        empty-findings branch would render as "ok: no findings" -- hiding
        the whole plan. Asserting the returncode alone passes vacuously
        against exactly that bug."""
        graph = self.configured()
        proc = self.run_cli(
            "preview", "--notes-home", self.notes_home, "--project", SLUG,
            "--graph", "%s=%s" % (BINDING, graph), "--format", "text")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertNotIn("ok: no findings", proc.stdout)
        self.assertIn("architecture preview", proc.stdout)
        self.assertIn("fingerprint: arch-plan:sha256:", proc.stdout)
        self.assertIn("Codebase Map.md", proc.stdout)


class AddBindingCommandTests(CliTestCase):

    def test_add_binding_exits_zero(self):
        self.init()
        proc, payload = self.run_json(
            "config", "add-binding", "--notes-home", self.notes_home,
            "--project", SLUG, "--alias", "main")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("main", payload["binding"]["alias"])

    def test_add_binding_before_init_is_a_findings_list(self):
        proc, payload = self.run_json(
            "config", "add-binding", "--notes-home", self.notes_home,
            "--project", SLUG, "--alias", "main")
        self.assertEqual(1, proc.returncode)
        self.assertEqual(["E_ARCH_CONFIG_MISSING"],
                         [f["code"] for f in payload["findings"]])
        self.assertNotIn("Traceback", proc.stderr)

    def test_a_supplied_binding_id_survives_to_the_config(self):
        self.init()
        self.run_json("config", "add-binding", "--notes-home",
                      self.notes_home, "--project", SLUG, "--alias", "main",
                      "--binding-id", BINDING)
        _, payload = self.run_json(
            "config", "status", "--notes-home", self.notes_home,
            "--project", SLUG)
        self.assertEqual([{"binding_id": BINDING, "alias": "main"}],
                         payload["config"]["bindings"])

    def test_a_duplicate_alias_is_a_findings_list(self):
        self.init()
        self.run_json("config", "add-binding", "--notes-home",
                      self.notes_home, "--project", SLUG, "--alias", "main")
        proc, payload = self.run_json(
            "config", "add-binding", "--notes-home", self.notes_home,
            "--project", SLUG, "--alias", "main")
        self.assertEqual(1, proc.returncode)
        self.assertEqual(["E_ARCH_CONFIG_BAD_BINDING"],
                         [f["code"] for f in payload["findings"]])


class SurfaceTests(CliTestCase):

    def test_the_cli_file_is_executable(self):
        self.assertTrue(os.access(CLI, os.X_OK),
                        "%s is not executable" % CLI)

    def test_no_subcommand_is_a_usage_error(self):
        proc = self.run_cli()
        self.assertEqual(2, proc.returncode)

    def test_unimplemented_verbs_are_absent_rather_than_stubbed(self):
        """confirm/apply land in the next slice. A stub that accepted them
        and did nothing would be worse than a usage error -- it would look
        like a working projection loop. `preview` landed in D5b and is
        deliberately no longer in this list."""
        for verb in ("confirm", "apply"):
            proc = self.run_cli(verb, "--notes-home", self.notes_home,
                                "--project", SLUG)
            self.assertEqual(2, proc.returncode,
                             "%r should not be accepted yet" % verb)

    def test_help_succeeds(self):
        proc = self.run_cli("--help")
        self.assertEqual(0, proc.returncode)
        self.assertIn("init", proc.stdout)


if __name__ == "__main__":
    unittest.main()
