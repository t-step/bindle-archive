"""Deterministic note bodies for the two D-owned projection types
(#230 child D, slice D1).

Renders the codebase map and component notes -- and nothing else. The note
tree is frozen (epic section 3): D creates `Codebase Map.md` and
`Components/`, F1-F4 populate the other four roots, and no renderer may
invent a sibling root.

Three constraints shape everything here:

- METRICS RENDER AS BANDS, NEVER RAW VALUES. A raw fan-in moves on edits
  that changed no architecture, so rendering it would rewrite notes on
  noise. C3 already froze band-only comparison for `diffs.fingerprint`;
  the rendered bytes have to agree with the differ or the differ lies.
- `bindings` IS NOT RENDERED, for the same reason: `diffs.FINGERPRINT_FIELDS`
  excludes it, so a note carrying it would move while the differ reported
  the candidate unchanged.
- NO OBSERVED PROVENANCE. `source_commit`, `provider_version`,
  `per_binding_status` and the projection timestamp belong to `index.json`.
  One of them inside the byte-compared region turns a single README commit
  into a rewrite of all N notes (AC10 / PT8 / PT31).

Identity does not appear in the region either: `arch_id` is written once, in
the note's YAML frontmatter, by `compose_new_note`. Frontmatter must be the
first bytes of a file for any YAML parser to read it as properties, so it
necessarily sits OUTSIDE the generated region -- written at creation and
never rewritten, which is what keeps it clear of byte comparison (AC13).
Nothing ever reads it back: `index.json` is the only identity authority
(FC-5).

Pure: no I/O, no clock, no run-only value.
"""

from architecture import candidates
from architecture import metrics
from architecture import ranking
from context_graph import regions

BEGIN = "<!-- bindle:architecture:generated:begin -->"
END = "<!-- bindle:architecture:generated:end -->"

# The signals rendered on a component note, in this fixed order. Same tuple
# and same order as `ranking.RANK_SIGNALS`, so the note reads in the order
# the ranking weighed them rather than in an order of its own.
RENDERED_SIGNALS = ranking.RANK_SIGNALS

# Every field a candidate record may carry (`candidates.RECORD_FIELDS`).
# Rendering is strict in both directions -- an unknown field means the
# record came from somewhere this module does not understand, and a missing
# one means a caller built a record by hand and dropped something.
_KNOWN_RECORD_FIELDS = frozenset(candidates.RECORD_FIELDS)

# What the map needs about each component it lists. `note_path` comes from
# the creation event (`state.parse_note_path`) and is never recomputed here.
_MEMBER_REQUIRED = ("candidate_key", "name", "note_path")

_PLACEHOLDER = "(none)"


def _require(record, projection_type, known, required, label):
    if not isinstance(record, dict):
        raise RenderInputError("%s must be a dict, got %r" % (label, type(record)))
    unknown = sorted(set(record) - set(known))
    if unknown:
        raise RenderInputError("%s carries unknown field(s): %s"
                               % (label, ", ".join(unknown)))
    missing = sorted(f for f in required if f not in record)
    if missing:
        raise RenderInputError("%s is missing field(s): %s"
                               % (label, ", ".join(missing)))
    if projection_type is not None and record.get("projection_type") != projection_type:
        raise RenderInputError(
            "%s expects projection_type %r, got %r"
            % (label, projection_type, record.get("projection_type")))


class RenderInputError(Exception):
    """A record this module cannot render as written."""


def _bullets(values):
    """A sorted bullet list, or an explicit placeholder.

    Sorting here rather than trusting arrival order is what makes the bytes
    independent of how the caller happened to build its list; the empty
    placeholder keeps an empty section from collapsing into a blank the next
    render could fill differently.
    """
    items = sorted(values or [])
    if not items:
        return "- " + _PLACEHOLDER
    return "\n".join("- %s" % (item,) for item in items)


def _band_lines(record):
    """One line per ranked signal, band only, `unknown` when unmeasured."""
    lines = []
    for signal in RENDERED_SIGNALS:
        measurement = (record.get("metrics") or {}).get(signal)
        band = None
        if isinstance(measurement, dict):
            band = measurement.get("band")
        lines.append("- %s: %s" % (signal, band or metrics.UNKNOWN_BAND))
    return "\n".join(lines)


def _section(heading, body):
    return "## %s\n\n%s\n" % (heading, body)


def render_component(record):
    """The generated-region body for one component note."""
    _require(record, "arch_component", _KNOWN_RECORD_FIELDS,
             candidates.RECORD_FIELDS, "component record")

    sections = [
        "# %s\n" % (record["name"],),
        _section("Structure",
                 "- members: %s" % (record["member_count"],)),
        _section("Source paths", _bullets(record["source_paths"])),
        _section("Symbols", _bullets(record["symbol_names"])),
        _section("Entry points", _bullets(record["entry_points"])),
        _section("Neighborhood", _bullets(record["neighborhood"])),
        _section("Signals", _band_lines(record)),
    ]
    return "\n".join(sections)


def render_codebase_map(record, members):
    """The generated-region body for `Codebase Map.md`.

    `members` is one dict per component the map lists -- `candidate_key`,
    `name`, and the component's `note_path`. The map links to notes; it
    never restates their contents, and raw files and symbols never become
    entries of their own.
    """
    _require(record, "arch_codebase_map", _KNOWN_RECORD_FIELDS,
             candidates.RECORD_FIELDS, "codebase map record")

    rows = []
    for member in sorted(members or [], key=_member_key):
        _require(member, None, _MEMBER_REQUIRED, _MEMBER_REQUIRED,
                 "codebase map member")
        rows.append("- [%s](%s) — `%s`"
                    % (member["name"], member["note_path"],
                       member["candidate_key"]))
    listing = "\n".join(rows) if rows else "- " + _PLACEHOLDER

    sections = [
        "# Codebase Map\n",
        _section("Components", listing),
        _section("Structure", "- components: %s" % (record["member_count"],)),
    ]
    return "\n".join(sections)


def _member_key(member):
    """Order the map by `candidate_key`, the key C2 froze as stable across
    ordinary edits -- not by `name`, which a G rename can move.
    """
    if not isinstance(member, dict) or "candidate_key" not in member:
        raise RenderInputError("codebase map member is missing candidate_key")
    return member["candidate_key"]


def compose_new_note(arch_id, projection_type, body):
    """The full text of a note being created for the first time.

    Frontmatter, then the generated region, then a user-owned tail. Only the
    region is ever rewritten; the frontmatter and everything below the tail
    heading belong to the reader from the moment the file exists.
    """
    frontmatter = (
        "---\n"
        "arch_id: %s\n"
        "projection_type: %s\n"
        "---\n" % (arch_id, projection_type)
    )
    return (
        frontmatter
        + regions.wrap(body, BEGIN, END)
        + "\n\n## Notes\n"
        + "(notes below this line are yours -- the projection will never "
          "touch them)\n"
    )
