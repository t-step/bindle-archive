"""Tests for architecture.apply (issue #230 child D, slice D4).

Scope note: this slice is the WRITE orchestrator -- the stale_preview abort,
the apply-state ledger, resume by re-planning, and `orphaned_by_resume`
classification. It does NOT decide identity: `identities` and the
`identity_allocation` records for mints arrive from the caller, because
nothing in the kit allocates a fresh arch-node hex today
(`ids.format_arch_node_id` has no caller). What IS asserted here is that
whatever identity records the caller supplies are appended to
judgments.jsonl BEFORE the first note byte, which is the guarantee #228
froze and the one a crash depends on.

Two acceptance bullets are deliberately NOT claimed: the index REBUILD from
judgments plus a live provider (PT21's carried-forward loss detection needs
a provider this slice never talks to), and PT16's capability-toggle
monotonicity (needs C's clustering driven end to end). This module writes
index.json; it does not rebuild it.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import apply as arch_apply
from architecture import candidates
from architecture import notes as arch_notes
from architecture import planner
from architecture import render
from architecture import state
from context_graph import config as ctx_config

PROJECT_ID = "project:" + "a" * 32
SLUG = "bindle"
BINDING_ID = "repository-binding:" + "d" * 32
# Distinguishes "the caller passed no fingerprint" from "the caller passed
# None deliberately" -- the second is the unconfirmed-apply case under test.
_UNSET = object()

MAP_ARCH_ID = "arch-node:%s:%s" % (PROJECT_ID, "1" * 32)
AUTH_ARCH_ID = "arch-node:%s:%s" % (PROJECT_ID, "2" * 32)


def _metric(band, value):
    return {"band": band, "value": value}


def _component(key, name, blast="high", member_count=3):
    return {
        "candidate_key": key,
        "projection_type": "arch_component",
        "name": name,
        "source_paths": ["src/%s" % (name,)],
        "symbol_names": [],
        "member_count": member_count,
        "entry_points": [],
        "neighborhood": [],
        "bindings": [BINDING_ID],
        "metrics": {
            "blast_radius": _metric(blast, 40),
            "fan_in": _metric("medium", 12),
            "fan_out": _metric("low", 2),
        },
    }


def _map_record(member_count=1):
    return {
        "candidate_key": candidates.CODEBASE_MAP_KEY,
        "projection_type": "arch_codebase_map",
        "name": "Codebase Map",
        "source_paths": ["."],
        "symbol_names": [],
        "member_count": member_count,
        "entry_points": [],
        "neighborhood": [],
        "bindings": [BINDING_ID],
        "metrics": {},
    }


def _config():
    return {
        "schema_version": 1,
        "projection_schema_version": 1,
        "project_id": PROJECT_ID,
        "project_slug": SLUG,
        "bindings": [{"binding_id": BINDING_ID, "alias": "bindle"}],
        "caps": {"max_nodes": 40, "over_cap_behavior": "report"},
        "thresholds": {"high": 0.9, "low": 0.4},
        "diff_size_confirmation_limit": 20,
    }


def _identity_record(arch_id, candidate_key):
    """The creation event for one minted identity, as the caller supplies
    it. `record_id` and the envelope are stamped by `append_judgment`."""
    return {
        "schema_version": 1,
        "kind": "identity_allocation",
        "project_id": PROJECT_ID,
        "decided_at": "2026-07-20T00:00:00Z",
        "arch_id": arch_id,
        "payload": {"candidate_key": candidate_key},
    }


class _ApplyCase(unittest.TestCase):
    """Filesystem fixture: a real notes home, a real project dir, real
    bytes. The defects this slice can ship are byte-level and
    ordering-level, so a mocked filesystem would test the mock."""

    maxDiff = None

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="bindle-arch-apply-")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.project_dir = ctx_config.project_dir(self.home, SLUG)
        os.makedirs(state.architecture_dir(self.home, SLUG), exist_ok=True)
        self.records = [_map_record(), _component("component:auth", "auth")]
        self.identities = {
            candidates.CODEBASE_MAP_KEY: {"arch_id": MAP_ARCH_ID,
                                          "slug": "codebase-map"},
            "component:auth": {"arch_id": AUTH_ARCH_ID, "slug": "auth"},
        }

    # -- helpers ---------------------------------------------------------

    def _fingerprint(self, records=None, config=None, previous=()):
        """The token preview would have printed for these inputs.

        `previous` is threaded through deliberately: the digest's manifest
        term is what this run would WRITE, which depends on what the last
        run already knows. A preview computed against different `previous`
        is a preview of a different plan, and apply is right to abort on it.
        """
        plan = planner.plan(
            records if records is not None else self.records,
            previous=previous,
            config=config if config is not None else _config(),
            identities=self.identities, notes_root=self.project_dir,
            bindings={BINDING_ID: {"source_commit": "e" * 40}},
            provider={"name": "reference", "version": "1.0.0"})
        return plan["fingerprint"]

    def _apply(self, records=None, fingerprint=_UNSET, identity_records=None,
               previous=(), config=None, projected_at="2026-07-20T00:00:00Z"):
        records = self.records if records is None else records
        return arch_apply.apply(
            self.home, SLUG, PROJECT_ID, records,
            self._fingerprint(records=records, config=config,
                              previous=previous)
            if fingerprint is _UNSET else fingerprint,
            identities=self.identities,
            identity_records=(self._all_identity_records()
                              if identity_records is None else identity_records),
            previous=previous,
            config=config if config is not None else _config(),
            bindings={BINDING_ID: {"source_commit": "e" * 40}},
            provider={"name": "reference", "version": "1.0.0"},
            projected_at=projected_at)

    def _all_identity_records(self):
        return [_identity_record(MAP_ARCH_ID, candidates.CODEBASE_MAP_KEY),
                _identity_record(AUTH_ARCH_ID, "component:auth")]

    def _note_path(self, relative):
        return os.path.join(self.project_dir, relative)

    def _read(self, relative):
        with open(self._note_path(relative), "r", encoding="utf-8") as handle:
            return handle.read()

    def _write(self, relative, text):
        path = self._note_path(relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def _apply_state(self):
        path = state.apply_state_path(self.home, SLUG)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _index(self):
        path = state.index_path(self.home, SLUG)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _judgments(self):
        path = state.judgments_path(self.home, SLUG)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def _mtimes(self):
        seen = {}
        for root, _dirs, files in os.walk(self.project_dir):
            for name in files:
                full = os.path.join(root, name)
                seen[full] = os.stat(full).st_mtime_ns
        return seen


class FirstProjection(_ApplyCase):
    """A first-ever projection against an EMPTY judgments.jsonl must produce
    notes. Without this branch the MVP creates nothing at all."""

    def test_notes_are_created(self):
        result = self._apply()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "applied")
        self.assertTrue(os.path.exists(self._note_path("Codebase Map.md")))
        self.assertTrue(os.path.exists(self._note_path("Components/auth.md")))

    def test_created_notes_carry_their_identity_in_frontmatter(self):
        self._apply()
        self.assertIn("arch_id: %s" % (AUTH_ARCH_ID,),
                      self._read("Components/auth.md"))

    def test_no_observed_provenance_inside_the_generated_region(self):
        """AC10 / PT8 / PT31: a source commit or a timestamp inside the
        byte-compared region turns one README commit into a rewrite of all
        N notes."""
        text = self._read("Components/auth.md") if self._apply() else None
        region = text[text.index(render.BEGIN):text.index(render.END)]
        for leak in ("e" * 40, "2026-07-20T00:00:00Z", "1.0.0", BINDING_ID):
            self.assertNotIn(leak, region)

    def test_the_index_records_the_projection(self):
        self._apply()
        index = self._index()
        self.assertEqual(state.validate_index(index), [])
        self.assertEqual(
            sorted(node["arch_id"] for node in index["nodes"]),
            sorted([MAP_ARCH_ID, AUTH_ARCH_ID]))

    def test_apply_state_is_cleared_on_success(self):
        """Cleared means REMOVED. The file's existence is then exactly the
        signal `resume` reads: an apply that did not finish."""
        self._apply()
        self.assertIsNone(self._apply_state())


class IdentityOrdering(_ApplyCase):
    """PT20. The identity commit precedes the first note byte, so a crash
    is always recoverable forward -- the identity exists and a fresh re-plan
    re-renders it. The other ordering forces recovery to read arch_id back
    out of apply-state or the note, which #228 forbids."""

    def test_identity_records_are_appended_before_any_note(self):
        seen = {}
        real_write = arch_apply.atomic_io.write_atomic

        def _spy(path, data):
            seen.setdefault(os.path.basename(path),
                            len(self._judgments()))
            return real_write(path, data)

        arch_apply.atomic_io.write_atomic = _spy
        self.addCleanup(setattr, arch_apply.atomic_io, "write_atomic",
                        real_write)
        self._apply()
        # By the time ANY file was written atomically, both identity
        # records were already durable in judgments.jsonl.
        self.assertTrue(seen)
        for basename, judgment_count in seen.items():
            self.assertEqual(judgment_count, 2,
                             "%s was written with %d identity record(s) on "
                             "disk" % (basename, judgment_count))

    def test_a_failed_identity_append_writes_nothing(self):
        result = self._apply(identity_records=[{"kind": "identity_allocation"}])
        self.assertFalse(result["ok"])
        self.assertFalse(os.path.exists(self._note_path("Components/auth.md")))
        self.assertIsNone(self._apply_state())


