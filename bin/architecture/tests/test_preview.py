"""Tests for architecture.preview (issue #374 child D, slice D5b).

This is the first module that runs the projection chain end to end --
graph -> candidates -> matcher -> allocator -> planner -- so these tests
are the first INTEGRATION evidence in the package. Every prior slice
asserted its own link with the next stage's input built by hand, which is
exactly the class of defect (`#185`'s sibling-anchor collision) that only a
real cycle catches.

Two assertions carry disproportionate weight:

1. FINGERPRINT STABILITY across two independent previews of identical
   inputs. Apply re-plans from scratch and aborts on a mismatch, so an
   unstable fingerprint means every confirmation burns as `stale_preview`.
   This is non-trivial because the allocator mints a RANDOM hex on each
   run: the test passes only because `arch_id` enters no fingerprint term
   while the derived slug -- which does, via note_path -> manifest -- is a
   pure function of the candidate name.
2. PREVIEW WRITES ZERO BYTES, asserted by walking the notes home and
   comparing the full path/content map, not by trusting the absence of an
   obvious write call.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import canonical
from architecture import preview
from architecture import project
from architecture import state

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SLUG = "bindle"
BINDING = "repository-binding:" + "0" * 31 + "1"
OTHER_BINDING = "repository-binding:" + "0" * 31 + "2"


def _snapshot(root):
    """Full path -> bytes map, so a write anywhere under the notes home is
    visible, including one to a file a test never named."""
    seen = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                seen[os.path.relpath(path, root)] = handle.read()
    return seen


class PreviewTestCase(unittest.TestCase):

    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)

    def write_graph(self, name=None, binding_id=BINDING, files=None,
                    symbols=None):
        files = files if files is not None else [{"path": "src/app.py"}]
        symbols = symbols if symbols is not None else [
            {"id": "sym-1", "name": "app", "kind": "module",
             "path": "src/app.py"}]
        doc = {
            "schema_version": 1,
            "binding_id": binding_id,
            "source_commit": "a" * 40,
            "provider": {"name": "reference-json", "version": "1.0.0"},
            "capabilities": ["contains"],
            "root": "",
            "coverage": [{"path_prefix": "", "capability": "contains",
                          "status": "observed"}],
            "files": files,
            "symbols": symbols,
            "edges": [],
        }
        path = os.path.join(self.workdir, name or "graph.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        return path

    def configured(self, binding_id=BINDING):
        project.init_project(self.notes_home, SLUG)
        project.add_binding(self.notes_home, SLUG, "main",
                            binding_id=binding_id)
        return self.write_graph(binding_id=binding_id)

    def preview(self, graph_path=None, binding_id=BINDING, **kwargs):
        graphs = ({binding_id: graph_path} if graph_path else {})
        return preview.build_preview(
            self.notes_home, SLUG, graphs,
            decided_at="2026-07-20T00:00:00Z", **kwargs)


class ChainTests(PreviewTestCase):

    def test_preview_produces_a_plan(self):
        out = self.preview(self.configured())
        self.assertTrue(out["ok"], out["findings"])
        self.assertTrue(out["entries"])

    def test_every_entry_has_an_identity(self):
        out = self.preview(self.configured())
        for entry in out["entries"]:
            self.assertTrue(entry["arch_id"],
                            "no arch_id for %r" % (entry["candidate_key"],))

    def test_the_codebase_map_is_always_planned(self):
        out = self.preview(self.configured())
        keys = [entry["candidate_key"] for entry in out["entries"]]
        self.assertIn("codebase-map", keys)

    def test_a_fresh_project_mints_every_identity(self):
        out = self.preview(self.configured())
        for entry in out["entries"]:
            self.assertEqual("mint", entry["identity_outcome"])

    def test_identity_records_are_returned_for_apply_to_commit(self):
        out = self.preview(self.configured())
        self.assertEqual(len(out["entries"]), len(out["identity_records"]))
        for record in out["identity_records"]:
            self.assertEqual("identity_allocation", record["kind"])

    def test_note_state_is_absent_before_anything_is_written(self):
        out = self.preview(self.configured())
        for entry in out["entries"]:
            self.assertEqual("absent", entry["note_state"])

    def test_graph_load_status_is_reported_per_binding(self):
        out = self.preview(self.configured())
        self.assertEqual(
            "loaded", out["graph"]["bindings"][BINDING]["status"])

    def test_a_fingerprint_is_produced(self):
        out = self.preview(self.configured())
        self.assertTrue(out["fingerprint"].startswith("arch-plan:sha256:"))


class FingerprintStabilityTests(PreviewTestCase):

    def test_two_previews_of_identical_inputs_agree(self):
        """The confirmation contract. Non-trivial because each run mints a
        fresh random arch_id -- this passes only because arch_id is not a
        fingerprint term and the slug that IS one is derived, not random."""
        graph = self.configured()
        first = self.preview(graph)
        second = self.preview(graph)
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_the_two_runs_really_did_mint_different_identities(self):
        """Guards the test above from passing vacuously: if allocation were
        somehow deterministic, fingerprint stability would prove nothing
        about which terms feed the digest."""
        graph = self.configured()
        first = self.preview(graph)
        second = self.preview(graph)
        self.assertNotEqual(
            [e["arch_id"] for e in first["entries"]],
            [e["arch_id"] for e in second["entries"]])

    def test_a_changed_graph_changes_the_fingerprint(self):
        graph = self.configured()
        before = self.preview(graph)["fingerprint"]
        moved = self.write_graph(
            name="graph2.json",
            files=[{"path": "src/app.py"}, {"path": "lib/util.py"}],
            symbols=[{"id": "sym-1", "name": "app", "kind": "module",
                      "path": "src/app.py"},
                     {"id": "sym-2", "name": "util", "kind": "module",
                      "path": "lib/util.py"}])
        after = self.preview(moved)["fingerprint"]
        self.assertNotEqual(before, after)


class WritesNothingTests(PreviewTestCase):

    def test_preview_writes_zero_bytes(self):
        graph = self.configured()
        before = _snapshot(self.notes_home)
        self.preview(graph)
        self.assertEqual(before, _snapshot(self.notes_home))

    def test_preview_creates_no_judgments_log(self):
        """The allocator's records are RETURNED for apply to commit, never
        appended here -- #228 forbids writing a judgment because a
        projection merely ran."""
        graph = self.configured()
        self.preview(graph)
        self.assertFalse(os.path.exists(
            state.judgments_path(self.notes_home, SLUG)))


class DeferredOutcomeTests(PreviewTestCase):

    def _log_identity(self, arch_id, source_paths, symbol_names,
                      slug=None, projection_type=None):
        """Append one identity_allocation carrying signals, so the matcher
        has something to score against.

        `slug`/`projection_type` are omitted by default, which is the
        PRE-D5c record shape: those records place nothing and are what the
        unplaceable branch reports."""
        path = state.judgments_path(self.notes_home, SLUG)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cfg = project.load_config(
            project.config_path(self.notes_home, SLUG))
        payload = {"candidate_key": "component:.",
                   "source_paths": sorted(source_paths),
                   "symbol_names": sorted(symbol_names),
                   "neighborhood": []}
        if slug:
            payload["slug"] = slug
        if projection_type:
            payload["projection_type"] = projection_type
        record = canonical.stamp({
            "schema_version": state.SCHEMA_VERSION,
            "kind": "identity_allocation",
            "project_id": cfg["project_id"],
            "decided_at": "2026-07-19T00:00:00Z",
            "arch_id": arch_id,
            "payload": payload,
        })
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _write_index(self, nodes):
        """The post-apply state: index.json records each node's
        creation-event note_path, which is the only place that path is
        stored -- the judgments log and the allocation payload hold
        neither a slug nor a path."""
        path = state.index_path(self.notes_home, SLUG)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cfg = project.load_config(
            project.config_path(self.notes_home, SLUG))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({
                "schema_version": state.SCHEMA_VERSION,
                "projection_schema_version": state.PROJECTION_SCHEMA_VERSION,
                "project_id": cfg["project_id"],
                "nodes": nodes,
            }, handle)

    def test_a_reused_identity_is_not_re_minted(self):
        graph = self.configured()
        first = self.preview(graph)
        component = [e for e in first["entries"]
                     if e["candidate_key"] == "component:."][0]
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        self._log_identity(component["arch_id"], record["source_paths"],
                           record["symbol_names"])
        self._write_index([{"arch_id": component["arch_id"],
                            "note_path": component["note_path"]}])
        second = self.preview(graph)
        reused = [e for e in second["entries"]
                  if e["candidate_key"] == "component:."][0]
        self.assertEqual("reuse", reused["identity_outcome"])
        self.assertEqual(component["arch_id"], reused["arch_id"])

    def test_a_reuse_keeps_the_creation_event_note_path(self):
        """A rename must never recompute the path, so the reused entry
        must carry the path index.json recorded, not one re-derived from
        the candidate's current name."""
        graph = self.configured()
        first = self.preview(graph)
        component = [e for e in first["entries"]
                     if e["candidate_key"] == "component:."][0]
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        self._log_identity(component["arch_id"], record["source_paths"],
                           record["symbol_names"])
        self._write_index([{"arch_id": component["arch_id"],
                            "note_path": "Components/renamed-by-hand.md"}])
        second = self.preview(graph)
        reused = [e for e in second["entries"]
                  if e["candidate_key"] == "component:."][0]
        self.assertEqual("Components/renamed-by-hand.md",
                         reused["note_path"])

    def test_an_allocation_carrying_its_slug_places_the_note_without_an_index(self):
        """Since D5c the allocation payload records the creation-event slug
        and projection type, so the log alone places the note -- the state
        a crash between the identity append and the index write leaves.
        The path is RE-DERIVED through `state.format_note_path`, the same
        function that produced it, not guessed from the current name."""
        graph = self.configured()
        first = self.preview(graph)
        component = [e for e in first["entries"]
                     if e["candidate_key"] == "component:."][0]
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        self._log_identity(component["arch_id"], record["source_paths"],
                           record["symbol_names"],
                           slug="root", projection_type="arch_component")
        # No index written: the crashed-mid-apply state.
        second = self.preview(graph)
        reused = [e for e in second["entries"]
                  if e["candidate_key"] == "component:."][0]
        self.assertEqual("reuse", reused["identity_outcome"])
        self.assertEqual("Components/root.md", reused["note_path"])
        self.assertEqual([], second["deferred"])

    def test_the_index_still_outranks_the_logged_slug(self):
        """The log says where the creation event PUT the note; the index
        says where it IS. A lifecycle event that moved it is recorded only
        in the index, so the index must win."""
        graph = self.configured()
        first = self.preview(graph)
        component = [e for e in first["entries"]
                     if e["candidate_key"] == "component:."][0]
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        self._log_identity(component["arch_id"], record["source_paths"],
                           record["symbol_names"],
                           slug="root", projection_type="arch_component")
        self._write_index([{"arch_id": component["arch_id"],
                            "note_path": "Components/moved-later.md"}])
        second = self.preview(graph)
        reused = [e for e in second["entries"]
                  if e["candidate_key"] == "component:."][0]
        self.assertEqual("Components/moved-later.md", reused["note_path"])

    def test_a_malformed_logged_slug_falls_through_to_deferral(self):
        """The log is authoritative for MEANING, not for legality. A
        hand-edited payload whose slug cannot form a legal note path is
        dropped rather than trusted into `format_note_path`."""
        graph = self.configured()
        first = self.preview(graph)
        component = [e for e in first["entries"]
                     if e["candidate_key"] == "component:."][0]
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        self._log_identity(component["arch_id"], record["source_paths"],
                           record["symbol_names"],
                           slug="Not A Slug",
                           projection_type="arch_component")
        second = self.preview(graph)
        self.assertTrue(second["ok"], second["findings"])
        deferred = [d for d in second["deferred"]
                    if d["candidate_key"] == "component:."]
        self.assertEqual(1, len(deferred))
        self.assertEqual("note_path_unknown", deferred[0]["reason"])

    def test_a_reuse_with_no_recorded_path_is_deferred_not_fatal(self):
        """A PRE-D5c allocation carries neither a slug nor a projection
        type, and apply appends the identity record BEFORE writing the
        index -- so a crash in between leaves the log knowing an identity
        that nothing can place. The candidate is deferred; it must not
        reject the whole plan."""
        graph = self.configured()
        first = self.preview(graph)
        component = [e for e in first["entries"]
                     if e["candidate_key"] == "component:."][0]
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        self._log_identity(component["arch_id"], record["source_paths"],
                           record["symbol_names"])
        # No index written: the crashed-mid-apply state.
        second = self.preview(graph)
        self.assertTrue(second["ok"], second["findings"])
        deferred = [d for d in second["deferred"]
                    if d["candidate_key"] == "component:."]
        self.assertEqual(1, len(deferred))
        self.assertEqual("note_path_unknown", deferred[0]["reason"])
        self.assertIn("E_ARCH_PREVIEW_IDENTITY_UNPLACEABLE",
                      [f["code"] for f in second["findings"]])

    def test_an_unplaceable_reuse_does_not_block_other_candidates(self):
        """The bug this guard fixes: a single unplaceable identity raised
        PlanInputError, which rejected every candidate in the run."""
        graph = self.configured()
        first = self.preview(graph)
        component = [e for e in first["entries"]
                     if e["candidate_key"] == "component:."][0]
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        self._log_identity(component["arch_id"], record["source_paths"],
                           record["symbol_names"])
        second = self.preview(graph)
        self.assertIn("codebase-map",
                      [e["candidate_key"] for e in second["entries"]])

    def test_a_contested_candidate_is_excluded_from_the_plan(self):
        """Two logged identities matching the same candidate equally well
        is a contest. Naming a winner is forbidden, and child G is a
        release out, so the candidate is reported and never projected."""
        graph = self.configured()
        first = self.preview(graph)
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        base = "arch-node:" + first["project_id"] + ":"
        self._log_identity(base + "a" * 32, record["source_paths"],
                           record["symbol_names"])
        self._log_identity(base + "b" * 32, record["source_paths"],
                           record["symbol_names"])
        out = self.preview(graph)
        deferred_keys = [d["candidate_key"] for d in out["deferred"]]
        self.assertIn("component:.", deferred_keys)
        self.assertNotIn("component:.",
                         [e["candidate_key"] for e in out["entries"]])

    def test_a_deferred_candidate_still_reports_why(self):
        graph = self.configured()
        first = self.preview(graph)
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        base = "arch-node:" + first["project_id"] + ":"
        self._log_identity(base + "a" * 32, record["source_paths"],
                           record["symbol_names"])
        self._log_identity(base + "b" * 32, record["source_paths"],
                           record["symbol_names"])
        out = self.preview(graph)
        entry = [d for d in out["deferred"]
                 if d["candidate_key"] == "component:."][0]
        # Exact, not a tuple of acceptable outcomes: a loose assertion here
        # would still pass if the two equally-scoring identities silently
        # collapsed into a routed single-match, which is the failure mode
        # the contest rule exists to prevent.
        self.assertEqual("contested", entry["outcome"])
        self.assertEqual("contested_high", entry["reason"])
        self.assertEqual(2, len(entry["contested_with"]))

    def test_a_deferred_candidate_does_not_get_an_allocation(self):
        """The allocator must not mint for a candidate the plan excludes --
        that would append an identity nobody confirmed."""
        graph = self.configured()
        first = self.preview(graph)
        record = [r for r in first["records"]
                  if r["candidate_key"] == "component:."][0]
        base = "arch-node:" + first["project_id"] + ":"
        self._log_identity(base + "a" * 32, record["source_paths"],
                           record["symbol_names"])
        self._log_identity(base + "b" * 32, record["source_paths"],
                           record["symbol_names"])
        out = self.preview(graph)
        allocated = [r["payload"]["candidate_key"]
                     for r in out["identity_records"]]
        self.assertNotIn("component:.", allocated)


