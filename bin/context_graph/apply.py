"""context_graph.apply -- the side-effect-free planned-state construction for
the #185 apply pipeline (design doc section 12, steps 1-6).

`build_plan` re-runs the #183 deterministic compiler, reduces the #184
judgment ledger into effective identity-anchor authorizations and judged
edges, constructs the exact intended `map.md` bytes in memory (authorized
anchor markers only), re-compiles against those planned bytes so a
first-apply anchor is discovered by the same canonical parser #183 uses,
materializes the effective judged edges, and validates the complete planned
state against #180's full invariant set -- all WITHOUT touching disk. It
returns the planned bytes/objects for map.md, index.json, and context.md.

This module WRITES NOTHING. Task 9 (`apply()`) adds the single-writer lock
and the atomic, byte-for-byte-diffed writes on top of the plan this module
produces. Keeping construction and validation entirely side-effect-free is
what lets #140's "construct and validate the complete intended final state
before its first write" guarantee be tested without a filesystem.
"""
import json
import os

from context_graph import (
    atomic_io,
    compiler,
    config,
    index_writer,
    ledger,
    lock,
    map_parser,
    projection,
    relationships as rel,
    validation,
)
from context_graph.map_writer import plan_map_bytes


class ApplyError(Exception):
    """Raised only when the plan cannot be constructed at all (mirrors
    compiler.CompilerError / review.ReviewError). `.findings` is a non-empty
    list of {"code", "message", ...} dicts so the CLI renders it uniformly
    with every other findings-shaped error. `build_plan` itself does not
    raise for expected aborts (missing config, project_id mismatch, an
    illegal judged edge at apply time) -- those return `{"ok": False, ...}`
    so the CLI can render findings and exit without a traceback."""

    def __init__(self, findings):
        self.findings = findings
        super().__init__("; ".join(f.get("message", "") for f in findings))


def _finding(code, message, **extra):
    out = {"code": code, "message": message}
    out.update(extra)
    return out


