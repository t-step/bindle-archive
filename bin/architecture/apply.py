"""architecture.apply -- the projection write orchestrator and its resume
(issue #230 child D, slice D4, epic #141).

The first D slice that writes. Everything before it planned, rendered or
classified in memory; this module is where a plan becomes bytes on disk,
and every guarantee the epic makes about crash safety lands here.

A CONFIRMATION BINDS THE PLAN IT WAS GIVEN FOR. Apply re-plans against
CURRENT inputs, recomputes D3's fingerprint, and aborts as `stale_preview`
when it differs from the token the operator confirmed. Trusting the plan
handed in would let a `git pull` between preview and apply write a plan
nobody saw and mint identities nobody reviewed.

RESUME RE-PLANS; IT NEVER REPLAYS. `apply-state.json` is recovery metadata
only (FC-5) -- it says an apply did not finish and which paths it touched,
and nothing about what any of it means. The write decision on resume comes
from a fresh plan against current inputs AND current disk, so a hand edit
made between the crash and the resume survives and a stale recorded hash
can never clobber it. The retained ledger's `after_hash` is never compared
against anything and never reproduced.

THE LEDGER RECORDS NOTE WRITES ONLY. `index.json` is rebuilt in full by
every re-plan, so it needs no recovery metadata; leaving it out also keeps
every ledger path a note path, which is what makes orphan detection
unambiguous -- an orphan is exactly a ledger path the fresh plan does not
contain. The ledger is created ONLY for a non-empty changed set, after the
plan validates and before the first write, and is CLEARED BY REMOVAL on
success. Removal rather than `status: complete` leaves one invariant
instead of two states to disambiguate: the file exists if and only if an
apply did not finish.

IDENTITY IS COMMITTED FIRST, THROUGH B'S PRIMITIVE. Every
`identity_allocation` append precedes the ledger and the first note byte,
routed through `judgments.commit_identity_then` rather than ordered by
hand -- the guarantee is a property of that function. A crash is then
always recoverable forward: the identity exists and a fresh re-plan
re-renders its note.

WHAT THIS MODULE DOES NOT DECIDE. Identity assignment arrives from the
caller: `identities` maps candidate keys to the arch-node ids the matcher
resolved, and `identity_records` carries the creation events for mints.
Nothing in the kit allocates a fresh arch-node hex today
(`ids.format_arch_node_id` has no caller), so minting a value here would be
inventing the allocator inside the writer. D5 wires the matcher and the
allocator to this surface. An identity whose allocation is already on the
log is never re-appended: allocation happens once, at the creation event.

AN ORPHAN IS CLASSIFIED, NOT RESOLVED. A note the crashed run wrote that
the fresh re-plan does not contain is marked `partial` with
`orphaned_by_resume`, its bytes untouched and reported. D may not delete it
(never-auto-delete) and may not stale it (G's AC16), so classification is
the honest MVP outcome.
"""
import hashlib
import os
import time

from architecture import judgments
from architecture import notes as arch_notes
from architecture import planner
from architecture import render
from architecture import state
from context_graph import atomic_io
from context_graph import config as ctx_config
from context_graph import lock

# The operation name B's lock reserves for this surface. Not one of the
# context-surface names: the lock covers both trees, and reusing "apply"
# would make a context apply and an architecture apply indistinguishable in
# a contention message.
LOCK_OPERATION = "arch_apply"

_STATUS_APPLIED = "applied"
_STATUS_NOOP = "noop"
_STATUS_STALE = "stale_preview"
_STATUS_UNCONFIRMED = "unconfirmed"
_STATUS_REJECTED = "rejected"


def _hash_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read_bytes(path):
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except (FileNotFoundError, NotADirectoryError):
        return None


def _read_text(path):
    data = _read_bytes(path)
    return None if data is None else data.decode("utf-8")


def _result(status, ok, **extra):
    result = {"status": status, "ok": ok, "writes": [], "conflicts": [],
              "orphans": [], "findings": [], "resumed": False}
    result.update(extra)
    return result


