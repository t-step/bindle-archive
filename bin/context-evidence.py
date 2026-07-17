#!/usr/bin/env python3
"""context-evidence.py — normalize typed evidence references (issue #181,
epic #140).

Three commands, all read-only / stdlib-only / network-free:

  context-evidence.py normalize --project-id PROJECT_ID [--repository OWNER/REPO]
      [--binding-id BINDING_ID ...] [--kind-hint github_issue|github_pr]
      [--check-existence] [--notes-home DIR] [--project-dir DIR] [--repo-root DIR]
      --value VALUE
      Normalize one evidence atom. Prints the result object as JSON.

  context-evidence.py normalize-field --project-id PROJECT_ID
      [--repository OWNER/REPO] [--binding-id BINDING_ID ...]
      [--check-existence] [--notes-home DIR] [--project-dir DIR] [--repo-root DIR]
      --value VALUE
      Tokenize a complete comma-separated evidence field (respecting
      Markdown-link and backtick spans as non-separator regions) and
      normalize each atom. Prints {"status": "field_ok", "results": [...]}
      or {"status": "field_rejected", "reason": ...} as JSON.

  context-evidence.py normalize-batch --project-id PROJECT_ID
      [--repository OWNER/REPO] [--binding-id BINDING_ID ...] --input PATH
      Normalize each {"value": ...} record of a JSONL file, one atom per
      line. Prints one JSON result object per line, in input order.

`--binding-id` may be repeated for a project with multiple configured
repository bindings; zero bindings means a repositoryless project (generic
document references normalize to the project-local form), exactly one
means the unique configured binding, and more than one makes any generic
document reference ambiguous (status "unresolved", reason
"binding_ambiguous") -- this CLI has no default-binding selection of its
own to offer.

`--check-existence` adds a non-authoritative `"exists"` boolean to any
normalized session/handoff/document result, checked against
--notes-home/--project-dir (session/handoff) or --repo-root (repository
document); never affects identity or status.

Grammar and identity rules are owned by context_graph.evidence; this file
is argument parsing and JSON rendering only.

Exit codes: 0 ok, 1 I/O error (e.g. --input unreadable), 64 usage error
(malformed/repository-shaped --project-id or --binding-id).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from context_graph import evidence
from context_graph import ids


def _check_existence(result, notes_home, project_dir, repo_root):
    if result.get("status") != "normalized":
        return result
    kind = result.get("kind")
    path = result.get("path")
    if kind in ("session", "handoff"):
        base = project_dir or notes_home
        if base is None:
            return result
        result = dict(result)
        result["exists"] = os.path.exists(os.path.join(base, path))
    elif kind in ("document_repository", "document_project_local"):
        base = repo_root if kind == "document_repository" else (project_dir or notes_home)
        if base is None:
            return result
        result = dict(result)
        result["exists"] = os.path.exists(os.path.join(base, path))
    return result


def _add_context_args(parser):
    parser.add_argument("--project-id", required=True, metavar="PROJECT_ID")
    parser.add_argument("--repository", default=None, metavar="OWNER/REPO")
    parser.add_argument("--binding-id", action="append", default=[], dest="binding_ids",
                         metavar="BINDING_ID",
                         help="may be repeated; zero means repositoryless, "
                              "more than one makes generic document references ambiguous")
    parser.add_argument("--notes-home", default=None, metavar="DIR")
    parser.add_argument("--project-dir", default=None, metavar="DIR")
    parser.add_argument("--repo-root", default=None, metavar="DIR")


def _validate_binding_ids(binding_ids):
    for binding_id in binding_ids:
        if not ids.BINDING_ID_RE.match(binding_id):
            raise evidence.MalformedIdentityError(
                "invalid --binding-id %r: must be repository-binding:<32-lowercase-hex>"
                % (binding_id,)
            )


def cmd_normalize(args):
    try:
        _validate_binding_ids(args.binding_ids)
        result = evidence.normalize(
            args.value,
            args.project_id,
            repository=args.repository,
            binding_ids=args.binding_ids,
            kind_hint=args.kind_hint,
        )
    except evidence.MalformedIdentityError as exc:
        print("context-evidence: %s" % exc, file=sys.stderr)
        return 64
    if args.check_existence:
        result = _check_existence(result, args.notes_home, args.project_dir, args.repo_root)
    print(json.dumps(result))
    return 0


def cmd_normalize_field(args):
    try:
        _validate_binding_ids(args.binding_ids)
        result = evidence.normalize_field(
            args.value,
            args.project_id,
            repository=args.repository,
            binding_ids=args.binding_ids,
        )
    except evidence.MalformedIdentityError as exc:
        print("context-evidence: %s" % exc, file=sys.stderr)
        return 64
    if args.check_existence and result.get("status") == "field_ok":
        result = dict(result)
        result["results"] = [
            _check_existence(r, args.notes_home, args.project_dir, args.repo_root)
            for r in result["results"]
        ]
    print(json.dumps(result))
    return 0


def cmd_normalize_batch(args):
    try:
        _validate_binding_ids(args.binding_ids)
    except evidence.MalformedIdentityError as exc:
        print("context-evidence: %s" % exc, file=sys.stderr)
        return 64
    try:
        with open(args.input, encoding="utf-8") as fh:
            lines = [line for line in (l.strip() for l in fh) if line]
    except OSError as exc:
        print("context-evidence: cannot read --input: %s" % exc, file=sys.stderr)
        return 1
    try:
        records = [json.loads(line) for line in lines]
    except json.JSONDecodeError as exc:
        print("context-evidence: malformed JSONL in --input: %s" % exc, file=sys.stderr)
        return 1
    try:
        results = evidence.normalize_batch(
            records, args.project_id, repository=args.repository,
            binding_ids=args.binding_ids,
        )
    except evidence.MalformedIdentityError as exc:
        print("context-evidence: %s" % exc, file=sys.stderr)
        return 64
    for result in results:
        print(json.dumps(result))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_norm = sub.add_parser("normalize", help="normalize one evidence atom")
    _add_context_args(p_norm)
    p_norm.add_argument("--kind-hint", choices=["github_issue", "github_pr"], default=None)
    p_norm.add_argument("--check-existence", action="store_true")
    p_norm.add_argument("--value", required=True)
    p_norm.set_defaults(func=cmd_normalize)

    p_field = sub.add_parser("normalize-field",
                             help="normalize a complete comma-separated evidence field")
    _add_context_args(p_field)
    p_field.add_argument("--check-existence", action="store_true")
    p_field.add_argument("--value", required=True)
    p_field.set_defaults(func=cmd_normalize_field)

    p_batch = sub.add_parser("normalize-batch",
                             help="normalize each {\"value\": ...} record of a JSONL file")
    _add_context_args(p_batch)
    p_batch.add_argument("--input", required=True, metavar="PATH")
    p_batch.set_defaults(func=cmd_normalize_batch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
