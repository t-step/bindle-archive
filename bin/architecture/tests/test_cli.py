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


def _snapshot(notes_home):
    """Full path -> bytes map of the PROJECTS tree, so a write anywhere
    under it is visible including one to a file a test never named.

    Scoped to `projects/` rather than the whole notes home because these
    fixtures keep the interchange document beside it, and a test that
    edits the graph would otherwise read as a write to the notes home."""
    root = os.path.join(notes_home, "projects")
    seen = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            seen[os.path.relpath(path, notes_home)] = _read_bytes(path)
    return seen


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


class ConfirmCommandTests(PreviewCommandTests):

    def confirm(self, graph, token, *extra):
        return self.run_json(
            "confirm", "--notes-home", self.notes_home, "--project", SLUG,
            "--graph", "%s=%s" % (BINDING, graph),
            "--decided-at", "2026-07-20T00:00:00Z",
            "--fingerprint", token, *extra)

    def test_a_current_token_confirms_and_exits_zero(self):
        graph = self.configured()
        _, plan = self.preview(graph)
        proc, payload = self.confirm(graph, plan["fingerprint"])
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(payload["confirmed"])

    def test_a_stale_token_is_refused_and_exits_one(self):
        """PT25, caught one step before apply. The token is checked against
        a freshly rebuilt plan, so an input that moved since the operator
        read the preview cannot be confirmed."""
        graph = self.configured()
        proc, payload = self.confirm(graph, "arch-plan:sha256:" + "0" * 64)
        self.assertEqual(1, proc.returncode)
        self.assertFalse(payload["confirmed"])
        self.assertIn("E_ARCH_CONFIRM_STALE_TOKEN",
                      [f["code"] for f in payload["findings"]])

    def test_confirm_writes_nothing_to_the_notes_home(self):
        graph = self.configured()
        _, plan = self.preview(graph)
        before = _snapshot(self.notes_home)
        self.confirm(graph, plan["fingerprint"])
        self.assertEqual(before, _snapshot(self.notes_home))

    def test_a_small_first_projection_triggers_no_confirmation_policy(self):
        """The default diff-size limit is 200 and this plan writes two
        notes, so nothing in the static policy fires. Asserted so the
        policy's POSITIVE cases below cannot pass vacuously."""
        graph = self.configured()
        _, plan = self.preview(graph)
        _, payload = self.confirm(graph, plan["fingerprint"])
        self.assertFalse(payload["requires_confirmation"])
        self.assertEqual([], payload["confirmation_reasons"])

    def test_a_plan_over_the_diff_size_limit_requires_confirmation(self):
        """`diff_size_confirmation_limit` is validated by
        `state.validate_config` but had NO consumer anywhere in the package
        before this slice -- a configured threshold nothing enforced."""
        self.init("--diff-size-confirmation-limit", "1")
        self.run_json("config", "add-binding", "--notes-home",
                      self.notes_home, "--project", SLUG, "--alias", "main",
                      "--binding-id", BINDING)
        graph = self.write_graph()
        _, plan = self.preview(graph)
        _, payload = self.confirm(graph, plan["fingerprint"])
        self.assertTrue(payload["requires_confirmation"])
        self.assertEqual(["diff_size_over_limit"],
                         [r["reason"] for r in payload["confirmation_reasons"]])

    def test_requiring_confirmation_is_a_report_not_a_refusal(self):
        """A policy veto in a read-only verb would leave the operator no
        way to approve a large-but-correct refresh."""
        self.init("--diff-size-confirmation-limit", "1")
        self.run_json("config", "add-binding", "--notes-home",
                      self.notes_home, "--project", SLUG, "--alias", "main",
                      "--binding-id", BINDING)
        graph = self.write_graph()
        _, plan = self.preview(graph)
        proc, payload = self.confirm(graph, plan["fingerprint"])
        self.assertEqual(0, proc.returncode)
        self.assertTrue(payload["confirmed"])
        self.assertTrue(payload["requires_confirmation"])


class ApplyCommandTests(PreviewCommandTests):

    def apply(self, graph, token):
        return self.run_json(
            "apply", "--notes-home", self.notes_home, "--project", SLUG,
            "--graph", "%s=%s" % (BINDING, graph),
            "--decided-at", "2026-07-20T00:00:00Z",
            "--projected-at", "2026-07-20T00:00:00Z",
            "--approval-token", token)

    def test_apply_with_the_printed_token_creates_the_notes(self):
        graph = self.configured()
        _, plan = self.preview(graph)
        proc, payload = self.apply(graph, plan["fingerprint"])
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("applied", payload["status"])
        for entry in plan["entries"]:
            self.assertTrue(os.path.isfile(os.path.join(
                self.notes_home, "projects", SLUG, entry["note_path"])))

    def test_apply_with_a_stale_token_aborts_and_writes_nothing(self):
        """PT25 at the surface that actually writes. The comparison happens
        inside `apply.apply` under the project lock, not in the CLI."""
        graph = self.configured()
        before = _snapshot(self.notes_home)
        proc, payload = self.apply(graph, "arch-plan:sha256:" + "0" * 64)
        self.assertEqual(1, proc.returncode)
        self.assertEqual("stale_preview", payload["status"])
        self.assertEqual(before, _snapshot(self.notes_home))

    def test_apply_with_no_token_is_a_usage_error(self):
        graph = self.configured()
        proc = self.run_cli(
            "apply", "--notes-home", self.notes_home, "--project", SLUG,
            "--graph", "%s=%s" % (BINDING, graph))
        self.assertEqual(2, proc.returncode)