def _commit_identities_then(path, records, write):
    """Append every identity record, then call `write` -- with each append
    routed through B's ordering primitive.

    Folded rather than looped so that no step is ordered by hand: each
    record's append is the thing that invokes the next, and the write side
    is reached only from inside the innermost `commit_identity_then`. A
    plain loop followed by `write()` would produce the same sequence today
    while quietly moving the guarantee out of B's function and into this
    call site, which is the failure #230 warns about for every inherited
    primitive.
    """
    stamped = []

    def _write_side():
        write()

    step = _write_side
    for record in reversed(list(records)):
        step = _chain(path, record, step, stamped)
    step()
    return stamped


def _chain(path, record, next_step, stamped):
    def _step():
        stamped.append(judgments.commit_identity_then(path, record, next_step))
    return _step


def _allocated_arch_ids(judgments_path, project_id):
    """The identities whose creation event is already on the log."""
    if not os.path.exists(judgments_path):
        return frozenset()
    loaded = judgments.load_judgments(judgments_path, project_id)
    return frozenset(
        record.get("arch_id") for record in loaded["records"]
        if record.get("kind") == "identity_allocation" and record.get("arch_id")
    )


def _render_body(entry, entries, record_by_key):
    record = record_by_key[entry["candidate_key"]]
    if entry["projection_type"] == "arch_codebase_map":
        members = [
            {"candidate_key": other["candidate_key"],
             "name": record_by_key[other["candidate_key"]]["name"],
             "note_path": other["note_path"]}
            for other in entries
            if other["projection_type"] == "arch_component"
            and not other["over_cap"]
        ]
        return render.render_codebase_map(record, members)
    return render.render_component(record)


def _decide(entry, entries, record_by_key, identities, project_dir):
    """The write decision for one entry, against current disk.

    Every entry is decided against disk, including one the plan calls a
    no-op: a no-op means the candidate's READING did not move, which says
    nothing about whether its note is still there. A crash between the
    identity commit and the note write leaves exactly that state, and
    deciding only the non-no-op entries would leave the note missing
    forever.
    """
    absolute = os.path.join(project_dir, entry["note_path"])
    body = _render_body(entry, entries, record_by_key)
    identity = identities.get(entry["candidate_key"], {})
    plan = arch_notes.plan_note(
        _read_text(absolute), body,
        arch_id=identity.get("arch_id"),
        projection_type=entry["projection_type"])
    return absolute, plan


def _index_node(entry, record, identity, bindings, provider, projected_at):
    node = {
        "arch_id": identity["arch_id"],
        "project_id": identity["arch_id"].split(":", 2)[1] + ":"
                      + identity["arch_id"].split(":")[2],
        "note_path": entry["note_path"],
        "binding_ids": sorted(
            b for b in (record.get("bindings") or [])
            if isinstance(b, str) and b.startswith("repository-binding:")),
        "projection_type": entry["projection_type"],
        "projection_schema_version": state.PROJECTION_SCHEMA_VERSION,
        "confidence": identity.get("confidence", "high"),
        "projection_status": "current",
        "source_paths": sorted(record.get("source_paths") or []),
    }
    if isinstance(provider, dict):
        if provider.get("name"):
            node["provider_name"] = provider["name"]
        if provider.get("version"):
            node["provider_version"] = provider["version"]
    commits = []
    for binding_id in node["binding_ids"]:
        observed = (bindings or {}).get(binding_id)
        commit = (observed.get("source_commit")
                  if isinstance(observed, dict) else observed)
        if isinstance(commit, str) and len(commit) == 40:
            commits.append({"binding_id": binding_id, "commit": commit})
    if commits:
        node["source_commits"] = commits
    if projected_at:
        node["last_projected_at"] = projected_at
    return node


