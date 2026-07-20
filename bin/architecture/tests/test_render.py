"""Deterministic note rendering for the two D-owned projection types
(#230 child D, slice D1).

Two invariants carry the weight here and both are easy to write vacuously:

- METRICS RENDER AS BANDS ONLY. A test that merely asserts a band string
  appears also passes against an implementation that renders the raw value
  beside it, so every band test below pairs a same-band/different-value case
  (bytes must be EQUAL) with a different-band case (bytes must DIFFER).
- NO OBSERVED PROVENANCE IN THE REGION. `source_commit`, `provider_version`,
  `per_binding_status` and the projection timestamp live in `index.json`
  alone; a single one of them inside the byte-compared region turns one
  README commit into a rewrite of every note (AC10 / PT8 / PT31).
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from architecture import render


def _measure(value, band):
    return {"value": value, "lower_bound": None, "coverage": "complete",
            "band": band}


def _component(**over):
    record = {
        "candidate_key": "component:auth",
        "projection_type": "arch_component",
        "name": "Auth",
        "source_paths": ["auth/session.py", "auth/tokens.py"],
        "symbol_names": ["Session", "mint_token"],
        "neighborhood": ["http", "storage"],
        "entry_points": ["auth/__main__.py"],
        "metrics": {
            "blast_radius": _measure(12, "high"),
            "fan_in": _measure(4, "moderate"),
            "fan_out": _measure(1, "low"),
        },
        "bindings": ["binding:aaa"],
        "member_count": 2,
    }
    record.update(over)
    return record


def _map(**over):
    record = {
        "candidate_key": "codebase-map",
        "projection_type": "arch_codebase_map",
        "name": "codebase-map",
        "source_paths": ["auth", "billing"],
        "symbol_names": ["Auth", "Billing"],
        "neighborhood": [],
        "entry_points": [],
        "metrics": {},
        "bindings": ["binding:aaa"],
        "member_count": 2,
    }
    record.update(over)
    return record


PROVENANCE_TOKENS = (
    "source_commit", "provider_version", "provider_name",
    "per_binding_status", "per_binding_coverage", "last_projected_at",
)


class ComponentBodyTest(unittest.TestCase):
    def test_is_pure(self):
        self.assertEqual(render.render_component(_component()),
                         render.render_component(_component()))

    def test_renders_the_name_and_member_count(self):
        body = render.render_component(_component())
        self.assertIn("Auth", body)
        self.assertIn("2", body)

    def test_carries_no_observed_provenance(self):
        body = render.render_component(_component())
        for token in PROVENANCE_TOKENS:
            self.assertNotIn(token, body)

    def test_source_paths_render_sorted_not_in_arrival_order(self):
        # Names chosen so sorted order REVERSES the input order -- an
        # implementation that just echoes the list fails.
        body = render.render_component(
            _component(source_paths=["zeta.py", "alpha.py"]))
        self.assertLess(body.index("alpha.py"), body.index("zeta.py"))

    def test_symbol_names_render_sorted_not_in_arrival_order(self):
        body = render.render_component(
            _component(symbol_names=["zeta_fn", "alpha_fn"]))
        self.assertLess(body.index("alpha_fn"), body.index("zeta_fn"))

    def test_entry_points_render_sorted_not_in_arrival_order(self):
        body = render.render_component(
            _component(entry_points=["z/__main__.py", "a/main.py"]))
        self.assertLess(body.index("a/main.py"), body.index("z/__main__.py"))

    def test_neighborhood_renders_sorted_not_in_arrival_order(self):
        body = render.render_component(
            _component(neighborhood=["zulu", "alfa"]))
        self.assertLess(body.index("alfa"), body.index("zulu"))

    def test_empty_lists_render_a_placeholder_rather_than_a_blank(self):
        body = render.render_component(
            _component(symbol_names=[], entry_points=[], neighborhood=[]))
        self.assertIn("(none)", body)

    # --- the two discriminating pairs -----------------------------------

    def test_a_raw_metric_change_within_one_band_does_not_change_bytes(self):
        low = render.render_component(_component(metrics={
            "blast_radius": _measure(12, "high"),
            "fan_in": _measure(4, "moderate"),
            "fan_out": _measure(1, "low"),
        }))
        high = render.render_component(_component(metrics={
            "blast_radius": _measure(9999, "high"),
            "fan_in": _measure(7, "moderate"),
            "fan_out": _measure(2, "low"),
        }))
        self.assertEqual(low, high)

    def test_a_band_change_does_change_bytes(self):
        before = render.render_component(_component())
        after = render.render_component(_component(metrics={
            "blast_radius": _measure(12, "very_high"),
            "fan_in": _measure(4, "moderate"),
            "fan_out": _measure(1, "low"),
        }))
        self.assertNotEqual(before, after)

    def test_raw_metric_values_never_appear(self):
        body = render.render_component(_component(metrics={
            "blast_radius": _measure(4242, "high"),
            "fan_in": _measure(4, "moderate"),
            "fan_out": _measure(1, "low"),
        }))
        self.assertNotIn("4242", body)
        self.assertIn("high", body)

    def test_an_unmeasured_signal_renders_unknown(self):
        body = render.render_component(_component(metrics={}))
        self.assertIn("unknown", body)

    # --- bindings are excluded, matching the C3 fingerprint -------------

    def test_a_binding_change_alone_does_not_change_bytes(self):
        # `diffs.FINGERPRINT_FIELDS` excludes `bindings` on purpose. If the
        # note rendered them, the differ would call a note unchanged while
        # its bytes moved -- a guaranteed spurious rewrite.
        self.assertEqual(
            render.render_component(_component(bindings=["binding:aaa"])),
            render.render_component(
                _component(bindings=["binding:bbb", "binding:ccc"])),
        )


class CodebaseMapBodyTest(unittest.TestCase):
    def _members(self):
        return [
            {"candidate_key": "component:zeta", "name": "Alpha",
             "note_path": "Components/zeta.md"},
            {"candidate_key": "component:alpha", "name": "Zulu",
             "note_path": "Components/alpha.md"},
        ]

    def test_is_pure(self):
        self.assertEqual(
            render.render_codebase_map(_map(), self._members()),
            render.render_codebase_map(_map(), self._members()),
        )

    def test_carries_no_observed_provenance(self):
        body = render.render_codebase_map(_map(), self._members())
        for token in PROVENANCE_TOKENS:
            self.assertNotIn(token, body)

    def test_members_render_ordered_by_candidate_key_not_by_name(self):
        # `name` order (Alpha, Zulu) contradicts `candidate_key` order
        # (component:alpha, component:zeta), so an implementation sorting on
        # the wrong field -- or not sorting at all -- fails.
        body = render.render_codebase_map(_map(), self._members())
        self.assertLess(body.index("component:alpha"),
                        body.index("component:zeta"))

    def test_each_member_links_to_its_note_path(self):
        body = render.render_codebase_map(_map(), self._members())
        self.assertIn("Components/alpha.md", body)
        self.assertIn("Components/zeta.md", body)

    def test_member_arrival_order_does_not_change_bytes(self):
        forward = render.render_codebase_map(_map(), self._members())
        backward = render.render_codebase_map(
            _map(), list(reversed(self._members())))
        self.assertEqual(forward, backward)

    def test_a_map_with_no_members_renders_a_placeholder(self):
        body = render.render_codebase_map(_map(member_count=0), [])
        self.assertIn("(none)", body)


class StrictInputTest(unittest.TestCase):
    def test_unknown_record_field_is_rejected(self):
        with self.assertRaises(render.RenderInputError):
            render.render_component(_component(surprise="x"))

    def test_missing_required_field_is_rejected(self):
        record = _component()
        del record["name"]
        with self.assertRaises(render.RenderInputError):
            render.render_component(record)

    def test_wrong_projection_type_is_rejected(self):
        with self.assertRaises(render.RenderInputError):
            render.render_component(_component(projection_type="arch_codebase_map"))

    def test_map_renderer_rejects_a_component_record(self):
        with self.assertRaises(render.RenderInputError):
            render.render_codebase_map(_component(), [])

    def test_unknown_member_field_is_rejected(self):
        with self.assertRaises(render.RenderInputError):
            render.render_codebase_map(_map(), [
                {"candidate_key": "component:a", "name": "A",
                 "note_path": "Components/a.md", "surprise": "x"}])


class NewNoteTest(unittest.TestCase):
    """The create-only composition: frontmatter must be the FIRST bytes of
    the file or no YAML parser reads it as properties, so it sits outside
    the generated region and is never rewritten on update.
    """

    def test_frontmatter_opens_the_file(self):
        text = render.compose_new_note(
            "arch-node:p:" + "a" * 32, "arch_component", "BODY\n")
        self.assertTrue(text.startswith("---\n"))

    def test_frontmatter_precedes_the_region_marker(self):
        text = render.compose_new_note(
            "arch-node:p:" + "a" * 32, "arch_component", "BODY\n")
        self.assertLess(text.index("---"), text.index(render.BEGIN))

    def test_frontmatter_carries_arch_id_and_projection_type(self):
        arch_id = "arch-node:p:" + "a" * 32
        text = render.compose_new_note(arch_id, "arch_component", "BODY\n")
        head = text.split(render.BEGIN)[0]
        self.assertIn(arch_id, head)
        self.assertIn("arch_component", head)

    def test_the_body_sits_inside_the_region(self):
        text = render.compose_new_note(
            "arch-node:p:" + "a" * 32, "arch_component", "BODY\n")
        inner = text.split(render.BEGIN)[1].split(render.END)[0]
        self.assertIn("BODY", inner)

    def test_a_user_owned_tail_follows_the_region(self):
        text = render.compose_new_note(
            "arch-node:p:" + "a" * 32, "arch_component", "BODY\n")
        self.assertTrue(text.rstrip().endswith(text.rstrip().splitlines()[-1]))
        self.assertGreater(len(text.split(render.END)[1].strip()), 0)

    def test_markers_are_the_architecture_pair_not_the_context_pair(self):
        self.assertEqual(render.BEGIN,
                         "<!-- bindle:architecture:generated:begin -->")
        self.assertEqual(render.END,
                         "<!-- bindle:architecture:generated:end -->")

    def test_is_pure(self):
        arch_id = "arch-node:p:" + "a" * 32
        self.assertEqual(
            render.compose_new_note(arch_id, "arch_component", "BODY\n"),
            render.compose_new_note(arch_id, "arch_component", "BODY\n"),
        )


if __name__ == "__main__":
    unittest.main()
