#!/usr/bin/env python3
"""map-entry-id.py — stable opaque identities for project-map entries
(issue #179, epic #140).

Two commands:

  map-entry-id.py allocate --project SLUG
      Print one newly allocated identity to stdout:
        context-node:<SLUG>:<32-lowercase-hex>
      The hex suffix comes from `secrets.token_hex(16)` — command-owned
      cryptographic entropy. Never reads or writes any file. The two
      authorized callers are the knowledge-promotion confirmed write (owned
      by #179, for newly promoted entries) and #184 anchor acceptance (for
      existing unanchored entries) — no other surface allocates an ID.

  map-entry-id.py validate --map PATH [--format text|json]
      Read-only. Parses a project-map.md and reports: anchored entries
      (deterministic discovery of persisted identities), unanchored
      entries, malformed markers, duplicate IDs, markers attached to an
      unsupported location (field lines, tension sides, prose), multiple
      identity markers on one entry, untyped retirement tombstones, and
      malformed/duplicate/self-referential/unresolved
      `bindle:superseded-by` metadata. Never writes; exits 1 if any
      error-severity finding is present, 0 otherwise (informational
      findings — unanchored entries, untyped legacy tombstones — never
      fail the run on their own).

Identity contract (frozen by #179):

  context-node:<creation-project-slug>:<32-lowercase-hex>

The slug is the project slug in effect when the entry was first anchored —
an opaque historical label, never rewritten, never re-derived from mutable
entry content (heading text, section, status, date, evidence, hashes).

Marker grammar:

  <!-- bindle:context-id: context-node:<slug>:<hex> -->
  <!-- bindle:superseded-by: context-node:<slug>:<hex> -->   (tombstones only, optional)

Placement (one identity per owner-curated top-level entry):

  Decision / Learning        -> on the `###` claim heading
  Single Assumption          -> on the top-level bullet
  Structured tension         -> on the parent top-level bullet (not its sides)
  Open question               -> on the top-level bullet
  Superseded (typed tombstone) -> `- <kind>: <claim> (retired YYYY-MM) ->
      <reason/replacement> <!-- bindle:context-id: <retired-id> -->
      [<!-- bindle:superseded-by: <replacement-id> -->]`
      kind is one of: decision, learning, assumption, tension, question.

Indented field lines (`why:`/`so:`/`revisit-when:`/`evidence:`) and tension
sides are structured content of the parent entry and never carry an
independent identity — a marker found there is malformed placement, reported
and never moved automatically.

Stdlib-only. No network, no subprocess, no writes of any kind.

Exit codes: 0 ok, 1 validation/read error, 64 usage error (bad --project).
"""
import argparse
import json
import re
import secrets
import sys

SCHEMA = "map-entry-id/v1"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ID_RE = re.compile(r"^context-node:([a-z0-9]+(?:-[a-z0-9]+)*):([0-9a-f]{32})$")

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
HEADING_RE = re.compile(r"^###\s")
TOP_BULLET_RE = re.compile(r"^-\s")
INDENT_BULLET_RE = re.compile(r"^[ \t]+-\s")
FIELD_RE = re.compile(r"^(why|so|revisit-when|evidence):")
COMMENT_RE = re.compile(r"<!--\s*(.*?)\s*-->")
TOMBSTONE_RE = re.compile(
    r"^-\s*(decision|learning|assumption|tension|question):\s*.+?"
    r"\s*\(retired\s+\d{4}-\d{2}\)\s*→\s*.+$"
)

SECTION_KEY = {
    "Brief": "brief",
    "Decisions": "decisions",
    "Learnings": "learnings",
    "Assumptions & tensions": "assumptions",
    "Open questions": "questions",
    "Superseded": "superseded",
}

# (section_key, line_role) -> the map-entry kind that role legitimately
# anchors an identity for. Anything else is an unsupported location.
ANCHOR_KIND = {
    ("decisions", "heading"): "decision",
    ("learnings", "heading"): "learning",
    ("assumptions", "top-bullet"): "assumption-or-tension",
    ("questions", "top-bullet"): "question",
    ("superseded", "top-bullet"): "superseded",
}