def _build_index(project_id, entries, record_by_key, identities, conflicted,
                 previous_index, orphan_paths, bindings, provider,
                 projected_at):
    """The projection's durable record: a node per note this run stands
    behind, plus every prior node it did not touch.

    Carrying prior nodes forward matters more than it looks: an over-cap
    candidate and an orphan both have notes on disk that this run did not
    write, and dropping their nodes would leave those files unreferenced by
    any surface -- the exact outcome the cap's "mark, do not drop" rule and
    the never-auto-delete rule exist to prevent.
    """
    nodes = []
    claimed_paths = set()
    for entry in entries:
        identity = identities.get(entry["candidate_key"]) or {}
        if entry["over_cap"] or not identity.get("arch_id"):
            continue
        if entry["note_path"] in conflicted:
            # The note on disk is not ours to describe: nothing was written
            # and its bytes are hand-authored.
            continue
        nodes.append(_index_node(entry, record_by_key[entry["candidate_key"]],
                                 identity, bindings, provider, projected_at))
        claimed_paths.add(entry["note_path"])

    known_ids = {node["arch_id"] for node in nodes}
    for node in (previous_index or {}).get("nodes", []):
        if node.get("arch_id") in known_ids:
            continue
        carried = dict(node)
        if carried.get("note_path") in orphan_paths:
            carried["projection_status"] = "partial"
            carried["orphaned_by_resume"] = True
        nodes.append(carried)

    index = {
        "schema_version": state.SCHEMA_VERSION,
        "projection_schema_version": state.PROJECTION_SCHEMA_VERSION,
        "project_id": project_id,
        "nodes": sorted(nodes, key=lambda node: node["arch_id"]),
    }
    references = (previous_index or {}).get("references")
    if references:
        index["references"] = references
    return index


def apply(notes_home, project_slug, project_id, records, confirmed_fingerprint,
          identities=None, identity_records=(), previous=(), config=None,
          bindings=None, provider=None, projected_at=None):
    """Write this run's projection, under B's cross-surface lock.

    Returns a result dict carrying `status` (`applied` / `noop` /
    `stale_preview` / `unconfirmed` / `rejected`), `ok`, the `writes`
    performed, any `conflicts` and `orphans`, and `resumed`.
    """
    project_dir = ctx_config.project_dir(notes_home, project_slug)
    with lock.ProjectLock(project_dir, LOCK_OPERATION):
        return _apply_locked(
            notes_home, project_slug, project_id, project_dir, records,
            confirmed_fingerprint, identities or {}, identity_records or (),
            previous, config, bindings, provider, projected_at)


