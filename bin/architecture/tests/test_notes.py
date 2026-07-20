"""Tests for architecture.notes (issue #230 child D, slice D4).

Scope note: these tests cover the note-file LIFECYCLE decision only --
create / update / noop / conflict for one note, given its current bytes.
They assert nothing about apply-state, resume, or ordering across notes;
those are the orchestrator's and are tested in test_apply.py. Nothing here
touches disk: `plan_note` is pure, and the whole point of separating it from
the orchestrator is that the decision can be exercised without a filesystem.
"""
import copy
import unittest

from architecture import notes
from architecture import render

ARCH_ID = "arch-node:project:" + "a" * 32 + ":" + "b" * 32


def _existing(body, tail="\n\n## Notes\nmine\n"):
    """A note on disk carrying `body` in its managed region."""
    return (
        "---\narch_id: %s\nprojection_type: arch_component\n---\n" % (ARCH_ID,)
        + render.BEGIN + "\n" + body + render.END
        + tail
    )


class PlanNoteCreate(unittest.TestCase):
    """The absent-file branch. A first-ever projection reaches this for
    every note, so a defect here means the MVP creates nothing at all."""

    def test_absent_file_creates_with_frontmatter_region_and_tail(self):
        plan = notes.plan_note(None, "BODY", arch_id=ARCH_ID,
                               projection_type="arch_component")
        self.assertEqual(plan["action"], "create")
        text = plan["text"]
        self.assertTrue(text.startswith("---\narch_id: %s\n" % (ARCH_ID,)))
        self.assertIn(render.BEGIN, text)
        self.assertIn(render.END, text)
        self.assertIn("BODY", text)

    def test_create_matches_compose_new_note_byte_for_byte(self):
        """The composer is child D1's frozen creation shape. Composing the
        text here by hand instead would let the two drift, and the drift
        would surface as a rewrite of every note on the run after a create.
        """
        plan = notes.plan_note(None, "BODY", arch_id=ARCH_ID,
                               projection_type="arch_component")
        self.assertEqual(
            plan["text"],
            render.compose_new_note(ARCH_ID, "arch_component", "BODY"))

    def test_create_without_identity_is_refused(self):
        """A note cannot be created without the identity that goes in its
        frontmatter. Defaulting it would write a note whose `arch_id` is
        empty and which `index.json` can never be reconciled against."""
        with self.assertRaises(notes.NoteInputError):
            notes.plan_note(None, "BODY", projection_type="arch_component")
        with self.assertRaises(notes.NoteInputError):
            notes.plan_note(None, "BODY", arch_id=ARCH_ID)


class PlanNoteRerun(unittest.TestCase):
    """The zero-write rerun. #230's acceptance says a rerun at the same
    commit writes zero bytes -- so an unchanged body must reach `noop`
    rather than an `update` carrying identical text."""

    def test_identical_body_is_noop(self):
        plan = notes.plan_note(_existing("BODY"), "BODY")
        self.assertEqual(plan["action"], "noop")
        self.assertNotIn("text", plan)

    def test_create_then_replan_same_body_is_noop(self):
        """The round trip that matters: the bytes `create` produced, fed
        back in with the same body, must plan as a no-op. If create and
        update disagree by even one byte, every note is rewritten on the
        run after its creation and the rerun acceptance bullet fails while
        both branches look correct in isolation."""
        created = notes.plan_note(None, "BODY", arch_id=ARCH_ID,
                                  projection_type="arch_component")["text"]
        plan = notes.plan_note(created, "BODY")
        self.assertEqual(plan["action"], "noop")


class PlanNoteUpdate(unittest.TestCase):
    """The update branch and the prose it must not touch."""

    def test_changed_body_updates(self):
        plan = notes.plan_note(_existing("OLD"), "NEW")
        self.assertEqual(plan["action"], "update")
        self.assertIn("NEW", plan["text"])
        self.assertNotIn("OLD", plan["text"])

    def test_user_prose_outside_the_region_survives_byte_for_byte(self):
        """AC13. The tail below the region and the frontmatter above it
        belong to the reader from the moment the file exists."""
        tail = "\n\n## Notes\nhand-written, mine, keep it\n\n- a bullet\n"
        before = _existing("OLD", tail=tail)
        plan = notes.plan_note(before, "NEW")
        text = plan["text"]
        self.assertTrue(text.endswith(tail))
        self.assertTrue(text.startswith(before[:before.index(render.BEGIN)]))

    def test_input_text_is_not_mutated(self):
        before = _existing("OLD")
        original = copy.copy(before)
        notes.plan_note(before, "NEW")
        self.assertEqual(before, original)


class PlanNoteConflict(unittest.TestCase):
    """A file this module may not rewrite. Guessing at either case risks
    destroying bytes the tool does not own, so both are refusals that write
    nothing rather than a best-effort splice."""

    def test_markerless_file_is_a_conflict(self):
        plan = notes.plan_note("# Hand-authored\n\nno markers here\n", "BODY")
        self.assertEqual(plan["action"], "conflict")
        self.assertEqual(plan["code"], notes.CONFLICT_UNMANAGED)
        self.assertNotIn("text", plan)

    def test_duplicated_markers_are_a_conflict(self):
        doubled = _existing("BODY") + render.BEGIN + "\nx" + render.END
        plan = notes.plan_note(doubled, "BODY")
        self.assertEqual(plan["action"], "conflict")
        self.assertEqual(plan["code"], notes.CONFLICT_MALFORMED)

    def test_end_before_begin_is_a_conflict(self):
        inverted = render.END + "\nbody\n" + render.BEGIN
        plan = notes.plan_note(inverted, "BODY")
        self.assertEqual(plan["action"], "conflict")
        self.assertEqual(plan["code"], notes.CONFLICT_MALFORMED)

    def test_a_note_managed_by_the_context_surface_is_unmanaged_here(self):
        """The context surface's marker pair is not this one. Seeing a
        `context.md` region as a valid region of its own would splice
        architecture bytes into a file child #185 owns."""
        foreign = ("<!-- bindle:context:generated:begin -->\nx"
                   "<!-- bindle:context:generated:end -->\n")
        plan = notes.plan_note(foreign, "BODY")
        self.assertEqual(plan["action"], "conflict")
        self.assertEqual(plan["code"], notes.CONFLICT_UNMANAGED)


class ConflictCodes(unittest.TestCase):
    """The codes are reported to a human and consumed by preview, so they
    are part of the surface rather than incidental strings."""

    def test_codes_name_the_architecture_surface(self):
        self.assertEqual(notes.CONFLICT_UNMANAGED, "arch_note_unmanaged")
        self.assertEqual(notes.CONFLICT_MALFORMED,
                         "arch_note_malformed_markers")


if __name__ == "__main__":
    unittest.main()