# --------------------------------------------------------------------------
# allocation
# --------------------------------------------------------------------------

def allocate_id(project_slug):
    """Allocate one new opaque identity. Command-owned entropy only — the
    caller (and never a model) supplies the project slug; the hex suffix is
    `secrets.token_hex(16)`, independent of claim text, section, status, and
    evidence. Raises ValueError for an invalid slug."""
    if not isinstance(project_slug, str) or not SLUG_RE.match(project_slug):
        raise ValueError("invalid --project slug %r (expected lowercase "
                          "kebab-case, e.g. 'bindle')" % (project_slug,))
    return "context-node:%s:%s" % (project_slug, secrets.token_hex(16))


# --------------------------------------------------------------------------
# marker scanning
# --------------------------------------------------------------------------

def _scan_comments(line):
    """[(key, value, raw)] for every `bindle:context-id`/`bindle:superseded-by`
    HTML comment on a line. Any other HTML comment (unknown bindle: key or a
    fully foreign comment) is user-owned and silently ignored — never
    reported, never touched."""
    out = []
    for m in COMMENT_RE.finditer(line):
        body = m.group(1)
        if body.startswith("bindle:context-id:"):
            out.append(("context-id", body[len("bindle:context-id:"):].strip(), m.group(0)))
        elif body.startswith("bindle:superseded-by:"):
            out.append(("superseded-by", body[len("bindle:superseded-by:"):].strip(), m.group(0)))
    return out


def _new_entry(section, role, line_no, text):
    return {"section": section, "role": role, "anchor_line": line_no,
            "anchor_text": text, "members": []}


