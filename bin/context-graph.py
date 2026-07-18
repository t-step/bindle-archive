#!/usr/bin/env python3
# bin/context-graph.py
"""context-graph.py — CLI entry point for Bindle's context graph (issue
#191, epic #140). Thin per the #180 adapter pattern: argument parsing, JSON
rendering, dispatch into context_graph.config / context_graph.lock. No
independent domain logic lives here.

#191 implements: `init`, `config status`, `config validate`, `config
add-repository`, `config update-repository`, `config remove-repository`,
`config set-default`, `config break-lock` — the initialization and
configuration boundary frozen by
docs/design/2026-07-17-context-graph-foundation.md section 4. #183 adds
`preview` -- the read-only, write-nothing deterministic compiler. #184 adds
`candidates` (read-only union of live anchor candidates and ledger
history), `propose` (validate an edge proposal against a fresh preview,
writes nothing, takes no lock), and `confirm` (revalidate against the
current graph and append exactly one judgment event under the
single-writer "confirm" lock). #185 adds `apply` -- recompute a fresh
preview, reduce #184's judgment ledger against it, and atomically write
map.md/index.json/context.md under the single-writer "apply" lock. The
remaining verb shown in that design (bare `validate`/`status`) belongs to
#185/#186 and is not defined here. `preview` intentionally has no
`--adopt-context-md` flag -- that flag previews a `context.md` diff, which
is `apply`'s own safety projection, not part of #183's own scope.

Exit codes: 0 success (including a `config validate` run that found zero
findings, a `preview` run whose conflicts list is non-empty, or a
`candidates` run with an empty rows list -- these are reported, not run
failures); 1 a domain error's findings list was rendered instead of a
traceback -- config.ConfigError (and subclasses, e.g. ConfigInvalidError,
ConfigMissingError) from any config.py call, context_graph.compiler.CompilerError
from `preview` (missing/malformed configuration, an unreadable map),
review.ReviewError from `candidates`/`propose`/`confirm` (review._preview()
wraps the same underlying CompilerError before it reaches the CLI),
lock.LockContention on `init`, a
non-empty findings list from `config validate`, `propose` (no valid
candidate), `confirm` (rejected/stale/invalid), or `apply` (ok=False, or
ok=True with a non-empty conflicts list, e.g. an unmanaged context.md); 2
argparse usage error (e.g. a missing required argument) -- unchanged
stdlib behavior, not implemented by this CLI.
"""
import argparse
import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(__file__))

from context_graph import apply as apply_mod
from context_graph import atomic_io
from context_graph import compiler
from context_graph import config
from context_graph import lock
from context_graph import review


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
    elif "nodes" in obj and "edges" in obj:
        _emit_text_preview(obj)
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))


def _emit_text_preview(preview):
    print("context-graph preview (project %s)" % preview["project_id"])
    print("nodes: %d, edges: %d, identity-anchor candidates: %d, conflicts: %d"
          % (len(preview["nodes"]), len(preview["edges"]),
             len(preview["identity_anchor_candidates"]), len(preview["conflicts"])))
    print("coverage:")
    for source, state in sorted(preview["coverage"].items()):
        print("  %s: %s" % (source, state))
    if preview["identity_anchor_candidates"]:
        print("unanchored entries:")
        for c in preview["identity_anchor_candidates"]:
            print("  [%s/%s] %s" % (c["section"], c["entry_kind"], c["display_claim"]))
    if preview["conflicts"]:
        print("conflicts:")
        for f in preview["conflicts"]:
            loc = " line=%s" % f["line"] if f.get("line") else ""
            print("  [%s]%s %s" % (f["code"], loc, f["message"]))


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
        cfg, created = config.init_project(args.notes_home, args.project, args.display_name)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e), owner=e.owner)}, args.format)
        return 1
    _emit({"created": created, "config": cfg}, args.format)
    return 0


def cmd_config_status(args):
    path = config.config_path(args.notes_home, args.project)
    try:
        cfg = config.load_config(path)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    cdir = config.context_dir(args.notes_home, args.project)
    owner = lock.read_owner(lock.lock_path(cdir))
    owner_live = None
    if isinstance(owner, dict) and "pid" in owner and owner.get("hostname") == socket.gethostname():
        owner_live = lock.pid_is_running(owner["pid"])
    pdir = config.project_dir(args.notes_home, args.project)
    orphaned_temp_files = _find_orphaned_temp_files((pdir, cdir))
    _emit({"config": cfg, "lock": owner, "lock_owner_live": owner_live,
           "orphaned_temp_files": orphaned_temp_files}, args.format)
    return 0