def _apply_locked(notes_home, project_slug, project_id, project_dir, records,
                  confirmed_fingerprint, identities, identity_records,
                  previous, config, bindings, provider, projected_at):
    if not confirmed_fingerprint:
        # Apply is the confirmed half of preview -> confirm -> apply. With
        # no token there is nothing to bind the plan to, and applying
        # anyway would make the confirmation optional in practice.
        return _result(_STATUS_UNCONFIRMED, False, findings=[{
            "code": "E_ARCH_APPLY_UNCONFIRMED",
            "message": "apply requires the plan fingerprint preview printed"}])

    try:
        plan = planner.plan(records, previous=previous, config=config,
                            identities=identities, notes_root=project_dir,
                            bindings=bindings, provider=provider)
    except planner.PlanInputError as exc:
        return _result(_STATUS_REJECTED, False, findings=[{
            "code": "E_ARCH_APPLY_PLAN_REJECTED", "message": str(exc)}])

    if plan["fingerprint"] != confirmed_fingerprint:
        return _result(
            _STATUS_STALE, False,
            confirmed_fingerprint=confirmed_fingerprint,
            current_fingerprint=plan["fingerprint"],
            findings=[{
                "code": "E_ARCH_APPLY_STALE_PREVIEW",
                "message": "inputs moved between preview and apply; the "
                           "confirmed plan is no longer the current one"}])

    apply_state_path = state.apply_state_path(notes_home, project_slug)
    retained = None
    if os.path.exists(apply_state_path):
        try:
            retained = atomic_io.read_json(apply_state_path)
        except ValueError:
            retained = None
    resumed = retained is not None

    entries = list(plan["entries"])
    record_by_key = {record["candidate_key"]: record for record in records}

    planned = []
    conflicts = []
    conflicted_paths = set()
    for entry in entries:
        if entry["over_cap"]:
            continue
        absolute, decision = _decide(entry, entries, record_by_key,
                                     identities, project_dir)
        if decision["action"] == "conflict":
            conflicts.append({"code": decision["code"],
                              "note_path": entry["note_path"]})
            conflicted_paths.add(entry["note_path"])
            continue
        if decision["action"] == "noop":
            continue
        planned.append({
            "note_path": entry["note_path"],
            "absolute": absolute,
            "bytes": decision["text"].encode("utf-8"),
            "candidate_key": entry["candidate_key"],
        })

    planned_paths = {entry["note_path"] for entry in entries}
    orphans = _orphans(retained, planned_paths, project_dir)

    previous_index = None
    index_path = state.index_path(notes_home, project_slug)
    if os.path.exists(index_path):
        try:
            previous_index = atomic_io.read_json(index_path)
        except ValueError:
            previous_index = None

    if not planned:
        # A semantic no-op: zero bytes, no ledger. A ledger RETAINED from an
        # interrupted run whose fresh plan is a no-op is simply cleared --
        # the work it recorded is already done or no longer planned.
        result = _result(_STATUS_NOOP, True, resumed=resumed,
                         conflicts=conflicts, orphans=orphans)
        if resumed:
            if orphans:
                atomic_io.write_json_atomic(index_path, _build_index(
                    project_id, entries, record_by_key, identities,
                    conflicted_paths, previous_index,
                    {orphan["note_path"] for orphan in orphans},
                    bindings, provider, projected_at))
            _clear(apply_state_path)
        return result

    ledger = {
        "schema_version": state.SCHEMA_VERSION,
        "project_id": project_id,
        "status": "in_progress",
        "started_at": projected_at or time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                    time.gmtime()),
        "writes": [
            {"order": order,
             "path": write["note_path"],
             "before_hash": _before_hash(write["absolute"]),
             "after_hash": _hash_bytes(write["bytes"]),
             "state": "pending"}
            for order, write in enumerate(planned)
        ],
    }
    findings = state.validate_apply_state(ledger)
    if findings:
        # Refusing here rather than writing an unreadable ledger: a manifest
        # a resume cannot parse is worse than no manifest, because the
        # resume then cannot tell an interrupted apply from a clean tree.
        return _result(_STATUS_REJECTED, False, findings=findings,
                       conflicts=conflicts, orphans=orphans, resumed=resumed)

    pending = [record for record in identity_records
               if record.get("arch_id") not in _allocated_arch_ids(
                   state.judgments_path(notes_home, project_slug), project_id)]

    writes = []

    def _write_everything():
        atomic_io.write_json_atomic(apply_state_path, ledger)
        for order, write in enumerate(planned):
            atomic_io.write_atomic(write["absolute"], write["bytes"])
            ledger["writes"][order]["state"] = "written"
            atomic_io.write_json_atomic(apply_state_path, ledger)
            writes.append({"note_path": write["note_path"], "written": True})

    try:
        _commit_identities_then(
            state.judgments_path(notes_home, project_slug), pending,
            _write_everything)
    except (judgments.JudgmentsCorruptError, ValueError) as exc:
        return _result(_STATUS_REJECTED, False, conflicts=conflicts,
                       orphans=orphans, resumed=resumed, findings=[{
                           "code": "E_ARCH_APPLY_IDENTITY_REFUSED",
                           "message": str(exc)}])

    atomic_io.write_json_atomic(index_path, _build_index(
        project_id, entries, record_by_key, identities, conflicted_paths,
        previous_index, {orphan["note_path"] for orphan in orphans},
        bindings, provider, projected_at))
    _clear(apply_state_path)

    return _result(_STATUS_APPLIED, True, writes=writes, conflicts=conflicts,
                   orphans=orphans, resumed=resumed)


def _before_hash(absolute):
    data = _read_bytes(absolute)
    return None if data is None else _hash_bytes(data)


def _orphans(retained, planned_paths, project_dir):
    """Notes an interrupted run wrote that the fresh plan does not contain.

    Only paths still ON DISK are reported: one the crashed run recorded but
    never actually wrote is not an orphan, it is a write that never
    happened, and reporting it would send a reader looking for a file that
    does not exist.
    """
    if not retained:
        return []
    orphans = []
    for write in retained.get("writes") or []:
        note_path = write.get("path")
        if not note_path or note_path in planned_paths:
            continue
        if not os.path.exists(os.path.join(project_dir, note_path)):
            continue
        orphans.append({"note_path": note_path,
                        "reason": "orphaned_by_resume"})
    return sorted(orphans, key=lambda orphan: orphan["note_path"])


def _clear(apply_state_path):
    """Clear the ledger by REMOVAL -- see the module docstring on why the
    file's existence is the whole signal."""
    try:
        os.remove(apply_state_path)
    except FileNotFoundError:
        pass
