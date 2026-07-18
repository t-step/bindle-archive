"""context_graph.map_parser — deterministic project-map entry extraction for
the #183 compiler (epic #140).

Reuses #179's frozen map grammar and its existing validation logic
(`bin/map-entry-id.py`, loaded as a library via importlib — its filename is
not import-safe) for entry boundaries, marker placement, duplicate/malformed
identity detection, and superseded-by resolution. This module adds only what
`bin/map-entry-id.py` does not already do: disambiguating an
`assumptions`-section top-bullet into `assumption` vs `tension` by counting
its indented sides, extracting each entry's structured field content
(`why:`/`so:`/`revisit-when:`/`evidence:`, tension sides, confidence,
open/parked status), and producing the exact marker-stripped entry bytes
`context_graph.canonical.entry_fingerprint` requires.

Every `evidence` value this module returns is the RAW, complete field
string, exactly as written (never comma-split, never Markdown-unwrapped) --
that grammar belongs solely to `context_graph.evidence` (#181), and this
module passes it through unchanged, per the design's "#183 never splits on
commas, never unwraps a Markdown link" boundary.

Pure. No I/O, no mutation, no network. Never writes to the map.
"""
import importlib.util
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_MAP_ENTRY_ID_PATH = os.path.join(os.path.dirname(_HERE), "map-entry-id.py")

_spec = importlib.util.spec_from_file_location("bindle_map_entry_id", _MAP_ENTRY_ID_PATH)
map_entry_id = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(map_entry_id)

# Marker comments only -- an owner-authored, unrelated HTML comment on the
# same line must survive byte-for-byte in entry_fingerprint input.
_MARKER_ONLY_RE = re.compile(r"<!--\s*bindle:(?:context-id|superseded-by):.*?-->")

_ASSUMPTION_RE = re.compile(
    r"^-\s*(?P<label>.+?)\s*—\s*confidence:\s*(?P<confidence>high|medium|low)"
    r"(?:\s*—\s*evidence:\s*(?P<evidence>.+?))?\s*$"
)
_SIDE_RE = re.compile(
    r"^-\s*(?P<label>.+?)(?:\s*—\s*evidence:\s*(?P<evidence>.+?))?\s*$"
)
_QUESTION_RE = re.compile(
    r"^-\s*(?P<label>.+?)\s*\((?P<qstatus>open|parked)\)"
    r"\s*—\s*so:\s*(?P<so>.+?)"
    r"(?:\s*—\s*evidence:\s*(?P<evidence>.+?))?"
    r"(?:\s*`inquiry\?`)?\s*$"
)
_FIELD_LINE_RE = re.compile(r"^[ \t]*(why|so|revisit-when|evidence):\s*(.*)$")

REQUIRED_SECTIONS = frozenset(map_entry_id.SECTION_KEY.values())


def _strip_markers_only(line):
    return _MARKER_ONLY_RE.sub("", line).rstrip()


def _entry_bytes(anchor_text, members):
    lines = [anchor_text] + [m[1] for m in members]
    return "\n".join(_strip_markers_only(l) for l in lines).encode("utf-8")


def _conflict(code, line, message, severity="error"):
    return {"severity": severity, "code": code, "line": line, "message": message}


def _fields_from_members(members):
    fields = {}
    for _line, text, role in members:
        if role != "field-line":
            continue
        m = _FIELD_LINE_RE.match(text)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def _new_entry(section, kind, line, entry_id, anchored, status, label,
                confidence, evidence_raw, sides, superseded_by, entry_bytes):
    return {
        "section": section, "kind": kind, "line": line, "id": entry_id,
        "anchored": anchored, "status": status, "label": label,
        "confidence": confidence, "evidence_raw": evidence_raw or "",
        "sides": sides, "superseded_by": superseded_by,
        "entry_bytes": entry_bytes,
    }


