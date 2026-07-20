"""architecture.notes -- the note-file lifecycle for one architecture note
(issue #230 child D, slice D4, epic #141).

The create/update/noop/conflict decision for a single note, given its
current bytes and the freshly rendered region body. Pure: no I/O, no clock,
no run-only value -- the orchestrator reads disk and writes bytes; this
module only decides.

WHY NOT `projection.plan_context_md`. That function is the same lifecycle
for a DIFFERENT surface: it hard-codes the context pair, the `# <title> —
context` scaffold and the `context_md_*` conflict vocabulary. Calling it
here would splice architecture bytes into a file #185 owns and report a
context code for an architecture note. D1 already moved the part that is
genuinely shared -- the marker mechanics -- into `context_graph.regions`,
so this module is the thin surface-specific half and there is still exactly
ONE scanner.

THE CREATE BRANCH DELEGATES TO `render.compose_new_note`. Composing the
first-ever bytes here instead would let the two shapes drift, and the drift
would not surface as a failure: it would surface as every note being
rewritten on the run after its creation, with the create path and the
update path each looking correct on its own. The round trip
(create -> re-plan same body -> noop) is what pins them together.

A CONFLICT WRITES NOTHING AND GUESSES NOTHING. A markerless file is a
hand-authored note, or one managed by some other marker pair; a file with
duplicated or inverted markers has no unambiguous region. Splicing either
on a best guess would destroy bytes the projection does not own, so both
are refusals reported by code.
"""

from architecture import render
from context_graph import regions

# A file with no architecture marker pair at all. Hand-authored, or managed
# by another pair -- this scanner sees only its own.
CONFLICT_UNMANAGED = "arch_note_unmanaged"

# Markers present but unusable: unequal counts, a duplicated or nested pair,
# or END before BEGIN. There is no region to replace.
CONFLICT_MALFORMED = "arch_note_malformed_markers"

CONFLICT_CODES = (CONFLICT_UNMANAGED, CONFLICT_MALFORMED)

ACTIONS = ("create", "update", "noop", "conflict")


class NoteInputError(Exception):
    """Input a note lifecycle cannot be decided from honestly."""


def plan_note(existing_text, body, arch_id=None, projection_type=None):
    """Plan the transition for one note.

    `existing_text` is the file's current text, or `None` when the file does
    not exist yet. `body` is the rendered generated-region body. Returns one
    of:

        {"action": "create", "text": ...}   the file does not exist
        {"action": "update", "text": ...}   the region's bytes must change
        {"action": "noop"}                  the region already holds `body`
        {"action": "conflict", "code": ...} this module may not rewrite it

    `arch_id` and `projection_type` are required on the create branch only:
    they go in the frontmatter, which is written once and never rewritten.
    """
    if existing_text is None:
        if not arch_id or not projection_type:
            raise NoteInputError(
                "creating a note requires arch_id and projection_type; "
                "got arch_id=%r projection_type=%r"
                % (arch_id, projection_type))
        return {"action": "create",
                "text": render.compose_new_note(arch_id, projection_type,
                                                body)}

    kind, _, _ = regions.scan(existing_text, render.BEGIN, render.END)
    if kind == "unmanaged":
        return {"action": "conflict", "code": CONFLICT_UNMANAGED}
    if kind == "malformed":
        return {"action": "conflict", "code": CONFLICT_MALFORMED}

    action, new_text = regions.splice(existing_text, body,
                                      render.BEGIN, render.END)
    if action == "noop":
        return {"action": "noop"}
    return {"action": "update", "text": new_text}