def parse_map(text):
    """Split map.md text into logical entries: one per `###` heading or
    top-level `- ` bullet, with its field-lines/indented-bullets/other
    continuation lines attached as members. Pure — no I/O, no mutation."""
    entries = []
    section = None
    current = None

    def flush():
        if current is not None:
            entries.append(current)

    for i, line in enumerate(text.splitlines(), start=1):
        m = SECTION_RE.match(line)
        if m:
            flush()
            current = None
            section = SECTION_KEY.get(m.group(1).strip())
            continue
        if HEADING_RE.match(line):
            flush()
            current = _new_entry(section, "heading", i, line)
            continue
        if TOP_BULLET_RE.match(line):
            flush()
            current = _new_entry(section, "top-bullet", i, line)
            continue
        if INDENT_BULLET_RE.match(line):
            if current is not None:
                current["members"].append((i, line, "indented-bullet"))
            else:
                entries.append(_new_entry(section, "orphan", i, line))
            continue
        if FIELD_RE.match(line):
            if current is not None:
                current["members"].append((i, line, "field-line"))
            else:
                entries.append(_new_entry(section, "orphan", i, line))
            continue
        if line.strip() == "":
            continue
        if current is not None:
            current["members"].append((i, line, "continuation"))
        else:
            entries.append(_new_entry(section, "prose", i, line))
    flush()
    return entries


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate_map(text):
    """Read-only structural validation of map.md text. Returns a dict with
    `entries` (deterministic discovery: anchored + unanchored) and `issues`
    (error/info findings); `ok` is False iff any issue has severity "error"."""
    entries = parse_map(text)
    issues = []
    out_entries = []

    def issue(severity, code, line, message):
        issues.append({"severity": severity, "code": code, "line": line,
                       "message": message})

    # First pass: every well-formed context-id value found anywhere, for the
    # superseded-by "unresolved" cross-check.
    all_ids_found = set()
    for e in entries:
        for _key, value, _raw in _scan_comments(e["anchor_text"]):
            if _key == "context-id" and ID_RE.match(value):
                all_ids_found.add(value)
        for _ln, mtext, _role in e["members"]:
            for _key, value, _raw in _scan_comments(mtext):
                if _key == "context-id" and ID_RE.match(value):
                    all_ids_found.add(value)

    live_occurrences = {}
    tombstone_occurrences = {}

    for e in entries:
        section, role = e["section"], e["role"]
        anchor_line, anchor_text = e["anchor_line"], e["anchor_text"]
        kind = ANCHOR_KIND.get((section, role))

        anchor_cid = [c for c in _scan_comments(anchor_text) if c[0] == "context-id"]
        anchor_sb = [c for c in _scan_comments(anchor_text) if c[0] == "superseded-by"]

        member_cid = []
        member_sb = []
        for ln, mtext, mrole in e["members"]:
            for key, value, raw in _scan_comments(mtext):
                if key == "context-id":
                    member_cid.append((ln, mtext, mrole, value, raw))
                else:
                    member_sb.append((ln, mtext, mrole, value, raw))

        if kind is None:
            # Not a location the grammar defines as a map entry at all
            # (e.g. Brief prose, or a bullet/heading in the wrong section).
            # Only worth reporting if it actually carries a marker.
            if anchor_cid:
                issue("error", "misplaced-marker", anchor_line,
                      "identity marker on an unsupported entry shape/section: %r"
                      % anchor_text.strip())
            for ln, mtext, _mrole, _v, _raw in member_cid:
                issue("error", "misplaced-marker", ln,
                      "identity marker on an unsupported location: %r" % mtext.strip())
            for ln, mtext, _mrole, _v, _raw in member_sb:
                issue("error", "misplaced-marker", ln,
                      "bindle:superseded-by outside a Superseded tombstone: %r"
                      % mtext.strip())
            continue

        # Member-line markers are always malformed placement for a real entry.
        for ln, mtext, mrole, _v, _raw in member_cid:
            label = "tension side" if mrole == "indented-bullet" else \
                ("field line" if mrole == "field-line" else "unsupported location")
            issue("error", "misplaced-marker", ln,
                  "identity marker on a %s (belongs on the parent entry): %r"
                  % (label, mtext.strip()))
        for ln, mtext, _mrole, _v, _raw in member_sb:
            issue("error", "misplaced-marker", ln,
                  "bindle:superseded-by must be on the tombstone's own line: %r"
                  % mtext.strip())

        total_cid = len(anchor_cid) + len(member_cid)
        if total_cid > 1:
            issue("error", "multiple-markers", anchor_line,
                  "multiple identity markers on one entry (%d found): %r"
                  % (total_cid, anchor_text.strip()))

        resolved_id = None
        if len(anchor_cid) == 1:
            value = anchor_cid[0][1]
            if ID_RE.match(value):
                resolved_id = value
            else:
                issue("error", "malformed-marker", anchor_line,
                      "malformed identity %r on %r" % (value, anchor_text.strip()))
        elif len(anchor_cid) > 1:
            for _key, value, _raw in anchor_cid:
                if not ID_RE.match(value):
                    issue("error", "malformed-marker", anchor_line,
                          "malformed identity %r on %r" % (value, anchor_text.strip()))

        entry_kind = kind
        if section == "superseded":
            tm = TOMBSTONE_RE.match(anchor_text.strip())
            if tm:
                entry_kind = tm.group(1)
            else:
                issue("info", "untyped-tombstone", anchor_line,
                      "untyped retirement tombstone (missing '<kind>: ' prefix "
                      "or malformed retirement grammar): %r" % anchor_text.strip())
            if resolved_id is None and not anchor_cid:
                issue("info", "untyped-tombstone", anchor_line,
                      "retirement tombstone has no bindle:context-id marker: %r"
                      % anchor_text.strip())

            if len(anchor_sb) > 1:
                issue("error", "superseded-by-duplicate", anchor_line,
                      "multiple bindle:superseded-by markers on one tombstone: %r"
                      % anchor_text.strip())
            elif len(anchor_sb) == 1:
                sb_value = anchor_sb[0][1]
                if sb_value == "":
                    issue("error", "superseded-by-missing-value", anchor_line,
                          "bindle:superseded-by has an empty value: %r"
                          % anchor_text.strip())
                elif not ID_RE.match(sb_value):
                    issue("error", "superseded-by-malformed", anchor_line,
                          "malformed bindle:superseded-by value %r: %r"
                          % (sb_value, anchor_text.strip()))
                elif resolved_id is not None and sb_value == resolved_id:
                    issue("error", "superseded-by-self-referential", anchor_line,
                          "bindle:superseded-by points at its own retired id: %r"
                          % anchor_text.strip())
                elif sb_value not in all_ids_found:
                    issue("error", "superseded-by-unresolved", anchor_line,
                          "bindle:superseded-by %r matches no bindle:context-id "
                          "in this map: %r" % (sb_value, anchor_text.strip()))

        bucket = tombstone_occurrences if section == "superseded" else live_occurrences
        if resolved_id is not None:
            bucket.setdefault(resolved_id, []).append(anchor_line)
        for _key, value, _raw in anchor_cid:
            if ID_RE.match(value) and value != resolved_id:
                bucket.setdefault(value, []).append(anchor_line)

        out_entries.append({
            "section": section,
            "kind": entry_kind,
            "line": anchor_line,
            "text": anchor_text.strip(),
            "id": resolved_id,
            "anchored": resolved_id is not None,
        })

    for bucket, plural in ((live_occurrences, "entries"), (tombstone_occurrences, "tombstones")):
        for id_, lines in bucket.items():
            if len(lines) > 1:
                issue("error", "duplicate-id", lines[0],
                      "identity %s reused across %d %s (lines %s)"
                      % (id_, len(lines), plural, ", ".join(str(n) for n in lines)))

    ok = not any(i["severity"] == "error" for i in issues)
    return {
        "schema": SCHEMA,
        "ok": ok,
        "entries": out_entries,
        "anchored_count": sum(1 for e in out_entries if e["anchored"]),
        "unanchored_count": sum(1 for e in out_entries if not e["anchored"]),
        "issues": issues,
    }


