"""Insert authorized identity-anchor markers into map.md with a minimal
diff. Only the target entry's anchor line changes; every other byte is
preserved. This is the same "never regenerate the file, never reorder the
owner's prose" discipline knowledge-promotion.md uses for map writes
(design doc section 12, "map.md marker writes").

`project_id` and `map_path` are the same frame fields the #183 compiler
passes to `canonical.entry_fingerprint` when it builds each unanchored
entry's identity-anchor candidate (compiler.py:296-299) -- an accepted
`identity_anchor` ledger event carries only the opaque `entry_fingerprint`
it was accepted under (`judgment.schema.json` requires just `assigned_id`
+ `entry_fingerprint` on identity_anchor events; review.py:196-204 mints
exactly those two and nothing else). Matching an authorized anchor back to
a *current* unanchored entry therefore means recomputing that same
fingerprint over this map's entries with this map's own frame fields --
`plan_map_bytes` takes them as explicit arguments rather than assuming
they can be read off the anchor or the entry.
"""
from context_graph import canonical

_MARKER = "<!-- bindle:context-id: %s -->"


def _finding(code, message, **extra):
    out = {"code": code, "message": message}
    out.update(extra)
    return out


def plan_map_bytes(map_text, entries, authorized_anchors, project_id, map_path):
    """Return (new_text, findings). Inserts one anchor marker per authorized
    anchor whose entry_fingerprint matches a current *unanchored* entry, at
    the end of that entry's anchor line. Unmatched anchors are reported and
    change nothing. Pure; no I/O."""
    # fingerprint -> unanchored entry (already-anchored entries are never
    # eligible targets, so they are excluded from this map entirely).
    by_fp = {}
    for e in entries:
        if not e["anchored"]:
            fp = canonical.entry_fingerprint(
                project_id, map_path, e["section"], e["kind"], e["entry_bytes"]
            )
            by_fp[fp] = e

    insertions = {}  # 1-based line number -> assigned_id
    findings = []
    for anchor in authorized_anchors:
        fp = anchor["entry_fingerprint"]
        entry = by_fp.get(fp)
        if entry is None:
            findings.append(_finding(
                "stale_anchor_no_entry",
                "authorized anchor %r matches no current unanchored entry"
                % (anchor["assigned_id"],),
                assigned_id=anchor["assigned_id"], entry_fingerprint=fp))
            continue
        insertions[entry["line"]] = anchor["assigned_id"]

    if not insertions:
        return map_text, findings

    lines = map_text.split("\n")
    for line_no, assigned_id in insertions.items():
        idx = line_no - 1
        lines[idx] = lines[idx].rstrip() + " " + (_MARKER % assigned_id)
    return "\n".join(lines), findings