class FailureTests(PreviewTestCase):

    def test_missing_config_is_a_findings_list(self):
        out = self.preview()
        self.assertFalse(out["ok"])
        self.assertEqual(["E_ARCH_PREVIEW_CONFIG_MISSING"],
                         [f["code"] for f in out["findings"]])

    def test_an_unconfigured_binding_is_refused(self):
        project.init_project(self.notes_home, SLUG)
        project.add_binding(self.notes_home, SLUG, "main",
                            binding_id=BINDING)
        graph = self.write_graph(binding_id=OTHER_BINDING)
        out = self.preview(graph, binding_id=OTHER_BINDING)
        self.assertFalse(out["ok"])
        self.assertEqual(["E_ARCH_PREVIEW_BINDING_UNKNOWN"],
                         [f["code"] for f in out["findings"]])

    def test_a_failed_preview_still_has_the_full_shape(self):
        out = self.preview()
        for key in ("ok", "findings", "entries", "fingerprint", "deferred",
                    "manifest", "over_cap", "identities", "records"):
            self.assertIn(key, out)

    def test_a_binding_with_no_document_is_reported_unavailable(self):
        project.init_project(self.notes_home, SLUG)
        project.add_binding(self.notes_home, SLUG, "main",
                            binding_id=BINDING)
        out = self.preview()
        self.assertTrue(out["ok"], out["findings"])
        self.assertEqual("unavailable",
                         out["graph"]["bindings"][BINDING]["status"])


