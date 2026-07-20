"""architecture.preview -- the read-only projection preview (issue #374
child D, slice D5b, epic #141).

THIS IS THE FIRST PLACE THE PROJECTION CHAIN ACTUALLY RUNS. Slices C2/C3
and D1-D4 each shipped one link of it fully tested and entirely unjoined:
`candidates.plan`, `matcher.match`, `allocate.allocate`, `planner.plan` and
`apply.apply` had no common caller, so every integration between them was
asserted only by a test constructing the next stage's input by hand. This
module is that caller. It writes nothing.

THE TWO CANDIDATE SHAPES ARE NOT INTERCHANGEABLE. `matcher.CANDIDATE_KNOWN`
is exactly five fields and the matcher HARD ABORTS on a sixth; `planner`
and `diffs` need the rich record and `diffs.fingerprint` hard aborts on
anything outside `candidates.RECORD_FIELDS`. So the matcher gets
`candidates.matcher_view(record)` and everything downstream gets the rich
record. Handing either to the wrong callee is not a soft failure.

CONTESTED AND ROUTED CANDIDATES ARE REPORTED, NEVER PROJECTED. The matcher
returns four exhaustive outcomes. `mint` and `reuse` are actionable here.
The other two are not, and that is a contract requirement rather than a
simplification: for a contest `matcher.py` records that naming an identity
"would be the winner-pick the frozen contest rule forbids", and for a
routed outcome that medium confidence "is never collapsed into a silent
reuse". Child G, which resolves both, is a release out. Projecting them
anyway would either mint a second identity for code that already has one or
silently pick a contest winner. So they are classified, surfaced to the
operator, and excluded from the plan.

`previous` IS EMPTY, AND THE PLAN'S DISPOSITIONS ARE THEREFORE UNRELIABLE.
`planner.plan` decides mint/refresh/noop by comparing each candidate's
`diffs.fingerprint` against the PRIOR RUN'S RICH RECORDS. Nothing persists
those. `index.json` stores projected NODES -- arch_id, note_path,
source_paths -- not candidate records, and `diffs.fingerprint` requires the
full `candidates.RECORD_FIELDS` shape, including `metrics` and
`member_count`, which no node carries. There is no lossless reconstruction,
so this module passes `previous=()` and every entry's plan-level
`disposition` reads `mint`.

That would be a LYING PREVIEW if left there, so it is not left there. Each
entry is additionally decided against CURRENT DISK through
`notes.plan_note` -- the same public function `apply._decide` uses -- and
reported as `note_state`: `absent`, `changed`, `current`, or `conflict`.
That is the field an operator should read, and it is the one that predicts
what apply will do. The plan-level `disposition` is retained unaltered
because it is what feeds the fingerprint's `manifest` term, and the
fingerprint must be computed here exactly as apply will recompute it or
every confirmation burns as `stale_preview`.

THE FINGERPRINT IS THE WHOLE POINT OF PREVIEW. `apply` re-plans from
scratch and compares; a mismatch aborts. So preview and apply must be
handed identical `records`, `config`, `bindings`, `provider` AND
`identities` -- `identities` feeds `note_path`, which feeds `manifest`,
which is a fingerprint term. A re-minted random hex is harmless because
`arch_id` enters no term, but a differing SLUG moves a note path and burns
the confirmation.
"""
import os

from architecture import allocate
from architecture import candidates as arch_candidates
from architecture import judgments as arch_judgments
from architecture import matcher
from architecture import notes as arch_notes
from architecture import planner
from architecture import project as arch_project
from architecture import render
from architecture import state
from context_graph import atomic_io
from context_graph import config as ctx_config
from structural_graph import graphset

# Codes new with this slice. Each describes an INVOCATION -- a graph that
# could not be loaded, a config that is not there, a batch the allocator
# refused -- rather than a property of a persisted document, which is why
# none is expressible as a JSON Schema constraint.
E_PREVIEW_CONFIG_MISSING = "E_ARCH_PREVIEW_CONFIG_MISSING"
E_PREVIEW_CONFIG_INVALID = "E_ARCH_PREVIEW_CONFIG_INVALID"
E_PREVIEW_GRAPH_UNUSABLE = "E_ARCH_PREVIEW_GRAPH_UNUSABLE"
E_PREVIEW_BINDING_UNKNOWN = "E_ARCH_PREVIEW_BINDING_UNKNOWN"
E_PREVIEW_ALLOCATION_REFUSED = "E_ARCH_PREVIEW_ALLOCATION_REFUSED"
E_PREVIEW_IDENTITY_UNPLACEABLE = "E_ARCH_PREVIEW_IDENTITY_UNPLACEABLE"
E_PREVIEW_PLAN_REJECTED = "E_ARCH_PREVIEW_PLAN_REJECTED"