def parse_project_map(text):
    """Parse project-map text into semantic entries plus conflicts.

    Returns {"entries": [...], "conflicts": [...]}. `entries` contains one
    item per uniquely parseable, canonical top-level map entry (anchored or
    not) -- an entry with a genuine shape conflict (bad tension cardinality,
    an untyped/unresolvable tombstone) is reported only in `conflicts`, never
    emitted as a half-formed entry. Missing required `##` sections are
    reported as one conflict without blocking parsing of the sections that
    are present.
    """
    raw_entries = map_entry_id.parse_map(text)
    validated = map_entry_id.validate_map(text)

    conflicts = [
        _conflict(issue["code"], issue["line"], issue["message"], issue["severity"])
        for issue in validated["issues"]
    ]

    found_sections = set()
    for line in text.splitlines():
        m = map_entry_id.SECTION_RE.match(line)
        if m:
            key = map_entry_id.SECTION_KEY.get(m.group(1).strip())
            if key:
                found_sections.add(key)
    missing = REQUIRED_SECTIONS - found_sections
    if missing:
        conflicts.append(_conflict(
            "missing-section", 0,
            "project map is missing required section(s): %s"
            % ", ".join(sorted(missing)),
        ))

    resolved_by_line = {e["line"]: e for e in validated["entries"]}

    entries = []
    for raw in raw_entries:
        resolved = resolved_by_line.get(raw["anchor_line"])
        if resolved is None:
            continue  # not a recognized entry shape (already reported, if marked)

        section = raw["section"]
        anchor_text = raw["anchor_text"]
        members = raw["members"]
        line = raw["anchor_line"]
        entry_id = resolved["id"]
        anchored = resolved["anchored"]
        no_marker_text = map_entry_id.COMMENT_RE.sub("", anchor_text).strip()
        entry_bytes = _entry_bytes(anchor_text, members)

        if section == "superseded":
            tm = map_entry_id.TOMBSTONE_RE.match(no_marker_text)
            if not tm:
                continue  # untyped/malformed tombstone -- already conflict-reported
            kind = tm.group("kind")
            label = tm.group("claim").strip()
            evidence_raw = ""
            sides = None

            # Retirement preserves a decision/learning's field lines, and a
            # tension's two sides, verbatim and indented beneath the
            # tombstone (knowledge-promotion.md "Retirement"). An
            # assumption/question tombstone instead folds its evidence tail
            # into the claim text itself ("the whole original bullet body,
            # verbatim") -- there is no separate line to recover it from, so
            # it is intentionally left unextracted here.
            if kind in ("decision", "learning"):
                fields = _fields_from_members(members)
                evidence_raw = fields.get("evidence", "")
            elif kind == "tension":
                side_members = [m for m in members if m[2] == "indented-bullet"]
                if len(side_members) == 2:
                    parsed_sides = []
                    for _ln, side_text, _role in side_members:
                        sm = _SIDE_RE.match(side_text.strip())
                        if sm:
                            parsed_sides.append({
                                "label": sm.group("label").strip(),
                                "evidence_raw": sm.group("evidence") or "",
                            })
                    if len(parsed_sides) == 2:
                        sides = parsed_sides

            superseded_by = None
            sb_comments = [
                c for c in map_entry_id._scan_comments(anchor_text)
                if c[0] == "superseded-by"
            ]
            if len(sb_comments) == 1:
                candidate = sb_comments[0][1]
                if map_entry_id.ID_RE.match(candidate) and candidate != entry_id:
                    superseded_by = candidate

            entries.append(_new_entry(
                section, kind, line, entry_id, anchored, "superseded", label,
                None, evidence_raw, sides, superseded_by, entry_bytes,
            ))
            continue

        if raw["role"] == "heading":
            hm = map_entry_id.HEADING_CLAIM_RE.match(no_marker_text)
            if not hm:
                continue
            kind = "decision" if section == "decisions" else "learning"
            fields = _fields_from_members(members)
            entries.append(_new_entry(
                section, kind, line, entry_id, anchored, "current",
                hm.group("claim").strip(), None, fields.get("evidence", ""),
                None, None, entry_bytes,
            ))
            continue

        if section == "questions":
            qm = _QUESTION_RE.match(no_marker_text)
            if not qm:
                continue
            entries.append(_new_entry(
                section, "question", line, entry_id, anchored,
                qm.group("qstatus"), qm.group("label").strip(), None,
                qm.group("evidence") or "", None, None, entry_bytes,
            ))
            continue

        if section == "assumptions":
            side_members = [m for m in members if m[2] == "indented-bullet"]
            if len(side_members) not in (0, 2):
                conflicts.append(_conflict(
                    "tension-cardinality", line,
                    "assumptions-section entry has %d indented side(s); "
                    "expected 0 (a plain assumption) or exactly 2 (a tension): %r"
                    % (len(side_members), anchor_text.strip()),
                ))
                continue

            am = _ASSUMPTION_RE.match(no_marker_text)
            if not am:
                continue

            if len(side_members) == 0:
                entries.append(_new_entry(
                    section, "assumption", line, entry_id, anchored, "current",
                    am.group("label").strip(), am.group("confidence"),
                    am.group("evidence") or "", None, None, entry_bytes,
                ))
                continue

            sides = []
            side_ok = True
            for _ln, side_text, _role in side_members:
                sm = _SIDE_RE.match(side_text.strip())
                if not sm:
                    side_ok = False
                    break
                sides.append({
                    "label": sm.group("label").strip(),
                    "evidence_raw": sm.group("evidence") or "",
                })
            if not side_ok:
                conflicts.append(_conflict(
                    "tension-cardinality", line,
                    "tension side does not match the expected "
                    "'<label> — evidence: <ptr>' shape: %r" % (anchor_text.strip(),),
                ))
                continue

            entries.append(_new_entry(
                section, "tension", line, entry_id, anchored, "current",
                am.group("label").strip(), am.group("confidence"), "",
                sides, None, entry_bytes,
            ))
            continue

    return {"entries": entries, "conflicts": conflicts}