def _find_orphaned_temp_files(directories):
    """Report (never delete -- design doc section 12, orphan cleanup is
    passive) files left behind by a crash between atomic_io.write_atomic's
    tempfile.mkstemp() call and its os.replace(). Matches that call's exact
    convention: prefix=".tmp-", no fixed suffix, created directly in the
    directory that holds the file it was standing in for."""
    found = set()
    for directory in directories:
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        for name in entries:
            if name.startswith(".tmp-"):
                candidate = os.path.join(directory, name)
                if os.path.isfile(candidate):
                    found.add(candidate)
    return sorted(found)


def cmd_config_validate(args):
    path = config.config_path(args.notes_home, args.project)
    try:
        cfg = config.load_config(path)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    if cfg is None:
        findings = _error_findings("E_CONFIG_MISSING", "no configuration found at %r" % (path,))
    else:
        findings = config.all_findings(cfg)
    _emit({"findings": findings}, args.format)
    return 1 if findings else 0


def cmd_config_add_repository(args):
    try:
        cfg, entry = config.add_repository(
            args.notes_home, args.project, args.alias, args.provider,
            coordinates=args.coordinates, local_checkout_path=args.local_checkout_path,
            is_default=args.default)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e), owner=e.owner)}, args.format)
        return 1
    _emit({"repository": entry, "config": cfg}, args.format)
    return 0


def cmd_config_update_repository(args):
    default = True if args.default else (False if args.no_default else None)
    try:
        cfg, entry = config.update_repository(
            args.notes_home, args.project, args.binding_id, alias=args.alias,
            coordinates=args.coordinates, local_checkout_path=args.local_checkout_path,
            default=default)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e), owner=e.owner)}, args.format)
        return 1
    _emit({"repository": entry, "config": cfg}, args.format)
    return 0


def cmd_config_remove_repository(args):
    try:
        cfg, removed = config.remove_repository(args.notes_home, args.project, args.binding_id)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e), owner=e.owner)}, args.format)
        return 1
    _emit({"removed": removed, "config": cfg}, args.format)
    return 0


def cmd_config_set_default(args):
    try:
        cfg, entry = config.set_default(args.notes_home, args.project, args.binding_id)
    except config.ConfigError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    except lock.LockContention as e:
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e), owner=e.owner)}, args.format)
        return 1
    _emit({"repository": entry, "config": cfg}, args.format)
    return 0


def _parse_repo_roots(pairs):
    roots = {}
    for pair in pairs or []:
        alias, sep, path = pair.partition("=")
        if not sep:
            raise ValueError("--repo-root must be ALIAS=PATH, got %r" % (pair,))
        roots[alias] = path
    return roots


def cmd_preview(args):
    try:
        repo_roots = _parse_repo_roots(args.repo_root)
    except ValueError as e:
        _emit({"findings": _error_findings("E_USAGE", str(e))}, args.format)
        return 1
    try:
        preview = compiler.compile_preview(args.notes_home, args.project, repo_roots=repo_roots)
    except compiler.CompilerError as e:
        _emit({"findings": e.findings}, args.format)
        return 1
    _emit(preview, args.format)
    return 0


def cmd_candidates(args):
    try:
        out = review.list_candidates(args.notes_home, args.project,
                                      subject_type=args.subject_type, status=args.status)
    except review.ReviewError as exc:
        _emit({"findings": exc.findings}, args.format)
        return 1
    _emit(out, args.format)
    return 0


def cmd_propose(args):
    try:
        proposal = atomic_io.read_json(args.input)
    except (OSError, ValueError) as exc:
        _emit({"findings": _error_findings("E_INPUT_UNREADABLE", str(exc))}, args.format)
        return 1
    try:
        out = review.propose(args.notes_home, args.project, proposal)
    except review.ReviewError as exc:
        _emit({"findings": exc.findings}, args.format)
        return 1
    _emit(out, args.format)
    return 0 if out["candidate"] is not None else 1


def cmd_confirm(args):
    proposal = None
    if args.input:
        try:
            proposal = atomic_io.read_json(args.input)
        except (OSError, ValueError) as exc:
            _emit({"findings": _error_findings("E_INPUT_UNREADABLE", str(exc))}, args.format)
            return 1
    try:
        out = review.confirm(args.notes_home, args.project, args.candidate_key,
                              args.decision, proposal=proposal)
    except review.ReviewError as exc:
        _emit({"findings": exc.findings}, args.format)
        return 1
    _emit(out, args.format)
    return 0 if not out["findings"] else 1


def cmd_apply(args):
    try:
        repo_roots = _parse_repo_roots(args.repo_root)
    except ValueError as e:
        _emit({"findings": _error_findings("E_USAGE", str(e))}, args.format)
        return 1
    out = apply_mod.apply(args.notes_home, args.project,
                          repo_roots=repo_roots,
                          adopt_context_md=args.adopt_context_md)
    _emit(out, args.format)
    return 0 if out["ok"] and not out["conflicts"] else 1


