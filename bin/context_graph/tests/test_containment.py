"""Tests for context_graph.containment — notes-home containment verified
AFTER symlink resolution (#230 slice D2, epic #141 R2/PT26).

The load-bearing cases are the ones a lexical check passes and a real
filesystem check fails: a symlink inside the root pointing out of it, a
sibling directory sharing the root's name as a string prefix, and a notes
home that is itself a symlink (the Obsidian-vault layout this repo's own
notes home uses).
"""
import os
import shutil
import tempfile
import unittest

from context_graph import containment


class ContainmentTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "notes")
        os.makedirs(os.path.join(self.root, "projects", "p"))
        self.outside = os.path.join(self.tmp, "outside")
        os.makedirs(self.outside)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class CheckPathTests(ContainmentTestCase):
    def test_path_below_root_is_contained(self):
        p = os.path.join(self.root, "projects", "p", "note.md")
        self.assertEqual(containment.check_path(self.root, p), ("contained", None))

    def test_nonexistent_path_below_root_is_contained(self):
        """Planned paths do not exist yet — that must not read as an escape."""
        p = os.path.join(self.root, "projects", "p", "arch", "new", "note.md")
        self.assertFalse(os.path.exists(p))
        self.assertEqual(containment.check_path(self.root, p), ("contained", None))

    def test_relative_path_is_joined_to_root(self):
        verdict, _ = containment.check_path(self.root, "projects/p/note.md")
        self.assertEqual(verdict, "contained")

    def test_dot_dot_escape_is_rejected(self):
        p = os.path.join(self.root, "projects", "..", "..", "outside", "x.md")
        self.assertEqual(containment.check_path(self.root, p)[0], "escapes")

    def test_absolute_path_outside_root_is_rejected(self):
        p = os.path.join(self.outside, "x.md")
        self.assertEqual(containment.check_path(self.root, p)[0], "escapes")

    def test_root_itself_is_rejected(self):
        """Writes must be BELOW the notes home, not AT it."""
        self.assertEqual(containment.check_path(self.root, self.root)[0], "escapes")

    def test_sibling_sharing_the_root_name_as_prefix_is_rejected(self):
        """`<root>-evil/x` must not pass a string-prefix comparison."""
        sibling = self.root + "-evil"
        os.makedirs(sibling)
        self.assertEqual(
            containment.check_path(self.root, os.path.join(sibling, "x.md"))[0],
            "escapes")

    def test_symlinked_file_pointing_outside_is_rejected(self):
        target = os.path.join(self.outside, "target.md")
        with open(target, "w") as fh:
            fh.write("x")
        link = os.path.join(self.root, "projects", "p", "note.md")
        os.symlink(target, link)
        self.assertEqual(containment.check_path(self.root, link)[0], "escapes")

    def test_symlinked_parent_directory_pointing_outside_is_rejected(self):
        """The escape is in an ANCESTOR, and the leaf need not exist."""
        link_dir = os.path.join(self.root, "projects", "p", "arch")
        os.symlink(self.outside, link_dir)
        leaf = os.path.join(link_dir, "note.md")
        self.assertFalse(os.path.exists(leaf))
        self.assertEqual(containment.check_path(self.root, leaf)[0], "escapes")

    def test_symlink_chain_out_and_back_in_is_contained(self):
        """Resolution is what counts, not how many hops it took."""
        hop = os.path.join(self.outside, "hop")
        os.symlink(os.path.join(self.root, "projects", "p"), hop)
        link = os.path.join(self.root, "projects", "p", "loop")
        os.symlink(hop, link)
        leaf = os.path.join(link, "note.md")
        self.assertEqual(containment.check_path(self.root, leaf)[0], "contained")

    def test_symlinked_notes_home_resolves_before_comparison(self):
        """The Obsidian layout: the notes home is itself a symlink."""
        alias = os.path.join(self.tmp, "alias")
        os.symlink(self.root, alias)
        p = os.path.join(alias, "projects", "p", "note.md")
        self.assertEqual(containment.check_path(alias, p), ("contained", None))

    def test_escape_verdict_reports_the_resolved_destination(self):
        p = os.path.join(self.root, "projects", "..", "..", "outside", "x.md")
        verdict, resolved = containment.check_path(self.root, p)
        self.assertEqual(verdict, "escapes")
        self.assertEqual(resolved, os.path.realpath(os.path.join(self.outside, "x.md")))

    def test_contained_verdict_carries_no_destination(self):
        p = os.path.join(self.root, "projects", "p", "note.md")
        self.assertEqual(containment.check_path(self.root, p)[1], None)

    def test_empty_path_is_rejected(self):
        self.assertEqual(containment.check_path(self.root, "")[0], "escapes")

    def test_non_string_path_is_rejected(self):
        for bad in (None, 3, ["x"]):
            self.assertEqual(containment.check_path(self.root, bad)[0], "escapes")

    def test_nul_byte_in_path_is_rejected(self):
        self.assertEqual(containment.check_path(self.root, "a\x00b")[0], "escapes")


class CheckPlanTests(ContainmentTestCase):
    def test_all_contained_plan_passes(self):
        paths = ["projects/p/a.md", "projects/p/b.md"]
        self.assertEqual(containment.check_plan(self.root, paths), ("contained", ()))

    def test_empty_plan_passes(self):
        self.assertEqual(containment.check_plan(self.root, []), ("contained", ()))

    def test_one_escaping_path_rejects_the_whole_plan(self):
        paths = [
            "projects/p/a.md",
            os.path.join(self.outside, "x.md"),
            "projects/p/b.md",
        ]
        verdict, offenders = containment.check_plan(self.root, paths)
        self.assertEqual(verdict, "rejected")
        self.assertEqual([o[0] for o in offenders], [paths[1]])

    def test_every_offender_is_reported_not_just_the_first(self):
        bad_a = os.path.join(self.outside, "a.md")
        bad_b = os.path.join(self.outside, "b.md")
        verdict, offenders = containment.check_plan(
            self.root, ["projects/p/ok.md", bad_a, bad_b])
        self.assertEqual(verdict, "rejected")
        self.assertEqual([o[0] for o in offenders], [bad_a, bad_b])

    def test_offenders_carry_their_resolved_destination(self):
        bad = os.path.join(self.outside, "a.md")
        _, offenders = containment.check_plan(self.root, [bad])
        self.assertEqual(offenders[0][1], os.path.realpath(bad))

    def test_offenders_preserve_plan_order(self):
        bad_a = os.path.join(self.outside, "a.md")
        bad_b = os.path.join(self.outside, "b.md")
        _, offenders = containment.check_plan(self.root, [bad_b, bad_a])
        self.assertEqual([o[0] for o in offenders], [bad_b, bad_a])

    def test_offenders_is_a_tuple(self):
        _, offenders = containment.check_plan(
            self.root, [os.path.join(self.outside, "a.md")])
        self.assertIsInstance(offenders, tuple)


if __name__ == "__main__":
    unittest.main()