class ZeroWriteRerun(_ApplyCase):
    """A rerun at the same commit writes zero bytes: no apply-state, no
    timestamp-only writes anywhere."""

    def setUp(self):
        super().setUp()
        self._apply()

    def test_rerun_writes_nothing_at_all(self):
        before = self._mtimes()
        result = self._apply(previous=self.records)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "noop")
        self.assertEqual(self._mtimes(), before)

    def test_rerun_creates_no_apply_state(self):
        self._apply(previous=self.records)
        self.assertIsNone(self._apply_state())

    def test_a_commit_that_changes_no_architecture_rewrites_no_note(self):
        """Same candidates, a moved source commit and a new provider
        version. Observed provenance changed; architecture did not."""
        before = self._mtimes()
        result = arch_apply.apply(
            self.home, SLUG, PROJECT_ID, self.records,
            planner.plan(self.records, previous=self.records, config=_config(),
                         identities=self.identities,
                         notes_root=self.project_dir,
                         bindings={BINDING_ID: {"source_commit": "f" * 40}},
                         provider={"name": "reference", "version": "2.0.0"}
                         )["fingerprint"],
            identities=self.identities,
            identity_records=self._all_identity_records(),
            previous=self.records, config=_config(),
            bindings={BINDING_ID: {"source_commit": "f" * 40}},
            provider={"name": "reference", "version": "2.0.0"},
            projected_at="2026-07-21T00:00:00Z")
        self.assertTrue(result["ok"])
        self.assertEqual(self._mtimes(), before)


