"""The marker-agnostic generated-region core (#230 child D, slice D1).

`projection.py` froze the BEGIN/END pair as module constants referenced
directly by `_scan_markers`, `plan_context_md`, and `plan_adopt_context_md`.
A second surface needs the same lifecycle around a DIFFERENT pair, so
the core moves here and takes the pair as arguments. These tests are written
against the core alone; `test_projection.py` remains the regression floor
proving the context surface still behaves byte-identically through it.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import regions

CG_BEGIN = "<!-- bindle:context-graph:generated:begin -->"
CG_END = "<!-- bindle:context-graph:generated:end -->"
OTHER_BEGIN = "<!-- bindle:other:generated:begin -->"
OTHER_END = "<!-- bindle:other:generated:end -->"


class WrapTest(unittest.TestCase):
    def test_wrap_composes_begin_newline_body_end(self):
        self.assertEqual(
            regions.wrap("BODY\n", OTHER_BEGIN, OTHER_END),
            OTHER_BEGIN + "\n" + "BODY\n" + OTHER_END,
        )

    def test_wrap_is_marker_agnostic(self):
        self.assertEqual(
            regions.wrap("B\n", "<!--x-->", "<!--y-->"),
            "<!--x-->\nB\n<!--y-->",
        )

    def test_wrap_does_not_add_a_trailing_newline_after_end(self):
        # The caller owns what follows END; an injected newline would shift
        # every byte of the preserved suffix on the first update.
        self.assertFalse(regions.wrap("B\n", OTHER_BEGIN, OTHER_END).endswith("\n"))


class ScanTest(unittest.TestCase):
    def test_no_markers_is_unmanaged(self):
        self.assertEqual(
            regions.scan("# hand written\n", OTHER_BEGIN, OTHER_END),
            ("unmanaged", None, None),
        )

    def test_one_ordered_pair_is_valid_with_start_offsets(self):
        text = "pre\n" + OTHER_BEGIN + "\nbody\n" + OTHER_END + "\npost\n"
        kind, begin_idx, end_idx = regions.scan(text, OTHER_BEGIN, OTHER_END)
        self.assertEqual(kind, "valid")
        self.assertEqual(begin_idx, text.index(OTHER_BEGIN))
        self.assertEqual(end_idx, text.index(OTHER_END))

    def test_end_before_begin_is_malformed(self):
        text = OTHER_END + "\nbody\n" + OTHER_BEGIN + "\n"
        self.assertEqual(regions.scan(text, OTHER_BEGIN, OTHER_END),
                         ("malformed", None, None))

    def test_duplicated_begin_is_malformed(self):
        text = OTHER_BEGIN + "\n" + OTHER_BEGIN + "\nbody\n" + OTHER_END + "\n"
        self.assertEqual(regions.scan(text, OTHER_BEGIN, OTHER_END),
                         ("malformed", None, None))

    def test_duplicated_end_is_malformed(self):
        text = OTHER_BEGIN + "\nbody\n" + OTHER_END + "\n" + OTHER_END + "\n"
        self.assertEqual(regions.scan(text, OTHER_BEGIN, OTHER_END),
                         ("malformed", None, None))

    def test_begin_without_end_is_malformed(self):
        self.assertEqual(regions.scan(OTHER_BEGIN + "\nbody\n", OTHER_BEGIN, OTHER_END),
                         ("malformed", None, None))

    def test_end_without_begin_is_malformed(self):
        self.assertEqual(regions.scan("body\n" + OTHER_END, OTHER_BEGIN, OTHER_END),
                         ("malformed", None, None))

    def test_an_end_marker_prefixed_by_the_begin_marker_is_malformed(self):
        # The degenerate overlap: when END *starts with* BEGIN, both markers
        # match at the SAME offset, so the pair encloses nothing. Ordering
        # must be strict -- accepting begin_idx == end_idx would call this
        # valid and hand splice a zero-length region to corrupt.
        begin, end = "<!--A-->", "<!--A-->B"
        text = "pre\n" + end + "\npost\n"
        self.assertEqual(regions.scan(text, begin, end),
                         ("malformed", None, None))

    def test_a_foreign_marker_pair_does_not_make_a_note_managed(self):
        # A second surface's note that quotes or neighbours a context-graph
        # region must still read as unmanaged to that surface's scanner --
        # otherwise D would splice its body into someone else's region.
        text = CG_BEGIN + "\ncontext body\n" + CG_END + "\n"
        self.assertEqual(regions.scan(text, OTHER_BEGIN, OTHER_END),
                         ("unmanaged", None, None))

    def test_each_pair_is_scanned_independently_in_one_text(self):
        text = (CG_BEGIN + "\nc\n" + CG_END + "\n"
                + OTHER_BEGIN + "\na\n" + OTHER_END + "\n")
        self.assertEqual(regions.scan(text, CG_BEGIN, CG_END)[0], "valid")
        self.assertEqual(regions.scan(text, OTHER_BEGIN, OTHER_END)[0], "valid")


class SpliceTest(unittest.TestCase):
    def _managed(self, body, prefix="# Title\n", suffix="\n## Mine\nprose\n"):
        return prefix + regions.wrap(body, OTHER_BEGIN, OTHER_END) + suffix

    def test_identical_region_is_a_noop(self):
        text = self._managed("BODY\n")
        self.assertEqual(regions.splice(text, "BODY\n", OTHER_BEGIN, OTHER_END),
                         ("noop", None))

    def test_changed_region_updates(self):
        text = self._managed("OLD\n")
        action, new_text = regions.splice(text, "NEW\n", OTHER_BEGIN, OTHER_END)
        self.assertEqual(action, "update")
        self.assertIn("NEW", new_text)
        self.assertNotIn("OLD", new_text)

    def test_bytes_outside_the_region_survive_an_update_exactly(self):
        prefix = "# Title\n\nuser intro\n"
        suffix = "\n## Maintainer notes\nédge \t case\n\n"
        text = self._managed("OLD\n", prefix=prefix, suffix=suffix)
        _, new_text = regions.splice(text, "NEW\n", OTHER_BEGIN, OTHER_END)
        self.assertTrue(new_text.startswith(prefix))
        self.assertTrue(new_text.endswith(suffix))
        # And the ONLY difference is the region itself.
        self.assertEqual(
            new_text,
            prefix + regions.wrap("NEW\n", OTHER_BEGIN, OTHER_END) + suffix,
        )

    def test_splice_rejects_unmanaged_text(self):
        with self.assertRaises(regions.RegionError):
            regions.splice("no markers\n", "B\n", OTHER_BEGIN, OTHER_END)

    def test_splice_rejects_malformed_text(self):
        with self.assertRaises(regions.RegionError):
            regions.splice(OTHER_BEGIN + "\nx\n", "B\n", OTHER_BEGIN, OTHER_END)

    def test_splice_leaves_a_foreign_region_untouched(self):
        text = (CG_BEGIN + "\ncontext\n" + CG_END + "\n"
                + regions.wrap("OLD\n", OTHER_BEGIN, OTHER_END) + "\n")
        _, new_text = regions.splice(text, "NEW\n", OTHER_BEGIN, OTHER_END)
        self.assertIn(CG_BEGIN + "\ncontext\n" + CG_END, new_text)
        self.assertIn(regions.wrap("NEW\n", OTHER_BEGIN, OTHER_END), new_text)


if __name__ == "__main__":
    unittest.main()