class AddBindingTests(PreviewTestCase):

    def test_binding_id_is_minted_when_omitted(self):
        project.init_project(self.notes_home, SLUG)
        _, binding = project.add_binding(self.notes_home, SLUG, "main")
        self.assertRegex(binding["binding_id"],
                         r"^repository-binding:[0-9a-f]{32}$")

    def test_a_supplied_binding_id_is_kept_verbatim(self):
        """A document carries its own binding_id and loads as
        `deconfigured` with no facts unless the config names that exact
        id, so a mint-only surface could never read a real document."""
        project.init_project(self.notes_home, SLUG)
        _, binding = project.add_binding(self.notes_home, SLUG, "main",
                                         binding_id=BINDING)
        self.assertEqual(BINDING, binding["binding_id"])

    def test_a_duplicate_alias_is_refused(self):
        project.init_project(self.notes_home, SLUG)
        project.add_binding(self.notes_home, SLUG, "main")
        with self.assertRaises(project.ConfigInvalidError):
            project.add_binding(self.notes_home, SLUG, "main")

    def test_a_duplicate_binding_id_is_refused(self):
        """graphset.load_set RAISES on a duplicate binding_id rather than
        silently collapsing two bindings into one loaded document."""
        project.init_project(self.notes_home, SLUG)
        project.add_binding(self.notes_home, SLUG, "one", binding_id=BINDING)
        with self.assertRaises(project.ConfigInvalidError):
            project.add_binding(self.notes_home, SLUG, "two",
                                binding_id=BINDING)

    def test_add_binding_before_init_is_refused(self):
        with self.assertRaises(project.ConfigInvalidError):
            project.add_binding(self.notes_home, SLUG, "main")

    def test_the_added_binding_survives_a_reload(self):
        project.init_project(self.notes_home, SLUG)
        project.add_binding(self.notes_home, SLUG, "main",
                            binding_id=BINDING)
        cfg = project.load_config(
            project.config_path(self.notes_home, SLUG))
        self.assertEqual([{"binding_id": BINDING, "alias": "main"}],
                         cfg["bindings"])
        self.assertEqual([], state.validate_config(cfg))


if __name__ == "__main__":
    unittest.main()