class ChangedOnlyRefresh(_ApplyCase):
    def setUp(self):
        super().setUp()
        self._apply()

    def test_only_the_affected_note_is_rewritten(self):
        before = self._mtimes()
        changed = [_map_record(), _component("component:auth", "auth",
                                             member_count=9)]
        result = self._apply(records=changed, previous=self.records)
        self.assertTrue(result["ok"])
        after = self._mtimes()
        auth = self._note_path("Components/auth.md")
        self.assertNotEqual(after[auth], before[auth])
        self.assertEqual(after[self._note_path("Codebase Map.md")],
                         before[self._note_path("Codebase Map.md")])

    def test_user_prose_survives_byte_identically(self):
        path = "Components/auth.md"
        text = self._read(path)
        edited = text + "\nmy own paragraph, do not touch\n"
        self._write(path, edited)
        changed = [_map_record(), _component("component:auth", "auth",
                                             member_count=9)]
        self._apply(records=changed, previous=self.records)
        self.assertTrue(self._read(path).endswith(
            "\nmy own paragraph, do not touch\n"))


class StalePreview(_ApplyCase):
    """A confirmation binds the plan it was given for. Without the abort, a
    git pull between preview and apply writes a plan the user never saw and
    mints identities they never reviewed."""

    def test_changed_inputs_abort_as_stale_preview(self):
        confirmed = self._fingerprint()
        moved = [_map_record(), _component("component:auth", "auth",
                                           member_count=99)]
        result = self._apply(records=moved, fingerprint=confirmed)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "stale_preview")

    def test_a_stale_preview_writes_nothing(self):
        confirmed = self._fingerprint()
        moved = [_map_record(), _component("component:auth", "auth",
                                           member_count=99)]
        self._apply(records=moved, fingerprint=confirmed)
        self.assertFalse(os.path.exists(self._note_path("Components/auth.md")))
        self.assertIsNone(self._apply_state())
        self.assertEqual(self._judgments(), [])

    def test_the_abort_reports_both_fingerprints(self):
        confirmed = self._fingerprint()
        moved = [_map_record(), _component("component:auth", "auth",
                                           member_count=99)]
        result = self._apply(records=moved, fingerprint=confirmed)
        self.assertEqual(result["confirmed_fingerprint"], confirmed)
        self.assertNotEqual(result["current_fingerprint"], confirmed)

    def test_an_unconfirmed_apply_is_refused(self):
        result = self._apply(fingerprint=None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unconfirmed")
        self.assertFalse(os.path.exists(self._note_path("Components/auth.md")))


class ApplyStateLedger(_ApplyCase):
    """apply-state.json is interrupted-apply recovery metadata ONLY (FC-5).
    It is created only for a non-empty changed set, after the manifest is
    validated and before the first write."""

    def test_the_ledger_validates_while_the_apply_is_in_flight(self):
        captured = []
        real_write = arch_apply.atomic_io.write_json_atomic

        def _spy(path, obj):
            if os.path.basename(path) == state.APPLY_STATE_FILENAME:
                captured.append(json.loads(json.dumps(obj)))
            return real_write(path, obj)

        arch_apply.atomic_io.write_json_atomic = _spy
        self.addCleanup(setattr, arch_apply.atomic_io, "write_json_atomic",
                        real_write)
        self._apply()
        self.assertTrue(captured)
        for document in captured:
            self.assertEqual(state.validate_apply_state(document), [],
                             "in-flight apply-state did not validate")
        self.assertEqual(captured[0]["status"], "in_progress")
        self.assertEqual([write["state"] for write in captured[0]["writes"]],
                         ["pending"] * len(captured[0]["writes"]))

    def test_the_ledger_records_before_and_after_hashes(self):
        captured = []
        real_write = arch_apply.atomic_io.write_json_atomic

        def _spy(path, obj):
            if os.path.basename(path) == state.APPLY_STATE_FILENAME:
                captured.append(json.loads(json.dumps(obj)))
            return real_write(path, obj)

        arch_apply.atomic_io.write_json_atomic = _spy
        self.addCleanup(setattr, arch_apply.atomic_io, "write_json_atomic",
                        real_write)
        self._apply()
        first = captured[0]
        for write in first["writes"]:
            # Nothing existed before a first-ever projection.
            self.assertIsNone(write["before_hash"])
            self.assertTrue(write["after_hash"].startswith("sha256:"))

    def test_write_order_is_dense_and_ascending(self):
        captured = []
        real_write = arch_apply.atomic_io.write_json_atomic

        def _spy(path, obj):
            if os.path.basename(path) == state.APPLY_STATE_FILENAME:
                captured.append(json.loads(json.dumps(obj)))
            return real_write(path, obj)

        arch_apply.atomic_io.write_json_atomic = _spy
        self.addCleanup(setattr, arch_apply.atomic_io, "write_json_atomic",
                        real_write)
        self._apply()
        orders = [write["order"] for write in captured[0]["writes"]]
        self.assertEqual(orders, list(range(len(orders))))


class Conflicts(_ApplyCase):
    """A note this projection may not rewrite is reported, not overwritten
    -- and it does not take the rest of the plan down with it."""

    def test_a_markerless_note_is_left_alone_and_reported(self):
        hand_written = "# auth\n\nI wrote this by hand.\n"
        self._write("Components/auth.md", hand_written)
        result = self._apply()
        self.assertEqual(self._read("Components/auth.md"), hand_written)
        codes = [conflict["code"] for conflict in result["conflicts"]]
        self.assertIn(arch_notes.CONFLICT_UNMANAGED, codes)

    def test_the_rest_of_the_plan_still_applies(self):
        self._write("Components/auth.md", "# auth\n\nhand written\n")
        self._apply()
        self.assertTrue(os.path.exists(self._note_path("Codebase Map.md")))

    def test_a_conflicted_note_is_not_claimed_in_the_index(self):
        """The index says which notes this projection stands behind. A node
        for a file we refused to write would claim authority over
        hand-authored bytes and make the next run's diff meaningless."""
        self._write("Components/auth.md", "# auth\n\nhand written\n")
        self._apply()
        paths = [node["note_path"] for node in self._index()["nodes"]]
        self.assertNotIn("Components/auth.md", paths)
        self.assertIn("Codebase Map.md", paths)


class ContainmentRejection(_ApplyCase):
    """A planned path escaping the notes home rejects the plan WHOLE."""

    def test_an_escaping_path_writes_nothing(self):
        self.identities["component:auth"] = {
            "arch_id": AUTH_ARCH_ID, "slug": "auth",
            "note_path": "../../escape.md"}
        result = self._apply(fingerprint="arch-plan:sha256:" + "0" * 64)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(os.path.exists(self._note_path("Codebase Map.md")))
        self.assertEqual(self._judgments(), [])


class Resume(_ApplyCase):
    """An interrupted apply is detected and safely resumed by RE-PLANNING
    against current inputs and disk -- never by replaying stored bytes."""

    def _interrupt(self):
        """Leave the fixture in the state a crash mid-apply leaves: one note
        written, a retained apply-state naming both, identities committed."""
        self._apply()
        os.remove(self._note_path("Codebase Map.md"))
        retained = {
            "schema_version": 1,
            "project_id": PROJECT_ID,
            "status": "in_progress",
            "started_at": "2026-07-20T00:00:00Z",
            "writes": [
                {"order": 0, "path": "Codebase Map.md", "before_hash": None,
                 "after_hash": "sha256:" + "c" * 64, "state": "pending"},
                {"order": 1, "path": "Components/auth.md",
                 "before_hash": None, "after_hash": "sha256:" + "d" * 64,
                 "state": "written"},
            ],
        }
        arch_apply.atomic_io.write_json_atomic(
            state.apply_state_path(self.home, SLUG), retained)

    def test_a_retained_apply_state_is_detected(self):
        self._interrupt()
        result = self._apply()
        self.assertTrue(result["resumed"])

    def test_resume_completes_the_missing_note(self):
        self._interrupt()
        self._apply()
        self.assertTrue(os.path.exists(self._note_path("Codebase Map.md")))

    def test_resume_does_not_duplicate_the_written_note(self):
        self._interrupt()
        self._apply()
        components = os.listdir(os.path.join(self.project_dir, "Components"))
        self.assertEqual(components, ["auth.md"])

    def test_resume_never_replays_stored_bytes(self):
        """The retained ledger's after_hash is a lie here -- it names bytes
        that were never on disk. A resume that replayed the ledger would
        have to produce them; one that re-plans ignores them entirely."""
        self._interrupt()
        self._apply()
        text = self._read("Codebase Map.md")
        self.assertIn(render.BEGIN, text)
        self.assertNotIn("c" * 64, text)

    def test_a_hand_edit_made_during_the_interruption_survives(self):
        """The bullet that makes replay unsafe: the user edited the note
        between the crash and the resume, so the ledger's before_hash no
        longer describes disk."""
        self._interrupt()
        path = "Components/auth.md"
        self._write(path, self._read(path) + "\nedited mid-crash\n")
        self._apply()
        self.assertTrue(self._read(path).endswith("\nedited mid-crash\n"))

    def test_a_note_missing_from_disk_is_rewritten_even_when_the_plan_says_noop(self):
        """The case that makes "decide EVERY entry against disk" load-
        bearing. The candidate's reading has not moved, so the plan calls
        it a no-op -- but the crash removed its note. Deciding only the
        non-no-op entries leaves that note missing forever, and every other
        resume test still passes because they re-plan from scratch."""
        self._apply()
        os.remove(self._note_path("Codebase Map.md"))
        result = self._apply(previous=self.records)
        self.assertTrue(result["ok"])
        self.assertTrue(os.path.exists(self._note_path("Codebase Map.md")))

    def test_no_orphan_when_every_ledger_path_is_still_planned(self):
        """A ledger path the fresh plan still contains is work to finish,
        not an orphan. Reporting it would tell the operator the projection
        disowned a note it is about to rewrite."""
        self._interrupt()
        result = self._apply()
        self.assertEqual(result["orphans"], [])

    def test_two_candidates_cannot_claim_one_note_path(self):
        """The ledger validation is not decoration: two identities carrying
        the same `note_path` would plan two writes to one file, and which
        one survived would depend on write order."""
        self.identities["component:auth"]["note_path"] = "Codebase Map.md"
        result = self._apply()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "rejected")
        self.assertIn("E_ARCH_APPLY_STATE_DUPLICATE_PATH",
                      [finding["code"] for finding in result["findings"]])

    def test_apply_state_is_cleared_after_a_resume(self):
        self._interrupt()
        self._apply()
        self.assertIsNone(self._apply_state())

    def test_a_retained_ledger_whose_replan_is_a_noop_is_simply_cleared(self):
        self._apply()
        arch_apply.atomic_io.write_json_atomic(
            state.apply_state_path(self.home, SLUG),
            {"schema_version": 1, "project_id": PROJECT_ID,
             "status": "in_progress", "started_at": "2026-07-20T00:00:00Z",
             "writes": [{"order": 0, "path": "Components/auth.md",
                         "before_hash": None,
                         "after_hash": "sha256:" + "d" * 64,
                         "state": "written"}]})
        result = self._apply(previous=self.records)
        self.assertTrue(result["ok"])
        self.assertIsNone(self._apply_state())


