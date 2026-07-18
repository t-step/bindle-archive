import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from context_graph import canonical, map_parser, map_writer  # noqa: E402

# Frame fields a real caller would hold constant for one map file across a
# whole apply run (compiler.py:236-247 derives the same two from config +
# project_slug). Arbitrary but fixed for the fixture.
PROJECT_ID = "demo-project"
MAP_PATH = "notes/context-graph/demo-project/map.md"

MAP = """# Demo — project map

## Brief

## Decisions

### Use a single-writer lock (2026-07, settled)
why: correctness
so: no concurrent identity allocation

## Learnings
## Assumptions & tensions
## Open questions
## Superseded
"""


class PlanMapBytesTest(unittest.TestCase):
    def _entries(self, text):
        return map_parser.parse_project_map(text)["entries"]

    def _fp_of_first_unanchored(self, text):
        for e in self._entries(text):
            if not e["anchored"]:
                return canonical.entry_fingerprint(
                    PROJECT_ID, MAP_PATH, e["section"], e["kind"], e["entry_bytes"]
                )
        raise AssertionError("no unanchored entry in fixture")

    def test_inserts_marker_on_anchor_line_only(self):
        fp = self._fp_of_first_unanchored(MAP)
        anchors = [{"assigned_id": "context-node:demo:deadbeef", "entry_fingerprint": fp}]
        new_text, findings = map_writer.plan_map_bytes(
            MAP, self._entries(MAP), anchors, PROJECT_ID, MAP_PATH
        )
        self.assertEqual(findings, [])
        self.assertIn(
            "### Use a single-writer lock (2026-07, settled) "
            "<!-- bindle:context-id: context-node:demo:deadbeef -->",
            new_text,
        )
        # exactly one line differs
        diff = [(a, b) for a, b in zip(MAP.splitlines(), new_text.splitlines()) if a != b]
        self.assertEqual(len(diff), 1)

    def test_unmatched_anchor_reports_and_writes_nothing(self):
        anchors = [{"assigned_id": "context-node:demo:0000", "entry_fingerprint": "sha256:nomatch"}]
        new_text, findings = map_writer.plan_map_bytes(
            MAP, self._entries(MAP), anchors, PROJECT_ID, MAP_PATH
        )
        self.assertEqual(new_text, MAP)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "stale_anchor_no_entry")

    def test_no_anchors_is_identity(self):
        new_text, findings = map_writer.plan_map_bytes(MAP, self._entries(MAP), [], PROJECT_ID, MAP_PATH)
        self.assertEqual(new_text, MAP)
        self.assertEqual(findings, [])

    def test_already_anchored_entry_never_reanchored(self):
        # Same entry, already carrying a marker -- its parsed entry_bytes are
        # marker-stripped (map_parser._strip_markers_only), so an authorized
        # anchor computed over that same content would, if matching were
        # naive, look like a match. It must not be: only *unanchored*
        # entries are eligible targets.
        anchored_map = MAP.replace(
            "### Use a single-writer lock (2026-07, settled)",
            "### Use a single-writer lock (2026-07, settled) "
            "<!-- bindle:context-id: context-node:demo:11111111111111111111111111111111 -->",
        )
        entries = self._entries(anchored_map)
        decision = next(e for e in entries if e["kind"] == "decision")
        self.assertTrue(decision["anchored"])
        fp = canonical.entry_fingerprint(
            PROJECT_ID, MAP_PATH, decision["section"], decision["kind"], decision["entry_bytes"]
        )
        anchors = [{"assigned_id": "context-node:demo:new", "entry_fingerprint": fp}]
        new_text, findings = map_writer.plan_map_bytes(anchored_map, entries, anchors, PROJECT_ID, MAP_PATH)
        self.assertEqual(new_text, anchored_map)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "stale_anchor_no_entry")


if __name__ == "__main__":
    unittest.main()