def cmd_config_break_lock(args):
    cdir = config.context_dir(args.notes_home, args.project)
    if not args.force:
        owner = lock.read_owner(lock.lock_path(cdir))
        _emit({"findings": _error_findings(
            "E_LOCK_BREAK_NOT_CONFIRMED",
            "config break-lock requires --force to confirm (current owner: %r)" % (owner,),
            owner=owner)}, args.format)
        return 1
    owner = lock.break_lock(cdir)
    _emit({"removed_owner": owner}, args.format)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="allocate project identity, create config.json")
    _add_common_args(p_init)
    p_init.add_argument("--display-name", default=None)
    p_init.set_defaults(func=cmd_init)

    p_preview = sub.add_parser(
        "preview", help="read-only deterministic compiler preview (#183)")
    _add_common_args(p_preview)
    p_preview.add_argument(
        "--repo-root", action="append", default=[], metavar="ALIAS=PATH",
        help="repeatable; ALIAS must be a configured repository alias")
    p_preview.set_defaults(func=cmd_preview)

    p_candidates = sub.add_parser(
        "candidates", help="list candidates (union of live anchors + ledger, #184)")
    _add_common_args(p_candidates)
    p_candidates.add_argument("--subject-type", choices=["edge", "identity_anchor"], default=None)
    p_candidates.add_argument(
        "--status", choices=["pending", "accepted", "rejected", "retired"], default=None)
    p_candidates.set_defaults(func=cmd_candidates)

    p_propose = sub.add_parser(
        "propose", help="validate an edge proposal against a fresh preview; writes nothing (#184)")
    _add_common_args(p_propose)
    p_propose.add_argument("--input", required=True, metavar="PATH",
                            help="path to a proposal.json envelope")
    p_propose.set_defaults(func=cmd_propose)

    p_confirm = sub.add_parser(
        "confirm", help="append one judgment event under the single-writer lock (#184)")
    _add_common_args(p_confirm)
    p_confirm.add_argument("--candidate-key", required=True)
    p_confirm.add_argument("--decision", required=True, choices=["accepted", "rejected", "retired"])
    p_confirm.add_argument("--input", default=None, metavar="PATH",
                            help="proposal.json (required for edge accepted|rejected)")
    p_confirm.set_defaults(func=cmd_confirm)

    p_apply = sub.add_parser(
        "apply", help="recompute, validate, and atomically write map/index/context (#185)")
    _add_common_args(p_apply)
    p_apply.add_argument(
        "--repo-root", action="append", default=[], metavar="ALIAS=PATH",
        help="repeatable; ALIAS must be a configured repository alias")
    p_apply.add_argument("--adopt-context-md", action="store_true",
                         help="adopt a still-markerless context.md, refusing if it gained markers")
    p_apply.set_defaults(func=cmd_apply)

    p_config = sub.add_parser("config", help="read or mutate project configuration")
    config_sub = p_config.add_subparsers(dest="config_command", required=True)

    p_status = config_sub.add_parser("status", help="read-only config + lock status")
    _add_common_args(p_status)
    p_status.set_defaults(func=cmd_config_status)

    p_validate = config_sub.add_parser("validate", help="read-only config validation")
    _add_common_args(p_validate)
    p_validate.set_defaults(func=cmd_config_validate)

    p_add = config_sub.add_parser("add-repository", help="add one repository binding")
    _add_common_args(p_add)
    p_add.add_argument("--alias", required=True)
    p_add.add_argument("--provider", required=True)
    p_add.add_argument("--coordinates", default=None)
    p_add.add_argument("--local-checkout-path", default=None)
    p_add.add_argument("--default", action="store_true")
    p_add.set_defaults(func=cmd_config_add_repository)

    p_update = config_sub.add_parser("update-repository", help="update one repository binding")
    _add_common_args(p_update)
    p_update.add_argument("--binding-id", required=True)
    p_update.add_argument("--alias", default=None)
    p_update.add_argument("--coordinates", default=None)
    p_update.add_argument("--local-checkout-path", default=None)
    default_group = p_update.add_mutually_exclusive_group()
    default_group.add_argument("--default", action="store_true")
    default_group.add_argument("--no-default", action="store_true")
    p_update.set_defaults(func=cmd_config_update_repository)

    p_remove = config_sub.add_parser("remove-repository", help="remove one repository binding")
    _add_common_args(p_remove)
    p_remove.add_argument("--binding-id", required=True)
    p_remove.set_defaults(func=cmd_config_remove_repository)

    p_default = config_sub.add_parser("set-default", help="set the unique default repository")
    _add_common_args(p_default)
    p_default.add_argument("--binding-id", required=True)
    p_default.set_defaults(func=cmd_config_set_default)

    p_break = config_sub.add_parser("break-lock", help="remove an existing .lock directly")
    _add_common_args(p_break)
    p_break.add_argument("--force", action="store_true")
    p_break.set_defaults(func=cmd_config_break_lock)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
