"""Tests for architecture.loop -- the confirm and apply halves of the
projection loop (#374 slice D5c).

`test_cli` drives these two verbs as real subprocesses and is the
acceptance evidence. This module covers the parts a subprocess test states
poorly: the static confirmation policy's individual triggers, and the
deliberate choice that `requires_confirmation` REPORTS rather than
refuses.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import loop
from architecture import preview as arch_preview
from architecture import project
from architecture import state

SLUG = "bindle"
BINDING = "repository-binding:" + "0" * 31 + "1"
DECIDED_AT = "2026-07-20T00:00:00Z"


class LoopTestCase(unittest.TestCase):

    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)

    def configure(self, **init_kwargs):
        project.init_project(self.notes_home, SLUG, **init_kwargs)
        project.add_binding(self.notes_home, SLUG, "main",
                            binding_id=BINDING)
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
        path = os.path.join(self.workdir, "graph.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        self.graph = path
        return path

    def graphs(self):
        return {BINDING: self.graph}

    def preview(self):
        return arch_preview.build_preview(
            self.notes_home, SLUG, self.graphs(), decided_at=DECIDED_AT)

    def config(self):
        return project.load_config(
            project.config_path(self.notes_home, SLUG))


class DiffSizeTests(LoopTestCase):

    def test_a_first_projection_counts_every_note_as_a_write(self):
        self.configure()
        result = self.preview()
        self.assertEqual(len(result["entries"]), loop.diff_size(result))

    def test_an_applied_projection_counts_zero(self):
        """Counted from `note_state`, decided against current disk -- NOT
        from the plan-level disposition, which reads `mint` on every run
        because preview passes previous=() and would report a full rewrite
        forever."""
        self.configure()
        result = self.preview()
        loop.apply_confirmed(self.notes_home, SLUG, self.graphs(),
                             result["fingerprint"], projected_at=DECIDED_AT)
        self.assertEqual(0, loop.diff_size(self.preview()))


class ConfirmationPolicyTests(LoopTestCase):

    def test_a_small_plan_triggers_nothing(self):
        self.configure()
        self.assertEqual(
            [], loop.confirmation_reasons(self.preview(), self.config()))

    def test_the_diff_size_limit_triggers(self):
        self.configure(diff_size_confirmation_limit=1)
        reasons = loop.confirmation_reasons(self.preview(), self.config())
        self.assertEqual(["diff_size_over_limit"],
                         [r["reason"] for r in reasons])

    def test_a_limit_exactly_equal_to_the_diff_size_does_not_trigger(self):
        """The limit is the largest ACCEPTABLE size, not the first
        rejected one. An off-by-one here would demand confirmation for
        every plan that exactly meets its own configured budget."""
        self.configure()
        size = loop.diff_size(self.preview())
        cfg = dict(self.config(), diff_size_confirmation_limit=size)
        self.assertEqual([], loop.confirmation_reasons(self.preview(), cfg))

    def test_an_over_cap_entry_triggers(self):
        """The cap binds CREATION, so an over-cap candidate is reported
        rather than created -- a plan the operator should see before
        approving, not one that silently drops components.

        Driven from a synthetic plan rather than a graph: this package's
        clustering yields a single root component for every flat fixture,
        so no interchange document these tests can write produces a second
        component to push over a cap. `test_planner` covers the ranking
        that SETS `over_cap`; this covers the policy that reports it."""
        self.configure()
        result = dict(self.preview(), over_cap=("component:weak",))
        self.assertIn("over_cap",
                      [r["reason"] for r in
                       loop.confirmation_reasons(result, self.config())])

    def test_a_deferred_candidate_triggers(self):
        """A deferred candidate will NOT be projected. Applying without
        surfacing that is applying a plan the operator misread."""
        self.configure()
        first = self.preview()
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        self._log_legacy_identity(
            first["project_id"],
            [e for e in first["entries"]
             if e["candidate_key"] == "component:."][0]["arch_id"],
            record["source_paths"], record["symbol_names"])
        result = self.preview()
        self.assertTrue(result["deferred"], "fixture deferred nothing")
        self.assertIn("deferred_candidates",
                      [r["reason"] for r in
                       loop.confirmation_reasons(result, self.config())])

    def test_a_conflicting_note_triggers(self):
        """A note whose generated region cannot be safely replaced is left
        alone by apply. The operator has to know that before approving, or
        the run silently does less than the plan appears to say."""
        self.configure()
        path = os.path.join(self.notes_home, "projects", SLUG,
                            "Components", "root.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("hand-written, no generated region\n")
        result = self.preview()
        self.assertIn(
            "conflict",
            [e["note_state"] for e in result["entries"]],
            "fixture produced no conflict")
        self.assertIn("note_conflict",
                      [r["reason"] for r in
                       loop.confirmation_reasons(result, self.config())])

    def _log_legacy_identity(self, project_id, arch_id, source_paths,
                             symbol_names):
        """Append a PRE-D5c allocation: signals but no slug, so the matcher
        continues the identity while nothing can place its note."""
        from architecture import canonical
        path = state.judgments_path(self.notes_home, SLUG)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        record = canonical.stamp({
            "schema_version": state.SCHEMA_VERSION,
            "kind": "identity_allocation",
            "project_id": project_id,
            "decided_at": "2026-07-19T00:00:00Z",
            "arch_id": arch_id,
            "payload": {"candidate_key": "component:.",
                        "source_paths": sorted(source_paths),
                        "symbol_names": sorted(symbol_names),
                        "neighborhood": []},
        })
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def test_a_missing_limit_triggers_nothing(self):
        """`diff_size_confirmation_limit` is required by the config schema,
        but `confirmation_reasons` is handed whatever config the caller
        loaded -- a hand-edited one without the key must not be read as a
        limit of zero, which would demand confirmation for every plan."""
        self.configure()
        cfg = {k: v for k, v in self.config().items()
               if k != "diff_size_confirmation_limit"}
        self.assertEqual([], loop.confirmation_reasons(self.preview(), cfg))


class ConfirmTests(LoopTestCase):

    def test_a_current_token_confirms(self):
        self.configure()
        result = self.preview()
        out = loop.confirm(self.notes_home, SLUG, self.graphs(),
                           result["fingerprint"], decided_at=DECIDED_AT)
        self.assertTrue(out["confirmed"])

    def test_a_stale_token_does_not_confirm(self):
        self.configure()
        out = loop.confirm(self.notes_home, SLUG, self.graphs(),
                           "arch-plan:sha256:" + "0" * 64,
                           decided_at=DECIDED_AT)
        self.assertFalse(out["confirmed"])
        self.assertIn(loop.E_CONFIRM_STALE_TOKEN,
                      [f["code"] for f in out["findings"]])

    def test_confirm_reports_the_token_it_was_given(self):
        """So a JSON consumer can tell the two fingerprints apart without
        having to remember what it passed in."""
        self.configure()
        out = loop.confirm(self.notes_home, SLUG, self.graphs(), "nope")
        self.assertEqual("nope", out["expected_fingerprint"])

    def test_requiring_confirmation_still_confirms(self):
        """The policy REPORTS. A veto in a read-only verb would leave a
        large-but-correct refresh with no way to be approved."""
        self.configure(diff_size_confirmation_limit=1)
        result = self.preview()
        out = loop.confirm(self.notes_home, SLUG, self.graphs(),
                           result["fingerprint"], decided_at=DECIDED_AT)
        self.assertTrue(out["confirmed"])
        self.assertTrue(out["requires_confirmation"])

    def test_confirm_without_a_plan_reports_no_plan(self):
        out = loop.confirm(self.notes_home, SLUG, {}, "anything")
        self.assertFalse(out["confirmed"])
        self.assertIn(loop.E_CONFIRM_NO_PLAN,
                      [f["code"] for f in out["findings"]])

    def test_confirm_writes_nothing(self):
        self.configure()
        result = self.preview()
        before = _snapshot(self.notes_home)
        loop.confirm(self.notes_home, SLUG, self.graphs(),
                     result["fingerprint"], decided_at=DECIDED_AT)
        self.assertEqual(before, _snapshot(self.notes_home))


class ApplyConfirmedTests(LoopTestCase):

    def test_a_plan_that_cannot_be_built_writes_nothing(self):
        before = _snapshot(self.notes_home)
        out = loop.apply_confirmed(self.notes_home, SLUG, {}, "anything")
        self.assertFalse(out["ok"])
        self.assertEqual("rejected", out["status"])
        self.assertEqual(before, _snapshot(self.notes_home))

    def test_a_stale_token_is_refused_by_apply_not_by_this_module(self):
        """The comparison belongs under the project lock inside
        `apply.apply`. A pre-check here would be a second, racier copy."""
        self.configure()
        out = loop.apply_confirmed(self.notes_home, SLUG, self.graphs(),
                                   "arch-plan:sha256:" + "0" * 64,
                                   projected_at=DECIDED_AT)
        self.assertEqual("stale_preview", out["status"])
        self.assertFalse(os.path.exists(
            state.index_path(self.notes_home, SLUG)))

    def test_the_applied_result_carries_the_preview_it_wrote(self):
        self.configure()
        result = self.preview()
        out = loop.apply_confirmed(self.notes_home, SLUG, self.graphs(),
                                   result["fingerprint"],
                                   projected_at=DECIDED_AT)
        self.assertEqual("applied", out["status"])
        self.assertEqual(result["fingerprint"], out["preview"]["fingerprint"])


def _snapshot(root):
    seen = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                seen[os.path.relpath(path, root)] = handle.read()
    return seen


if __name__ == "__main__":
    unittest.main()
