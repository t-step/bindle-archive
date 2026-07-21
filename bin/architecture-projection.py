#!/usr/bin/env python3
# bin/architecture-projection.py
"""architecture-projection.py -- CLI entry point for Bindle's architecture
projection (issue #374 child D slice D5, epic #141). Thin per the #180
adapter pattern: argument parsing, JSON/text rendering, and dispatch into
architecture.project. No domain logic lives here.

WHY NOT `bin/architecture.py`. The domain package is `bin/architecture/`,
and a regular package SHADOWS a sibling module of the same name -- so
`bin/architecture.py` could never be imported, only executed by path. Worse,
`bin/check-finding-codes.py` governs a surface by `os.walk`ing the
directories named in its coverage file's `sources`, and a walk over a plain
FILE yields nothing: every finding code emitted from `bin/architecture.py`
would have been silently ungoverned. The hyphenated name sidesteps both.
(`bin/context-graph.py` gets this for free -- its package is spelled
`context_graph`, so the two names never collided.)

FINDING CODES ARE DEFINED IN THE PACKAGE, NOT HERE, for the same reason:
this file is not walked by the coverage gate, so a code string invented in
it would escape the ledger. Every code this CLI renders is imported from
`architecture.project` or raised by `architecture.state`. `E_USAGE` and
`E_LOCK_CONTENTION` are the two exceptions and both are CLI-layer transport
errors that describe an invocation rather than a document -- the same two
`bin/context-graph.py` renders.

#374 slices D5a-D5c implement the whole loop: `init` and `config
status|validate|add-binding` (the initialization and configuration
boundary, which had NO implementation before D5a -- `architecture.state`
validated a config that nothing authored), then `preview`, `confirm` and
`apply`.

THE TOKEN ROUND TRIP HAS NO PYTHON PRECEDENT IN THIS REPO.
`bin/context-graph.py`'s `confirm` takes `--candidate-key`/`--decision`
and its `apply` takes no token at all; the `--approval-token` idiom exists
only in the bash release scripts, and `planner.py` cites it as an ANALOGY.
So `preview` prints a plan fingerprint, `confirm` checks a held one
against the current plan and reports the confirmation policy, and `apply`
takes it back as `--approval-token`. The token is never persisted -- #230
bars it from `apply-state.json` -- so re-running `preview` is always a
legal way to recover one.

Exit codes: 0 success (including a `config validate` run that found zero
findings); 1 a domain error's findings list was rendered instead of a
traceback -- architecture.state.ArchStateError and its subclasses
(ConfigInvalidError, ConfigUnreadableError), lock.LockContention, or a
non-empty findings list from `config validate`; 2 argparse usage error --
unchanged stdlib behavior, not implemented here.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from architecture import loop
from architecture import preview
from architecture import project
from architecture import state
from context_graph import config as ctx_config
from context_graph import lock


def _emit(obj, fmt):
    if fmt == "text":
        _emit_text(obj)
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))


def _emit_text(obj):
    # The preview shape is checked BEFORE the findings shape. A successful
    # preview carries `findings: []`, which the empty-findings branch below
    # would render as "ok: no findings" -- hiding the entire plan behind a
    # cheerful one-liner.
    # Order matters: a confirm result IS a preview result plus three
    # fields, and an apply result carries the whole preview under
    # `preview`. Checking the preview shape first would render either one
    # as a plain preview and drop the verdict the operator ran the verb
    # for.
    if "confirmed" in obj:
        _emit_text_confirm(obj)
        return
    if "status" in obj and "writes" in obj:
        _emit_text_apply(obj)
        return
    if "fingerprint" in obj and "entries" in obj:
        _emit_text_preview(obj)
        return
    findings = obj.get("findings")
    if findings:
        for f in findings:
            loc = ""
            if f.get("index") is not None:
                loc += " index=%d" % f["index"]
            if f.get("field"):
                loc += " field=%s" % f["field"]
            print("%s:%s %s" % (f["code"], loc, f["message"]))
    elif findings == []:
        print("ok: no findings")
    elif "config" in obj:
        _emit_text_config(obj)
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))


def _emit_text_preview(obj):
    if not obj["ok"]:
        for f in obj["findings"]:
            print("%s: %s" % (f["code"], f["message"]))
        return
    print("architecture preview (project %s)" % obj["project_id"])
    print("fingerprint: %s" % obj["fingerprint"])
    print("entries: %d, deferred: %d, over-cap: %d"
          % (len(obj["entries"]), len(obj["deferred"]),
             len(obj["over_cap"])))
    print("bindings:")
    for binding_id, info in sorted(obj["graph"]["bindings"].items()):
        print("  %s: %s (%s)"
              % (binding_id, info["status"], info["freshness"]))
    if obj["entries"]:
        print("plan:")
        for entry in obj["entries"]:
            print("  [%s/%s] %s -> %s%s"
                  % (entry["identity_outcome"], entry["note_state"],
                     entry["candidate_key"], entry["note_path"],
                     " (over cap)" if entry["over_cap"] else ""))
    if obj["deferred"]:
        print("deferred (reported, never projected):")
        for entry in obj["deferred"]:
            print("  [%s] %s: %s"
                  % (entry["outcome"], entry["candidate_key"],
                     entry["reason"]))
    if obj["findings"]:
        print("findings:")
        for f in obj["findings"]:
            print("  %s: %s" % (f["code"], f["message"]))


def _emit_text_confirm(obj):
    print("confirmed: %s" % ("yes" if obj["confirmed"] else "NO"))
    print("expected fingerprint: %s" % obj["expected_fingerprint"])
    print("current fingerprint:  %s" % obj["fingerprint"])
    if obj["requires_confirmation"]:
        print("this plan requires explicit confirmation:")
        for reason in obj["confirmation_reasons"]:
            print("  %s: %s" % (reason["reason"], reason["detail"]))
    else:
        print("no confirmation-policy trigger fired for this plan")
    if obj["findings"]:
        print("findings:")
        for f in obj["findings"]:
            print("  %s: %s" % (f["code"], f["message"]))


def _emit_text_apply(obj):
    print("status: %s" % obj["status"])
    if obj.get("resumed"):
        print("resumed a run that did not finish")
    print("writes: %d" % len(obj["writes"]))
    for write in obj["writes"]:
        print("  wrote %s" % write["note_path"])
    for label in ("conflicts", "orphans"):
        rows = obj.get(label) or []
        if rows:
            print("%s: %d" % (label, len(rows)))
            for row in rows:
                print("  %s" % (row.get("note_path") or row))
    if obj.get("findings"):
        print("findings:")
        for f in obj["findings"]:
            print("  %s: %s" % (f["code"], f["message"]))


def _emit_text_config(obj):
    cfg = obj["config"]
    if "created" in obj:
        print("%s architecture projection for project %s"
              % ("created" if obj["created"] else "already configured",
                 cfg["project_slug"]))
    print("project_id: %s" % cfg["project_id"])
    print("projection_schema_version: %d" % cfg["projection_schema_version"])
    print("bindings: %d" % len(cfg["bindings"]))
    print("caps: max_nodes=%d over_cap_behavior=%s"
          % (cfg["caps"]["max_nodes"], cfg["caps"]["over_cap_behavior"]))
    print("thresholds: high=%s low=%s"
          % (cfg["thresholds"]["high"], cfg["thresholds"]["low"]))
    print("diff_size_confirmation_limit: %d"
          % cfg["diff_size_confirmation_limit"])
    exclusions = cfg.get("exclusions") or []
    print("exclusions: %d" % len(exclusions))
    for pattern in exclusions:
        print("  %s" % pattern)
    if "lock" in obj:
        print("lock: %s" % (obj["lock"] if obj["lock"] else "none"))


def _error_findings(code, message, **extra):
    d = {"code": code, "message": message, "index": None, "field": None}
    d.update(extra)
    return [d]


def _add_common_args(p):
    p.add_argument("--notes-home", required=True, metavar="PATH")
    p.add_argument("--project", required=True, metavar="SLUG")
    p.add_argument("--format", choices=["json", "text"], default="json")


def _add_graph_args(p):
    """The three verbs that RUN the chain take identical inputs.

    Not a stylistic dedupe: preview, confirm and apply must each be able
    to rebuild the SAME plan, and every one of these arguments feeds a
    fingerprint term. A flag offered to one verb and not the others would
    make the token they exchange unreproducible."""
    _add_common_args(p)
    p.add_argument(
        "--graph", action="append", default=[], metavar="BINDING_ID=PATH",
        help="repeatable; BINDING_ID must be a configured binding")
    p.add_argument("--provider-name", default=None)
    p.add_argument("--provider-version", default=None)
    p.add_argument(
        "--decided-at", default=None, metavar="TIMESTAMP",
        help="UTC timestamp recorded on any identity allocated by this run")


def cmd_init(args):
    try:
        cfg, created = project.init_project(
            args.notes_home, args.project,
            display_name=args.display_name,
            max_nodes=args.max_nodes,
            high=args.threshold_high,
            low=args.threshold_low,
            diff_size_confirmation_limit=args.diff_size_confirmation_limit)
    except state.ArchStateError as exc:
        _emit({"findings": exc.findings}, args.format)
        return 1
    except lock.LockContention as exc:
        _emit({"findings": _error_findings(
            "E_LOCK_CONTENTION", str(exc), owner=exc.owner)}, args.format)
        return 1
    _emit({"created": created, "config": cfg}, args.format)
    return 0


def cmd_config_status(args):
    path = project.config_path(args.notes_home, args.project)
    try:
        cfg = project.load_config(path)
    except state.ArchStateError as exc:
        _emit({"findings": exc.findings}, args.format)
        return 1
    if cfg is None:
        _emit({"findings": _error_findings(
            project.E_CONFIG_MISSING,
            "no architecture configuration at %r" % (path,))}, args.format)
        return 1
    pdir = ctx_config.project_dir(args.notes_home, args.project)
    _emit({"config": cfg, "config_path": path,
           "lock": lock.read_owner(lock.lock_path(pdir))}, args.format)
    return 0


def cmd_config_validate(args):
    try:
        findings = project.validate(args.notes_home, args.project)
    except state.ArchStateError as exc:
        _emit({"findings": exc.findings}, args.format)
        return 1
    _emit({"findings": findings}, args.format)
    return 1 if findings else 0


def cmd_config_add_binding(args):
    try:
        cfg, binding = project.add_binding(
            args.notes_home, args.project, args.alias,
            binding_id=args.binding_id)
    except state.ArchStateError as exc:
        _emit({"findings": exc.findings}, args.format)
        return 1
    except lock.LockContention as exc:
        _emit({"findings": _error_findings(
            "E_LOCK_CONTENTION", str(exc), owner=exc.owner)}, args.format)
        return 1
    _emit({"binding": binding, "config": cfg}, args.format)
    return 0


def _parse_graphs(pairs):
    graphs = {}
    for pair in pairs or []:
        binding_id, sep, path = pair.partition("=")
        if not sep:
            raise ValueError(
                "--graph must be BINDING_ID=PATH, got %r" % (pair,))
        graphs[binding_id] = path
    return graphs


def cmd_preview(args):
    try:
        graphs = _parse_graphs(args.graph)
    except ValueError as exc:
        _emit({"findings": _error_findings("E_USAGE", str(exc))}, args.format)
        return 1
    out = preview.build_preview(
        args.notes_home, args.project, graphs,
        provider=({"name": args.provider_name,
                   "version": args.provider_version}
                  if args.provider_name else None),
        decided_at=args.decided_at)
    _emit(out, args.format)
    # Deferred (contested/routed) candidates are REPORTED, not a run
    # failure -- the same stance bin/context-graph.py takes on conflicts.
    return 0 if out["ok"] else 1


def cmd_confirm(args):
    try:
        graphs = _parse_graphs(args.graph)
    except ValueError as exc:
        _emit({"findings": _error_findings("E_USAGE", str(exc))}, args.format)
        return 1
    out = loop.confirm(
        args.notes_home, args.project, graphs, args.fingerprint,
        provider=({"name": args.provider_name,
                   "version": args.provider_version}
                  if args.provider_name else None),
        decided_at=args.decided_at)
    _emit(out, args.format)
    return 0 if out["confirmed"] else 1


def cmd_apply(args):
    try:
        graphs = _parse_graphs(args.graph)
    except ValueError as exc:
        _emit({"findings": _error_findings("E_USAGE", str(exc))}, args.format)
        return 1
    try:
        out = loop.apply_confirmed(
            args.notes_home, args.project, graphs, args.approval_token,
            provider=({"name": args.provider_name,
                       "version": args.provider_version}
                      if args.provider_name else None),
            decided_at=args.decided_at,
            projected_at=args.projected_at)
    except lock.LockContention as exc:
        _emit({"findings": _error_findings(
            "E_LOCK_CONTENTION", str(exc), owner=exc.owner)}, args.format)
        return 1
    _emit(out, args.format)
    return 0 if out["ok"] else 1


def _positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1, got %r" % (text,))
    return value


def _unit_interval(text):
    value = float(text)
    if not 0.0 <= value <= 1.0:
        raise argparse.ArgumentTypeError(
            "must be between 0 and 1 inclusive, got %r" % (text,))
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser(
        "init", help="allocate project identity, create config.json")
    _add_common_args(p_init)
    p_init.add_argument("--display-name", default=None)
    p_init.add_argument("--max-nodes", type=_positive_int, default=None,
                        help="note-count cap; binds CREATION only "
                             "(default %d)" % project.DEFAULT_MAX_NODES)
    p_init.add_argument("--threshold-high", type=_unit_interval, default=None,
                        help="default %s" % project.DEFAULT_THRESHOLD_HIGH)
    p_init.add_argument("--threshold-low", type=_unit_interval, default=None,
                        help="default %s" % project.DEFAULT_THRESHOLD_LOW)
    p_init.add_argument(
        "--diff-size-confirmation-limit", type=int, default=None,
        help="default %d" % project.DEFAULT_DIFF_SIZE_CONFIRMATION_LIMIT)
    p_init.set_defaults(func=cmd_init)

    p_config = sub.add_parser("config", help="read project configuration")
    config_sub = p_config.add_subparsers(dest="config_command", required=True)

    p_status = config_sub.add_parser(
        "status", help="read-only config + lock status")
    _add_common_args(p_status)
    p_status.set_defaults(func=cmd_config_status)

    p_validate = config_sub.add_parser(
        "validate", help="read-only config validation")
    _add_common_args(p_validate)
    p_validate.set_defaults(func=cmd_config_validate)

    p_add = config_sub.add_parser(
        "add-binding", help="add one repository binding")
    _add_common_args(p_add)
    p_add.add_argument("--alias", required=True)
    p_add.add_argument(
        "--binding-id", default=None,
        help="the interchange document's own binding_id; minted when "
             "omitted. A document whose binding_id is not configured loads "
             "as `deconfigured` with no facts.")
    p_add.set_defaults(func=cmd_config_add_binding)

    p_preview = sub.add_parser(
        "preview", help="read-only projection preview; writes nothing")
    _add_graph_args(p_preview)
    p_preview.set_defaults(func=cmd_preview)

    p_confirm = sub.add_parser(
        "confirm",
        help="check a preview fingerprint against the current plan and "
             "report the confirmation policy; writes nothing")
    _add_graph_args(p_confirm)
    p_confirm.add_argument(
        "--fingerprint", required=True, metavar="TOKEN",
        help="the plan fingerprint `preview` printed")
    p_confirm.set_defaults(func=cmd_confirm)

    p_apply = sub.add_parser(
        "apply", help="write the confirmed plan under the project lock")
    _add_graph_args(p_apply)
    p_apply.add_argument(
        "--approval-token", required=True, metavar="TOKEN",
        help="the plan fingerprint `preview` printed. apply re-plans and "
             "aborts as stale_preview if the inputs moved since")
    p_apply.add_argument(
        "--projected-at", default=None, metavar="TIMESTAMP",
        help="UTC timestamp recorded on each projected node")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