# Reported per planned entry, from deciding it against current disk.
NOTE_STATES = ("absent", "changed", "current", "conflict")

# Outcomes this surface can act on. The other two are child G's.
ACTIONABLE_OUTCOMES = ("mint", "reuse")


def _finding(code, message, **extra):
    d = {"code": code, "message": message, "index": None, "field": None}
    d.update(extra)
    return d


def _failed(findings):
    """A preview that could not be built. Same top-level shape as a
    successful one so a caller never has to branch on presence."""
    return {
        "ok": False,
        "findings": list(findings),
        "project_id": None,
        "entries": (),
        "manifest": (),
        "fingerprint": None,
        "over_cap": (),
        "applied": {},
        "deferred": [],
        "graph": {},
        "identities": {},
        "identity_records": [],
        "records": [],
    }


def _structural_cfg(config):
    """The structural-graph config, derived from the architecture config's
    bindings. `structural_graph.document` consults it only to resolve a
    binding_id to its repository entry (`document._find_binding`), so the
    binding_id/alias pair is all it needs."""
    return {
        "schema_version": 1,
        "repositories": [
            {"alias": binding.get("alias"),
             "binding_id": binding.get("binding_id")}
            for binding in (config.get("bindings") or [])
        ],
    }


def _load_graph(config, graph_paths):
    """Load the interchange documents for the configured bindings.

    `graph_paths` maps BINDING_ID -> path. That keying is not a choice:
    `graphset.load_set` looks each path up by binding_id, and a binding with
    no entry is reported `unavailable` rather than failing the run."""
    configured = {binding.get("binding_id")
                  for binding in (config.get("bindings") or [])}
    unknown = sorted(set(graph_paths or {}) - configured)
    if unknown:
        return None, [_finding(
            E_PREVIEW_BINDING_UNKNOWN,
            "no configured binding for %s; configure it first "
            "(`config add-binding`) so the projection knows which "
            "repository the document describes"
            % (", ".join(repr(b) for b in unknown),),
            field="bindings")]
    try:
        loaded = graphset.load_set(_structural_cfg(config), graph_paths or {})
    except ValueError as exc:
        # load_set raises only for a config whose bindings collide, which
        # state.validate_config already rejects -- so reaching here means
        # the config was hand-edited past its own validator.
        return None, [_finding(E_PREVIEW_GRAPH_UNUSABLE, str(exc))]
    return loaded, []


def _graph_report(loaded):
    """Per-binding load status, surfaced verbatim. A partial outage is
    contained by design (FC-4): one binding failing leaves the others'
    facts intact, so this is reported rather than raised."""
    return {
        "bindings": {
            binding_id: {"status": info["status"],
                         "freshness": info["freshness"]}
            for binding_id, info in sorted(
                (loaded.get("bindings") or {}).items())
        },
        "findings": list(loaded.get("findings") or []),
    }


def _existing_note_paths(notes_home, project_slug, config):
    """arch_id -> note_path from `index.json`, when one exists.

    `planner._note_path` prefers a note_path an identity carries, and the
    creation-event path is exactly what a rename must not recompute. A
    reused identity has no slug to format a path from, so without this
    lookup a reuse would either fail to place or silently move the note."""
    path = state.index_path(notes_home, project_slug)
    if not os.path.exists(path):
        return {}
    try:
        index = atomic_io.read_json(path)
    except (OSError, ValueError):
        # A damaged index is not this surface's to repair, and preview
        # writes nothing. Falling back to no carried paths is safe: the
        # planner then formats from the slug, and apply re-reads the index
        # itself under the lock.
        return {}
    carried = {}
    for node in (index or {}).get("nodes") or []:
        arch_id = node.get("arch_id")
        note_path = node.get("note_path")
        if arch_id and note_path:
            carried[arch_id] = note_path
    return carried


def _logged_note_paths(fold):
    """arch_id -> note_path, re-derived from each identity's OWN allocation.

    index.json is written AFTER the identity is appended, so between the
    two a reuse has an identity nobody can place. Since #374 slice D5c the
    allocation payload records the creation-event `slug` and
    `projection_type`, so the path is re-derived through the same
    `state.format_note_path` that produced it -- an exact reconstruction,
    not a guess from the candidate's current name (which a rename would
    move).

    Records written before that slice carry neither field and are skipped:
    they stay unplaceable, and `E_ARCH_PREVIEW_IDENTITY_UNPLACEABLE`
    reports them. This is a fallback BENEATH index.json, never above it --
    the index holds the path actually on disk, including one a later
    lifecycle event moved."""
    paths = {}
    for arch_id, kinds in (fold.get("latest_by_kind") or {}).items():
        payload = (kinds.get("identity_allocation") or {}).get("payload") or {}
        slug = payload.get("slug")
        projection_type = payload.get("projection_type")
        if not slug or not projection_type:
            continue
        try:
            paths[arch_id] = state.format_note_path(projection_type, slug)
        except ValueError:
            # A hand-edited payload. The log is authoritative for meaning,
            # not for legality: an illegal path is dropped and the identity
            # falls through to the unplaceable branch.
            continue
    return paths