def render_text(result):
    lines = []
    lines.append("map-entry-id validate (%s)" % result["schema"])
    lines.append("entries: %d anchored, %d unanchored"
                 % (result["anchored_count"], result["unanchored_count"]))
    for e in result["entries"]:
        state = e["id"] if e["anchored"] else "(unanchored)"
        lines.append("  [%s/%s] line %d: %s -- %s"
                     % (e["section"], e["kind"], e["line"], state, e["text"]))
    if result["issues"]:
        lines.append("issues:")
        for i in result["issues"]:
            lines.append("  [%s] %s line %d: %s"
                         % (i["severity"], i["code"], i["line"], i["message"]))
    else:
        lines.append("issues: none")
    lines.append("ok: %s" % result["ok"])
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def cmd_allocate(args):
    try:
        new_id = allocate_id(args.project)
    except ValueError as exc:
        print("map-entry-id: %s" % exc, file=sys.stderr)
        return 64
    print(new_id)
    return 0


def cmd_validate(args):
    try:
        with open(args.map, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("map-entry-id: cannot read --map: %s" % exc, file=sys.stderr)
        return 1
    result = validate_map(text)
    if args.format in ("json", "both"):
        print(json.dumps(result, indent=2))
    if args.format in ("text", "both"):
        print(render_text(result))
    return 0 if result["ok"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_alloc = sub.add_parser("allocate", help="allocate one new opaque identity")
    p_alloc.add_argument("--project", required=True, metavar="SLUG",
                         help="creation-project slug (lowercase kebab-case)")
    p_alloc.set_defaults(func=cmd_allocate)

    p_val = sub.add_parser("validate", help="read-only validation of a project map")
    p_val.add_argument("--map", required=True, metavar="PATH")
    p_val.add_argument("--format", choices=["text", "json", "both"], default="text")
    p_val.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
