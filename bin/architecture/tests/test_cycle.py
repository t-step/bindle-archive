"""End-to-end projection cycle: preview -> apply -> preview (#374 D5c).

WHY THIS MODULE EXISTS SEPARATELY FROM test_preview AND test_apply. Both of
those exercise one half. `test_preview` builds the chain and writes nothing;
`test_apply` writes, but is handed `identities` and `identity_records`
constructed by hand. Neither ever feeds APPLY'S OWN OUTPUT back into a
second preview -- and that is the only place the identity round trip is
observable. The #185 lesson (a green unit suite over a broken real cycle)
is the reason this exists.

The load-bearing assertion is that the second preview REUSES the identity
the first run committed. Continuity runs entirely through the judgments
log: `matcher.identity_signals` scores a candidate against the signals in
each identity's own records and reads NOTHING from the projection state.
So an allocation record that carries no signals scores zero against every
candidate, the matcher reports `mint`, and the run allocates a SECOND
identity for code that already has one -- which is the outcome #228's
identity rules exist to prevent.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import apply as arch_apply
from architecture import judgments as arch_judgments
from architecture import preview
from architecture import project
from architecture import state

SLUG = "bindle"
BINDING = "repository-binding:" + "0" * 31 + "1"
DECIDED_AT = "2026-07-20T00:00:00Z"


def _snapshot(root):
    seen = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                seen[os.path.relpath(path, root)] = handle.read()
    return seen


class CycleTestCase(unittest.TestCase):

    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)
        self.graph = self._configure()

    def _configure(self):
        project.init_project(self.notes_home, SLUG)
        project.add_binding(self.notes_home, SLUG, "main", binding_id=BINDING)
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
        return path

    def preview(self):
        return preview.build_preview(
            self.notes_home, SLUG, {BINDING: self.graph},
            decided_at=DECIDED_AT)

    def apply_preview(self, out):
        """Apply exactly what preview planned.

        Every input apply re-plans from must be the SAME object preview
        planned from -- records, identities, config, bindings, provider --
        or the re-plan produces a different fingerprint and the run aborts
        as stale_preview instead of writing."""
        config = project.load_config(
            project.config_path(self.notes_home, SLUG))
        return arch_apply.apply(
            self.notes_home, SLUG, out["project_id"], out["records"],
            out["fingerprint"],
            identities=out["identities"],
            identity_records=out["identity_records"],
            config=config,
            bindings={binding_id: dict(info) for binding_id, info
                      in (out["graph"]["bindings"] or {}).items()},
            projected_at=DECIDED_AT)


class FirstApplyTests(CycleTestCase):

    def test_the_first_apply_writes_the_planned_notes(self):
        out = self.preview()
        result = self.apply_preview(out)
        self.assertTrue(result["ok"], result.get("findings"))
        self.assertEqual("applied", result["status"])
        for entry in out["entries"]:
            self.assertTrue(os.path.exists(os.path.join(
                self.notes_home, "projects", SLUG, entry["note_path"])),
                "not written: %r" % (entry["note_path"],))

    def test_the_first_apply_commits_one_identity_per_entry(self):
        out = self.preview()
        self.apply_preview(out)
        log = arch_judgments.load_judgments(
            state.judgments_path(self.notes_home, SLUG), out["project_id"])
        allocations = [r for r in log["records"]
                       if r["kind"] == "identity_allocation"]
        self.assertEqual(len(out["entries"]), len(allocations))


class SecondPreviewTests(CycleTestCase):
    """The round trip. Everything here is about the SECOND run reading what
    the first one committed."""

    def test_the_second_preview_reuses_every_identity(self):
        first = self.preview()
        self.apply_preview(first)
        second = self.preview()
        self.assertTrue(second["ok"], second["findings"])
        outcomes = {entry["candidate_key"]: entry["identity_outcome"]
                    for entry in second["entries"]}
        self.assertEqual(
            {key: "reuse" for key in outcomes},
            outcomes,
            "a committed identity was not continued: %r" % (outcomes,))

    def test_the_second_preview_defers_nothing(self):
        first = self.preview()
        self.apply_preview(first)
        second = self.preview()
        self.assertEqual([], second["deferred"])

    def test_the_second_preview_keeps_every_arch_id(self):
        first = self.preview()
        self.apply_preview(first)
        second = self.preview()
        before = {entry["candidate_key"]: entry["arch_id"]
                  for entry in first["entries"]}
        after = {entry["candidate_key"]: entry["arch_id"]
                 for entry in second["entries"]}
        self.assertEqual(before, after)

    def test_the_second_preview_sees_every_note_as_current(self):
        first = self.preview()
        self.apply_preview(first)
        second = self.preview()
        for entry in second["entries"]:
            self.assertEqual("current", entry["note_state"],
                             "%r" % (entry["candidate_key"],))


class RerunTests(CycleTestCase):
    """AC: a rerun at the same commit writes zero bytes."""

    def test_a_rerun_at_the_same_commit_writes_zero_bytes(self):
        first = self.preview()
        self.apply_preview(first)
        before = _snapshot(self.notes_home)
        second = self.preview()
        self.apply_preview(second)
        self.assertEqual(before, _snapshot(self.notes_home))

    def test_a_rerun_appends_no_second_allocation(self):
        """An identity is allocated once, at its creation event. A rerun
        that appends a second allocation for the same code is the duplicate
        identity #228 forbids -- and it is invisible to a bytes comparison
        of the NOTES alone, because both allocations render the same note."""
        first = self.preview()
        self.apply_preview(first)
        second = self.preview()
        self.apply_preview(second)
        log = arch_judgments.load_judgments(
            state.judgments_path(self.notes_home, SLUG), first["project_id"])
        allocations = [r for r in log["records"]
                       if r["kind"] == "identity_allocation"]
        self.assertEqual(len(first["entries"]), len(allocations))


class ChangedRefreshTests(CycleTestCase):
    """A rerun whose inputs MOVED. This is where a broken identity round
    trip does visible damage: the noop path short-circuits an unchanged
    rerun before it appends anything, so a duplicate identity only reaches
    the log once a run actually writes."""

    def _regraph(self, files, symbols=None):
        with open(self.graph, encoding="utf-8") as handle:
            doc = json.load(handle)
        doc["files"] = files
        if symbols is not None:
            doc["symbols"] = symbols
        with open(self.graph, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)

    def _add_a_file(self):
        """Adds a file WITHOUT moving the component's scoring signals, so
        the note changes while continuity stays high-confidence. A change
        that moves the signals is the routed case below, not this one."""
        self._regraph([{"path": "src/app.py"}, {"path": "docs/readme.md"}])

    def test_a_changed_run_refreshes_rather_than_re_identifying(self):
        first = self.preview()
        self.apply_preview(first)
        self._add_a_file()
        second = self.preview()
        changed = [e for e in second["entries"]
                   if e["candidate_key"] == "component:."][0]
        self.assertEqual("reuse", changed["identity_outcome"])
        self.assertEqual("changed", changed["note_state"])

    def test_a_changed_run_appends_no_second_allocation(self):
        first = self.preview()
        self.apply_preview(first)
        self._add_a_file()
        second = self.preview()
        result = self.apply_preview(second)
        self.assertEqual("applied", result["status"])
        log = arch_judgments.load_judgments(
            state.judgments_path(self.notes_home, SLUG), first["project_id"])
        allocations = [r for r in log["records"]
                       if r["kind"] == "identity_allocation"]
        self.assertEqual(
            len(first["entries"]), len(allocations),
            "a second identity was allocated for code that already had one")

    def test_the_refreshed_note_keeps_its_creation_event_path(self):
        first = self.preview()
        self.apply_preview(first)
        before = {e["candidate_key"]: e["note_path"] for e in first["entries"]}
        self._add_a_file()
        second = self.preview()
        after = {e["candidate_key"]: e["note_path"] for e in second["entries"]}
        self.assertEqual(before, after)

    def test_a_signal_moving_change_is_routed_never_re_minted(self):
        """The documented limitation, asserted so it cannot regress into a
        silent re-identification. When the signals move far enough that
        continuity is only MEDIUM confidence, `matcher` routes the
        candidate to child G rather than collapsing it into a reuse -- and
        a routed candidate is deferred, so it is never re-minted either."""
        first = self.preview()
        self.apply_preview(first)
        self._regraph(
            [{"path": "src/app.py"}, {"path": "src/util.py"}],
            [{"id": "sym-1", "name": "app", "kind": "module",
              "path": "src/app.py"},
             {"id": "sym-2", "name": "util", "kind": "module",
              "path": "src/util.py"}])
        second = self.preview()
        deferred = [d for d in second["deferred"]
                    if d["candidate_key"] == "component:."]
        self.assertEqual(1, len(deferred), second["deferred"])
        self.assertEqual("routed", deferred[0]["outcome"])
        self.assertNotIn("component:.",
                         [e["candidate_key"] for e in second["entries"]])


class CrashedApplyTests(CycleTestCase):
    """The state the unplaceable-reuse question was about: the identity is
    on the log and index.json was never written."""

    def test_an_identity_committed_without_an_index_is_still_placeable(self):
        first = self.preview()
        self.apply_preview(first)
        os.remove(state.index_path(self.notes_home, SLUG))
        second = self.preview()
        self.assertTrue(second["ok"], second["findings"])
        self.assertEqual([], second["deferred"])
        self.assertEqual(
            {e["candidate_key"]: e["note_path"] for e in first["entries"]},
            {e["candidate_key"]: e["note_path"] for e in second["entries"]})

    def test_an_identity_committed_without_an_index_is_reused(self):
        first = self.preview()
        self.apply_preview(first)
        os.remove(state.index_path(self.notes_home, SLUG))
        second = self.preview()
        for entry in second["entries"]:
            self.assertEqual("reuse", entry["identity_outcome"])


if __name__ == "__main__":
    unittest.main()