def _merge_identities(outcomes, minted, carried_paths):
    """Combine the matcher's reuses with the allocator's mints.

    Nothing in the package does this: `allocate` returns mints only and
    `matcher` returns an arch_id for reuses, and `planner`/`apply` want one
    mapping. A reuse contributes no slug -- it never had a creation event
    here -- so it must carry the note_path recorded at its own creation,
    which is what `carried_paths` supplies."""
    identities = dict(minted)
    for outcome in outcomes:
        if outcome["outcome"] != "reuse":
            continue
        key = outcome["candidate_key"]
        arch_id = outcome["arch_id"]
        identity = {"arch_id": arch_id}
        if outcome.get("confidence"):
            identity["confidence"] = outcome["confidence"]
        note_path = carried_paths.get(arch_id)
        if note_path:
            identity["note_path"] = note_path
        identities[key] = identity
    return identities


def _render_body(entry, entries, record_by_key):
    """The generated-region body for one entry.

    Mirrors `apply._render_body` deliberately: preview's whole claim is
    that it predicts what apply will write, and predicting it from a
    different rendering would make the prediction meaningless. The map's
    member list excludes over-cap components for the same reason apply's
    does -- the cap binds creation, so an over-cap component has no note to
    link to."""
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


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def _note_state(entry, entries, record_by_key, identities, project_dir):
    """Decide one entry against CURRENT DISK, without writing.

    Uses `notes.plan_note`, the same public function `apply._decide` calls,
    so preview and apply cannot disagree about whether a note would change.
    Every entry is decided, including one the plan calls a no-op: a no-op
    means the candidate's reading did not move, which says nothing about
    whether its note is still on disk."""
    absolute = os.path.join(project_dir, entry["note_path"])
    existing = _read_text(absolute)
    identity = identities.get(entry["candidate_key"], {})
    try:
        body = _render_body(entry, entries, record_by_key)
        planned = arch_notes.plan_note(
            existing, body,
            arch_id=identity.get("arch_id"),
            projection_type=entry["projection_type"])
    except arch_notes.NoteInputError:
        # plan_note's create branch requires an arch_id. An entry can reach
        # here without one only when the matcher deferred it, and those are
        # excluded from the plan -- so this is a genuine "cannot place",
        # reported rather than crashing the preview.
        return "conflict", None
    action = planned["action"]
    if action == "create":
        return "absent", None
    if action == "update":
        return "changed", None
    if action == "noop":
        return "current", None
    return "conflict", planned.get("code")


