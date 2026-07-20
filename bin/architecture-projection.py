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

#374 slice D5a implements `init` and `config status|validate` -- the
initialization and configuration boundary, which had NO implementation
before this slice (`architecture.state` validated a config that nothing
authored). `preview`, `confirm` and `apply` are the projection loop and
land in the following slice; they are deliberately absent rather than
stubbed, so `--help` never advertises a verb that does nothing.

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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
