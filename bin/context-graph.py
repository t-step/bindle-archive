#!/usr/bin/env python3
# bin/context-graph.py
"""context-graph.py — CLI entry point for Bindle's context graph (issue
#191, epic #140). Thin per the #180 adapter pattern: argument parsing, JSON
rendering, dispatch into context_graph.config / context_graph.lock. No
independent domain logic lives here.

This issue (#191) implements exactly: `init`, `config status`, `config
validate`, `config add-repository`, `config update-repository`, `config
remove-repository`, `config set-default`, `config break-lock` — the
initialization and configuration boundary frozen by
docs/design/2026-07-17-context-graph-foundation.md section 4. The remaining
verbs shown there (`preview`, `candidates`, `propose`, `confirm`, `apply`,
bare `validate`/`status`) belong to #183/#184/#185/#186 and are not defined
here.

Exit codes: 0 success (including a `config validate` run that found zero
findings); 1 a domain error's findings list was rendered instead of a
traceback -- config.ConfigError (and subclasses, e.g. ConfigInvalidError,
ConfigMissingError) from any config.py call, lock.LockContention on
`init`, or a non-empty findings list from `config validate`; 2 argparse
usage error (e.g. a missing required argument) -- unchanged stdlib
behavior, not implemented by this CLI.
"""
import argparse
import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(__file__))

from context_graph import config
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
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))


def _error_findings(code, message):
    return [{"code": code, "message": message, "index": None, "field": None}]


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
        _emit({"findings": _error_findings("E_LOCK_CONTENTION", str(e))}, args.format)
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
    _emit({"config": cfg, "lock": owner, "lock_owner_live": owner_live}, args.format)
    return 0


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="allocate project identity, create config.json")
    _add_common_args(p_init)
    p_init.add_argument("--display-name", default=None)
    p_init.set_defaults(func=cmd_init)

    p_config = sub.add_parser("config", help="read or mutate project configuration")
    config_sub = p_config.add_subparsers(dest="config_command", required=True)

    p_status = config_sub.add_parser("status", help="read-only config + lock status")
    _add_common_args(p_status)
    p_status.set_defaults(func=cmd_config_status)

    p_validate = config_sub.add_parser("validate", help="read-only config validation")
    _add_common_args(p_validate)
    p_validate.set_defaults(func=cmd_config_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