class FullCycleTests(PreviewCommandTests):
    """#374's headline acceptance criterion, driven end to end through the
    real CLI as separate processes: init -> add-binding -> preview ->
    confirm -> apply -> rerun. Every prior slice asserted its own link with
    the next stage's input built by hand."""

    def cycle(self, graph):
        _, plan = self.preview(graph)
        confirm_proc, confirmed = self.run_json(
            "confirm", "--notes-home", self.notes_home, "--project", SLUG,
            "--graph", "%s=%s" % (BINDING, graph),
            "--decided-at", "2026-07-20T00:00:00Z",
            "--fingerprint", plan["fingerprint"])
        self.assertEqual(0, confirm_proc.returncode, confirm_proc.stderr)
        self.assertTrue(confirmed["confirmed"])
        apply_proc, applied = self.run_json(
            "apply", "--notes-home", self.notes_home, "--project", SLUG,
            "--graph", "%s=%s" % (BINDING, graph),
            "--decided-at", "2026-07-20T00:00:00Z",
            "--projected-at", "2026-07-20T00:00:00Z",
            "--approval-token", plan["fingerprint"])
        self.assertEqual(0, apply_proc.returncode, apply_proc.stderr)
        return plan, applied

    def test_the_full_cycle_runs_and_writes_the_projection(self):
        graph = self.configured()
        plan, applied = self.cycle(graph)
        self.assertEqual("applied", applied["status"])
        self.assertEqual(len(plan["entries"]), len(applied["writes"]))

    def test_a_rerun_at_the_same_commit_writes_zero_bytes(self):
        """THE criterion. Asserted through the real CLI over the whole
        notes home, not through `apply()` in a fixture."""
        graph = self.configured()
        self.cycle(graph)
        before = _snapshot(self.notes_home)
        self.cycle(graph)
        self.assertEqual(before, _snapshot(self.notes_home))

    def test_the_rerun_reuses_the_identities_the_first_run_committed(self):
        """Guards the zero-write test from passing for the wrong reason: a
        run that re-minted every identity could still render byte-identical
        notes, and the damage would be in the log."""
        graph = self.configured()
        self.cycle(graph)
        _, committed = self.preview(graph)
        self.assertEqual(
            ["reuse"] * len(committed["entries"]),
            [e["identity_outcome"] for e in committed["entries"]])
        self.cycle(graph)
        _, after_rerun = self.preview(graph)
        self.assertEqual(
            {e["candidate_key"]: e["arch_id"] for e in committed["entries"]},
            {e["candidate_key"]: e["arch_id"] for e in after_rerun["entries"]})

    def test_a_previewed_arch_id_is_provisional_until_apply_commits_one(self):
        """A DELIBERATE, DOCUMENTED ASYMMETRY, asserted so it cannot be
        mistaken for a bug later.

        `apply` rebuilds the plan in its own process and mints its own
        hexes, so the arch_id a first-ever `preview` displays is NOT the
        one that gets committed. That is safe -- `arch_id` enters no
        fingerprint term, which is exactly why the token still matches --
        and it is unavoidable: nothing carries a minted hex between two
        processes, because the only thing the operator carries is the
        token, and #230 bars persisting it.

        Every LATER preview is exact, because the identity is then read
        back from the log rather than minted."""
        graph = self.configured()
        before_apply, _ = self.cycle(graph)
        _, committed = self.preview(graph)
        self.assertNotEqual(
            {e["candidate_key"]: e["arch_id"] for e in before_apply["entries"]},
            {e["candidate_key"]: e["arch_id"] for e in committed["entries"]})
        self.assertEqual(
            {e["candidate_key"]: e["note_path"]
             for e in before_apply["entries"]},
            {e["candidate_key"]: e["note_path"] for e in committed["entries"]})

    def test_a_changed_only_refresh_rewrites_just_the_changed_note(self):
        graph = self.configured()
        self.cycle(graph)
        before = _snapshot(self.notes_home)
        with open(graph, encoding="utf-8") as handle:
            doc = json.load(handle)
        doc["files"] = [{"path": "src/app.py"}, {"path": "docs/readme.md"}]
        with open(graph, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        _, applied = self.cycle(graph)
        after = _snapshot(self.notes_home)
        changed = [path for path in sorted(set(before) | set(after))
                   if before.get(path) != after.get(path)]
        self.assertIn("projects/%s/Components/root.md" % SLUG, changed)
        self.assertNotIn("projects/%s/Codebase Map.md" % SLUG, changed)


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