def _read_text_or_none(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def build_plan(notes_home, project_slug, repo_roots=None, adopt_context_md=False,
               github_adapter=None):
    """Construct and validate the complete intended final state for `apply`
    without writing anything (design doc section 12, steps 1-6).

    Returns a dict:
      - `{"ok": False, "findings": [...], "conflicts": [...]}` on any hard
        abort (unreadable config, project_id mismatch, an accepted judged
        edge whose endpoint pair is illegal against this run's planned graph,
        or a whole-state invariant violation). No `artifacts` key is present.
      - `{"ok": True, "findings": [...], "conflicts": [...], "artifacts":
        {...}}` otherwise, where `artifacts` carries the planned bytes/objects
        for map.md, index.json, and context.md (never written here).
    """
    findings = []

    # Step 1: re-run the full #183 deterministic pipeline against current
    # sources -- never trust a prior preview or index.json.
    try:
        base = compiler.compile_preview(
            notes_home, project_slug, repo_roots=repo_roots,
            github_adapter=github_adapter)
    except compiler.CompilerError as exc:
        return {"ok": False, "findings": list(exc.findings), "conflicts": []}

    cfg = config.load_config(config.config_path(notes_home, project_slug))
    project_id = base["project_id"]
    context_dir = config.context_dir(notes_home, project_slug)
    project_dir = config.project_dir(notes_home, project_slug)

    # Step 2: verify project identity. config, base, and any existing
    # index.json must all agree. Never allocate or repair the id here.
    if cfg is None or cfg.get("project_id") != project_id:
        return {"ok": False, "conflicts": base["conflicts"], "findings": [_finding(
            "project_id_mismatch",
            "configured project_id %r does not match compiled project_id %r"
            % ((cfg or {}).get("project_id"), project_id))]}
    index_path = os.path.join(context_dir, "index.json")
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as fh:
                existing_index = json.load(fh)
        except (ValueError, OSError):
            existing_index = None
        if isinstance(existing_index, dict) and \
                existing_index.get("project_id") not in (None, project_id):
            return {"ok": False, "conflicts": base["conflicts"], "findings": [_finding(
                "project_id_mismatch",
                "on-disk index.json project_id %r does not match compiled "
                "project_id %r" % (existing_index.get("project_id"), project_id))]}

    # Step 3: load and reduce the judgment ledger. The revalidation callback
    # (invoked per accepted event by the reducer) gates identity-anchor events
    # by fingerprint against this run's #183 graph, and applies TIER 1 of the
    # two-tier illegal-judged-edge model (design section 11/12/16):
    #
    #   Tier 1 (here, drop-and-continue): if BOTH endpoints of an accepted edge
    #   already exist in `base` (the on-disk graph) and the pair is illegal, the
    #   judgment was already stale before this run -- return False so the
    #   reducer drops it as inert and emits a `stale_illegal_judgment` finding;
    #   the apply CONTINUES with the edge simply not materialized.
    #
    #   If either endpoint is ABSENT from `base` it may be first-anchored THIS
    #   run, so its legality cannot be judged against `base` -- return True and
    #   defer to Tier 2 (step 6's materialization against the PLANNED graph).
    events = ledger.load_judgments(ledger.judgments_path(notes_home, project_slug))
    base_anchor_fps = {
        c["entry_fingerprint"] for c in base["identity_anchor_candidates"]
    }
    base_nodes_by_id = {n["id"]: n for n in base["nodes"]}

    def _revalidate(ev):
        if ev.get("subject_type") == "identity_anchor":
            # An accepted anchor stays effective if its target still exists
            # in either state: already MATERIALIZED (its assigned_id is a
            # node in the base graph, from a prior apply's marker) or still
            # PENDING (its fingerprint is an unanchored candidate, not yet
            # applied). base_anchor_fps only ever holds UNANCHORED entries,
            # so without the materialized-node check every anchor would be
            # flagged stale_illegal_judgment and dropped on the apply
            # immediately after the one that materialized it (issue #185).
            return (ev.get("assigned_id") in base_nodes_by_id
                    or ev.get("entry_fingerprint") in base_anchor_fps)
        if ev.get("subject_type") == "edge":
            src = base_nodes_by_id.get(ev.get("source"))
            tgt = base_nodes_by_id.get(ev.get("target"))
            if src is None or tgt is None:
                # An endpoint may be first-anchored this run: defer legality to
                # the planned-graph check at step 6 (Tier 2).
                return True
            verdict = rel.validate_endpoint_pair(
                ev.get("relationship"), src.get("class"), src.get("kind"),
                tgt.get("class"), tgt.get("kind"))
            # Tier 1: illegal already against base -> drop as inert, continue.
            return verdict["ok"]
        return True

    reduced = ledger.reduce_judgments(events, revalidate=_revalidate)
    findings.extend(reduced["findings"])

    accepted_anchor_events = [
        cur["event"] for cur in reduced["effective"].values()
        if cur["subject_type"] == "identity_anchor"
    ]
    effective_edge_events = [
        cur["event"] for cur in reduced["effective"].values()
        if cur["subject_type"] == "edge"
    ]

    # Step 3-4: construct the exact intended map.md bytes in memory -- only
    # authorized anchor markers inserted, no other byte changed.
    #
    # A satisfied anchor (its assigned_id is already a node in `base`) was
    # materialized by a prior apply -- its marker already sits on disk, so it
    # needs no insertion. plan_map_bytes only matches anchors to UNANCHORED
    # entries by fingerprint, so passing satisfied anchors through would emit
    # a spurious `stale_anchor_no_entry` finding on every clean re-apply
    # (issue #185). Only PENDING anchors are inserted.
    pending_anchor_events = [
        ev for ev in accepted_anchor_events
        if ev.get("assigned_id") not in base_nodes_by_id
    ]
    map_rel_path = compiler._map_rel_path(project_slug)
    base_map_text = _read_text_or_none(
        os.path.join(project_dir, compiler.MAP_FILENAME)) or ""
    base_entries = map_parser.parse_project_map(base_map_text)["entries"]
    planned_map, map_findings = plan_map_bytes(
        base_map_text, base_entries, pending_anchor_events, project_id, map_rel_path)
    findings.extend(map_findings)

    # Step 4-5: re-compile against the PLANNED map bytes using the same
    # canonical parser #183 uses. An entry anchored for the first time this
    # run is therefore discovered by re-parsing the actual planned text, so it
    # appears in this run's final nodes/edges (the first-apply-anchor
    # guarantee, design doc section 12 step 4).
    final = compiler.compile_preview(
        notes_home, project_slug, repo_roots=repo_roots,
        github_adapter=github_adapter, map_text_override=planned_map)

    # Step 6: materialize effective judged edges onto the planned graph.
    nodes_by_id = {n["id"]: n for n in final["nodes"]}
    seen_keys = {e["key"] for e in final["edges"]}
    materialized = []
    abort_illegal = False
    for ev in effective_edge_events:
        source = ev.get("source")
        relationship = ev.get("relationship")
        target = ev.get("target")
        src = nodes_by_id.get(source)
        tgt = nodes_by_id.get(target)
        if src is None or tgt is None:
            # A referenced node has since been removed from the map: the
            # judged edge is orphaned and cannot be materialized. Drop it with
            # a diagnostic (non-destructive -- the operator deleted the entry),
            # rather than aborting the whole apply.
            findings.append(_finding(
                "judged_edge_missing_endpoint",
                "judged edge %s|%s|%s references a node absent from the "
                "planned graph" % (source, relationship, target),
                subject_key=ev.get("subject_key")))
            continue
        verdict = rel.validate_endpoint_pair(
            relationship, src.get("class"), src.get("kind"),
            tgt.get("class"), tgt.get("kind"))
        if not verdict["ok"]:
            # TIER 2 (design section 11/12/16, two-tier illegal-edge model): an
            # accepted edge that was LEGAL at ledger reduction (an endpoint was
            # absent from `base`, so Tier 1 deferred it) but is ILLEGAL against
            # the PLANNED graph -- e.g. an endpoint first-anchored THIS run
            # whose planned kind makes the pair illegal. Unlike Tier 1's
            # drop-and-continue, this aborts the ENTIRE apply and nothing is
            # written. A DISTINCT finding code (`illegal_edge_planned_state`,
            # never `stale_illegal_judgment`) lets a consumer tell "continued"
            # from "aborted".
            findings.append(_finding(
                "illegal_edge_planned_state",
                "accepted judged edge %s|%s|%s is illegal against the planned "
                "graph (%s/%s -> %s/%s)" % (
                    source, relationship, target, src.get("class"),
                    src.get("kind"), tgt.get("class"), tgt.get("kind")),
                subject_key=ev.get("subject_key")))
            abort_illegal = True
            continue
        # The judged edge's key IS its ledger subject_key: #180's whole-state
        # validation matches a human_judgment edge to an effective accepted
        # judgment by `edge["key"] in {judgment["subject_key"]}`
        # (validation._check_edges), and the ledger's edge subject_key is
        # canonical.edge_subject_key(...), not the deterministic pipe key.
        key = ev.get("subject_key")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        materialized.append({
            "key": key,
            "source": source,
            "relationship": relationship,
            "target": target,
            "status": "confirmed",
            "origin": "human_judgment",
            # v1 pins review_trigger to the relationship default; validation
            # rejects any other value (E_EDGE_REVIEW_TRIGGER_MISMATCH).
            "review_trigger": rel.get_review_trigger_default(relationship),
            "basis": ev.get("basis", []),
        })

    if abort_illegal:
        return {"ok": False, "conflicts": final["conflicts"], "findings": findings}

    final["edges"] = sorted(final["edges"] + materialized, key=lambda e: e["key"])

    # Step 7: attach the two apply-only index fields. `unresolved_evidence`
    # surfaces the compiler's own unresolved-evidence conflicts (a map
    # evidence pointer that did not tokenize or did not resolve to a source);
    # `suppressed_rejections` is the reducer's monotonic set of rejected
    # candidate keys (a rejected candidate whose content is unchanged is not
    # re-offered). index_writer defaults both to [] when absent.
    final["unresolved_evidence"] = [
        {"code": c["code"], "message": c["message"], "line": c.get("line")}
        for c in final["conflicts"]
        if str(c.get("code", "")).startswith("unresolved-evidence")
    ]
    final["suppressed_rejections"] = sorted(reduced["rejected_keys"])

    # Step 8: validate the complete planned state against #180's full
    # invariant set BEFORE any write. Any survivor is an illegal record that
    # slipped into the planned graph -- abort the entire apply (design doc
    # section 12 step 6). Nothing is written.
    bundle_findings = validation.validate_bundle({
        "config": cfg, "nodes": final["nodes"], "edges": final["edges"],
        "candidates": [], "judgments": events,
    })
    if bundle_findings:
        for f in bundle_findings:
            findings.append(_finding(
                "planned_state_invariant_violation",
                "%s: %s" % (f["code"], f["message"]), field=f.get("field")))
        return {"ok": False, "conflicts": final["conflicts"], "findings": findings}

    # Step 9: render the three target artifacts (NO writes). The index's
    # planned_bytes match atomic_io.write_json_atomic's serialization exactly,
    # so Task 9's byte-for-byte no-op comparison is against the same bytes
    # that would be written.
    planned_index = index_writer.render_index(final)
    index_bytes = (json.dumps(planned_index, indent=2, sort_keys=True) + "\n").encode("utf-8")

    managed = projection.render_managed_region(final)
    title = (cfg.get("display_name") or project_slug)
    existing_context = _read_text_or_none(os.path.join(project_dir, "context.md"))
    if adopt_context_md:
        ctx_plan = projection.plan_adopt_context_md(existing_context or "", managed, title)
    else:
        ctx_plan = projection.plan_context_md(existing_context, managed, title)

    return {
        "ok": True,
        "findings": findings,
        "conflicts": final["conflicts"],
        "artifacts": {
            "map": {
                "path": os.path.join(project_dir, compiler.MAP_FILENAME),
                "planned_bytes": planned_map.encode("utf-8"),
            },
            "index": {
                "path": index_path,
                "planned_obj": planned_index,
                "planned_bytes": index_bytes,
            },
            "context": {
                "path": os.path.join(project_dir, "context.md"),
                "plan": ctx_plan,
            },
        },
    }


def _write_if_changed(path, planned_bytes):
    """Semantic no-op comparison (design doc section 12 step 7): if the file
    already exists and its bytes are byte-identical to `planned_bytes`, write
    NOTHING -- no temp file, no rename, so its mtime never advances. Otherwise
    atomically replace it and report whether the file was created or updated."""
    existing = None
    try:
        with open(path, "rb") as fh:
            existing = fh.read()
    except FileNotFoundError:
        existing = None
    if existing is not None and existing == planned_bytes:
        return {"path": path, "written": False, "reason": "noop"}
    atomic_io.write_atomic(path, planned_bytes)
    return {
        "path": path,
        "written": True,
        "reason": "created" if existing is None else "updated",
    }


def _write_context(context_artifact, conflicts):
    """Write context.md per its projection plan. create/update/adopt carry the
    rendered `text` (UTF-8 encoded, then byte-compared like any other artifact);
    `noop` writes nothing; `conflict` (e.g. a markerless hand-authored file)
    writes nothing and appends its code to `conflicts` -- so a context conflict
    still lets map + index write (per-file atomicity, not cross-file)."""
    path = context_artifact["path"]
    plan = context_artifact["plan"]
    action = plan["action"]
    if action in ("create", "update", "adopt"):
        return _write_if_changed(path, plan["text"].encode("utf-8"))
    if action == "noop":
        return {"path": path, "written": False, "reason": "noop"}
    # action == "conflict"
    conflicts.append({"code": plan["code"], "artifact": "context.md"})
    return {"path": path, "written": False, "reason": "conflict"}


def apply(notes_home, project_slug, repo_roots=None, adopt_context_md=False,
          github_adapter=None):
    """Acquire the project single-writer lock, build the full plan inside it,
    and atomically write only the artifacts whose planned bytes differ from
    disk, in the fixed order map -> index -> context (design doc section 12
    step 7: the persisted map marker is source authority; generated outputs
    follow). Per-file atomicity only -- there is no cross-file atomicity. The
    lock is released on completion or exception via ProjectLock's context
    manager."""
    cdir = config.context_dir(notes_home, project_slug)
    with lock.ProjectLock(cdir, "apply"):
        plan = build_plan(notes_home, project_slug, repo_roots,
                          adopt_context_md, github_adapter)
        if not plan["ok"]:
            return {"ok": False, "findings": plan["findings"],
                    "conflicts": plan.get("conflicts", []), "writes": []}
        writes = []
        art = plan["artifacts"]
        writes.append(_write_if_changed(
            art["map"]["path"], art["map"]["planned_bytes"]))      # map FIRST
        writes.append(_write_if_changed(
            art["index"]["path"], art["index"]["planned_bytes"]))  # index SECOND
        conflicts = list(plan.get("conflicts", []))
        writes.append(_write_context(art["context"], conflicts))   # context THIRD
        return {"ok": True, "findings": plan["findings"],
                "conflicts": conflicts, "writes": writes}