def build_preview(notes_home, project_slug, graph_paths, provider=None,
                  decided_at=None):
    """Build this run's projection preview. WRITES NOTHING.

    `graph_paths` maps binding_id -> interchange document path. Returns a
    dict whose `ok` says whether a plan was produced; `findings` is always
    present and always a list."""
    config = None
    try:
        config = arch_project.load_config(
            arch_project.config_path(notes_home, project_slug))
    except state.ArchStateError as exc:
        return _failed(exc.findings)
    if config is None:
        return _failed([_finding(
            E_PREVIEW_CONFIG_MISSING,
            "no architecture configuration for project %r; run `init` first"
            % (project_slug,))])
    config_findings = state.validate_config(config)
    if config_findings:
        return _failed([_finding(
            E_PREVIEW_CONFIG_INVALID,
            "the architecture configuration does not validate; preview "
            "refuses to plan against it")] + list(config_findings))

    project_id = config["project_id"]
    project_dir = ctx_config.project_dir(notes_home, project_slug)

    loaded, findings = _load_graph(config, graph_paths)
    if findings:
        return _failed(findings)

    planned = arch_candidates.plan(
        loaded, configured=tuple(config.get("exclusions") or ()))
    records = list(planned["candidates"])

    try:
        log = arch_judgments.load_judgments(
            state.judgments_path(notes_home, project_slug), project_id)
    except state.ArchStateError as exc:
        # Covers JudgmentsCorruptError and ProjectIdMismatchError alike --
        # both subclass ArchStateError, so a separate clause for either
        # would be unreachable.
        return _failed(exc.findings)
    fold = arch_judgments.fold_judgments(log["records"])

    try:
        assigned = matcher.match(
            [arch_candidates.matcher_view(record) for record in records],
            fold, thresholds=config.get("thresholds"))
    except state.ArchStateError as exc:
        return _failed(exc.findings)
    outcomes = list(assigned["outcomes"])
    by_key = {outcome["candidate_key"]: outcome for outcome in outcomes}

    # Deferred: classified, surfaced, and excluded from the plan.
    deferred = [
        {"candidate_key": outcome["candidate_key"],
         "outcome": outcome["outcome"],
         "confidence": outcome["confidence"],
         "reason": outcome["reason"],
         "contested_with": outcome.get("contested_with"),
         "contested_by": outcome.get("contested_by")}
        for outcome in outcomes
        if outcome["outcome"] not in ACTIONABLE_OUTCOMES
    ]
    deferred_keys = {entry["candidate_key"] for entry in deferred}
    projectable = [record for record in records
                   if record["candidate_key"] not in deferred_keys]

    # Index first in precedence, log as the fallback: the index records
    # where a note actually IS, the log where its creation event PUT it.
    carried_paths = _logged_note_paths(fold)
    carried_paths.update(_existing_note_paths(notes_home, project_slug, config))

    # A REUSED IDENTITY WHOSE NOTE PATH IS UNKNOWN CANNOT BE PLACED, and is
    # deferred rather than allowed to reject the whole plan. A reuse
    # supplies no slug -- its creation event happened in an earlier run --
    # so `planner._note_path` can only use a path the identity carries.
    #
    # Since D5c there are TWO records of that path (`_logged_note_paths`
    # and `_existing_note_paths`), which is what closed #374's
    # unplaceable-reuse question: the allocation payload carries the
    # creation-event slug, so the crash window between the identity append
    # and the index write no longer strands anything. What remains here is
    # the residue -- an allocation written BEFORE D5c, or one hand-edited
    # into illegality. Those are deferred; before this guard the resulting
    # PlanInputError rejected every candidate in the run, unrelated ones
    # included.
    unplaceable = []
    for outcome in outcomes:
        if outcome["outcome"] != "reuse":
            continue
        if not carried_paths.get(outcome["arch_id"]):
            unplaceable.append(outcome["candidate_key"])
    unplaceable_findings = []
    if unplaceable:
        unplaceable_set = set(unplaceable)
        unplaceable_findings.append(_finding(
            E_PREVIEW_IDENTITY_UNPLACEABLE,
            "the judgments log knows an identity for %s but neither "
            "index.json nor the identity's own allocation records a "
            "usable note path for it; these candidates are deferred "
            "rather than projected to a guessed path"
            % (", ".join(repr(key) for key in sorted(unplaceable_set)),)))
        deferred.extend(
            {"candidate_key": key,
             "outcome": "reuse",
             "confidence": by_key[key]["confidence"],
             "reason": "note_path_unknown",
             "contested_with": None,
             "contested_by": None}
            for key in sorted(unplaceable_set))
        deferred_keys |= unplaceable_set
        projectable = [record for record in projectable
                       if record["candidate_key"] not in unplaceable_set]

    to_mint = [record for record in projectable
               if by_key[record["candidate_key"]]["outcome"] == "mint"]
    try:
        minted = allocate.allocate(project_id, to_mint, decided_at)
    except (allocate.SlugError, allocate.SlugCollisionError) as exc:
        # Both, explicitly: SlugCollisionError does NOT subclass SlugError
        # -- they are sibling ValueError subclasses -- so catching only the
        # latter would let a refused batch escape as a traceback.
        return _failed([_finding(E_PREVIEW_ALLOCATION_REFUSED, str(exc))])

    identities = _merge_identities(outcomes, minted["identities"],
                                   carried_paths)

    try:
        plan = planner.plan(
            projectable, previous=(), config=config, identities=identities,
            notes_root=project_dir, bindings=loaded.get("bindings"),
            provider=provider)
    except planner.PlanInputError as exc:
        return _failed([_finding(E_PREVIEW_PLAN_REJECTED, str(exc))])

    record_by_key = {record["candidate_key"]: record
                     for record in projectable}
    entries = []
    for entry in plan["entries"]:
        note_state, conflict_code = _note_state(
            entry, plan["entries"], record_by_key, identities, project_dir)
        enriched = dict(entry)
        enriched["note_state"] = note_state
        enriched["arch_id"] = identities.get(
            entry["candidate_key"], {}).get("arch_id")
        enriched["identity_outcome"] = by_key[
            entry["candidate_key"]]["outcome"]
        if conflict_code:
            enriched["conflict_code"] = conflict_code
        entries.append(enriched)

    return {
        "ok": True,
        "findings": (list(assigned["findings"]) + list(log["findings"])
                     + unplaceable_findings),
        "project_id": project_id,
        "entries": tuple(entries),
        "manifest": plan["manifest"],
        "fingerprint": plan["fingerprint"],
        "over_cap": plan["over_cap"],
        "applied": plan["applied"],
        "deferred": deferred,
        "graph": _graph_report(loaded),
        "identities": identities,
        "identity_records": minted["records"],
        "records": projectable,
    }