class OrphanedByResume(_ApplyCase):
    """A note the crashed run wrote that the fresh re-plan does not contain.
    D may not delete it (never-auto-delete) and may not stale it (G's AC16),
    so classification is the honest MVP outcome: mark it partial, flag it,
    leave its bytes alone, report it."""

    def _orphan(self):
        """Interrupt an apply that wrote a note for a candidate the next
        run's inputs no longer contain."""
        self._apply()
        orphan_id = "arch-node:%s:%s" % (PROJECT_ID, "3" * 32)
        self.identities["component:legacy"] = {"arch_id": orphan_id,
                                               "slug": "legacy"}
        records = self.records + [_component("component:legacy", "legacy")]
        self._apply(records=records, previous=self.records,
                    identity_records=[_identity_record(orphan_id,
                                                       "component:legacy")])
        del self.identities["component:legacy"]
        arch_apply.atomic_io.write_json_atomic(
            state.apply_state_path(self.home, SLUG),
            {"schema_version": 1, "project_id": PROJECT_ID,
             "status": "in_progress", "started_at": "2026-07-20T00:00:00Z",
             "writes": [{"order": 0, "path": "Components/legacy.md",
                         "before_hash": None,
                         "after_hash": "sha256:" + "e" * 64,
                         "state": "written"}]})
        return orphan_id

    def test_the_orphan_is_reported(self):
        self._orphan()
        result = self._apply(previous=self.records)
        self.assertEqual([orphan["note_path"] for orphan in result["orphans"]],
                         ["Components/legacy.md"])

    def test_the_orphans_bytes_are_untouched(self):
        self._orphan()
        before = self._read("Components/legacy.md")
        self._apply(previous=self.records)
        self.assertEqual(self._read("Components/legacy.md"), before)

    def test_the_orphan_is_not_deleted(self):
        self._orphan()
        self._apply(previous=self.records)
        self.assertTrue(os.path.exists(self._note_path("Components/legacy.md")))

    def test_the_orphan_is_classified_in_the_index(self):
        orphan_id = self._orphan()
        self._apply(previous=self.records)
        index = self._index()
        self.assertEqual(state.validate_index(index), [])
        node = [n for n in index["nodes"] if n["arch_id"] == orphan_id][0]
        self.assertEqual(node["projection_status"], "partial")
        self.assertTrue(node["orphaned_by_resume"])

    def test_the_orphan_is_not_staled(self):
        """G's AC16 owns `stale`. D marking it stale here would take a
        decision that is not D's and that G could not distinguish from its
        own."""
        orphan_id = self._orphan()
        self._apply(previous=self.records)
        node = [n for n in self._index()["nodes"]
                if n["arch_id"] == orphan_id][0]
        self.assertNotEqual(node["projection_status"], "stale")


class PredictedSurvivors(_ApplyCase):
    """Four guarantees whose mutants a mutation pass predicted would
    survive the tests above. Written before the mutants were run, per the
    method this epic settled: a test added AFTER watching a mutant survive
    tends to assert the mutation rather than the guarantee."""

    def test_a_ledger_path_that_was_never_written_is_not_an_orphan(self):
        """The crashed run recorded the intent and died before the write.
        Reporting it would send a reader looking for a file that has never
        existed -- and `orphaned_by_resume` is a claim about BYTES."""
        self._apply()
        arch_apply.atomic_io.write_json_atomic(
            state.apply_state_path(self.home, SLUG),
            {"schema_version": 1, "project_id": PROJECT_ID,
             "status": "in_progress", "started_at": "2026-07-20T00:00:00Z",
             "writes": [{"order": 0, "path": "Components/never-written.md",
                         "before_hash": None,
                         "after_hash": "sha256:" + "f" * 64,
                         "state": "pending"}]})
        result = self._apply(previous=self.records)
        self.assertEqual(result["orphans"], [])

    def test_before_hash_describes_the_bytes_on_disk(self):
        """A `before_hash` computed from the PLANNED bytes instead of the
        existing file would compare equal to `after_hash` and make the
        ledger useless for telling a completed write from a pending one."""
        self._apply()
        with open(self._note_path("Components/auth.md"), "rb") as handle:
            existing = handle.read()
        captured = []
        real_write = arch_apply.atomic_io.write_json_atomic

        def _spy(path, obj):
            if os.path.basename(path) == state.APPLY_STATE_FILENAME:
                captured.append(json.loads(json.dumps(obj)))
            return real_write(path, obj)

        arch_apply.atomic_io.write_json_atomic = _spy
        self.addCleanup(setattr, arch_apply.atomic_io, "write_json_atomic",
                        real_write)
        changed = [_map_record(), _component("component:auth", "auth",
                                             member_count=9)]
        self._apply(records=changed, previous=self.records)
        write = [w for w in captured[0]["writes"]
                 if w["path"] == "Components/auth.md"][0]
        self.assertEqual(
            write["before_hash"],
            "sha256:" + hashlib.sha256(existing).hexdigest())
        self.assertNotEqual(write["before_hash"], write["after_hash"])

    def test_an_identity_is_allocated_exactly_once(self):
        """Allocation is a creation event. Re-appending it on every run
        would put two `identity_allocation` records on the log for one
        identity, and the log is the sole authority for identity."""
        self._apply()
        changed = [_map_record(), _component("component:auth", "auth",
                                             member_count=9)]
        self._apply(records=changed, previous=self.records)
        allocations = [record for record in self._judgments()
                       if record["kind"] == "identity_allocation"]
        self.assertEqual(sorted(record["arch_id"] for record in allocations),
                         sorted([MAP_ARCH_ID, AUTH_ARCH_ID]))

    def test_the_ledger_advances_after_each_write(self):
        """'Advanced after each write' is what makes a retained ledger
        readable: a ledger frozen at all-pending cannot say how far the
        crashed run got."""
        captured = []
        real_write = arch_apply.atomic_io.write_json_atomic

        def _spy(path, obj):
            if os.path.basename(path) == state.APPLY_STATE_FILENAME:
                captured.append(json.loads(json.dumps(obj)))
            return real_write(path, obj)

        arch_apply.atomic_io.write_json_atomic = _spy
        self.addCleanup(setattr, arch_apply.atomic_io, "write_json_atomic",
                        real_write)
        self._apply()
        written_counts = [sum(1 for w in document["writes"]
                              if w["state"] == "written")
                          for document in captured]
        # Strictly increasing from zero, one write at a time.
        self.assertEqual(written_counts, list(range(len(captured))))


class Locking(_ApplyCase):
    """B's cross-surface lock, acquired under D's own operation name."""

    def test_apply_acquires_the_project_lock(self):
        seen = []
        real_lock = arch_apply.lock.ProjectLock

        def _spy(project_dir, operation, **kwargs):
            seen.append((project_dir, operation))
            return real_lock(project_dir, operation, **kwargs)

        arch_apply.lock.ProjectLock = _spy
        self.addCleanup(setattr, arch_apply.lock, "ProjectLock", real_lock)
        self._apply()
        self.assertEqual(seen, [(self.project_dir, "arch_apply")])


if __name__ == "__main__":
    unittest.main()
