"""Tests for context_graph.map_parser -- #183's project-map entry
extraction. Test names reference the fixture numbers from #183's own issue
body "Fixtures and pressure tests" list where applicable.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import map_parser

SLUG = "bindle"


def _map(*, brief="", decisions="", learnings="", assumptions="",
         questions="", superseded=""):
    return (
        "## Brief\n%s\n"
        "## Decisions\n%s\n"
        "## Learnings\n%s\n"
        "## Assumptions & tensions\n%s\n"
        "## Open questions\n%s\n"
        "## Superseded\n%s\n"
    ) % (brief, decisions, learnings, assumptions, questions, superseded)


def _by_kind(entries, kind):
    return [e for e in entries if e["kind"] == kind]


class CanonicalEntryShapes(unittest.TestCase):
    # 1. All canonical entry shapes parse to one node each.
    def test_decision(self):
        text = _map(decisions=(
            "### Ship it (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: reasons\n"
            "so: answer\n"
            "revisit-when: never\n"
            "evidence: docs/x.md\n" % SLUG
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        decisions = _by_kind(result["entries"], "decision")
        self.assertEqual(len(decisions), 1)
        d = decisions[0]
        self.assertEqual(d["label"], "Ship it")
        self.assertEqual(d["status"], "current")
        self.assertTrue(d["anchored"])
        self.assertEqual(d["evidence_raw"], "docs/x.md")

    def test_learning(self):
        text = _map(learnings=(
            "### Learned something (2026-07) "
            "<!-- bindle:context-id: context-node:%s:22222222222222222222222222222222 -->\n"
            "why: reasons\n"
            "so: answer\n"
            "evidence: docs/y.md\n" % SLUG
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        learnings = _by_kind(result["entries"], "learning")
        self.assertEqual(len(learnings), 1)
        self.assertEqual(learnings[0]["label"], "Learned something")

    def test_assumption(self):
        text = _map(assumptions=(
            "- We assume X — confidence: medium — evidence: docs/z.md "
            "<!-- bindle:context-id: context-node:%s:33333333333333333333333333333333 -->\n"
            % SLUG
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        assumptions = _by_kind(result["entries"], "assumption")
        self.assertEqual(len(assumptions), 1)
        self.assertEqual(assumptions[0]["confidence"], "medium")
        self.assertEqual(assumptions[0]["evidence_raw"], "docs/z.md")

    def test_question(self):
        text = _map(questions=(
            "- Should we do Y? (open) — so: it clarifies scope — evidence: docs/q.md "
            "<!-- bindle:context-id: context-node:%s:44444444444444444444444444444444 -->\n"
            % SLUG
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        questions = _by_kind(result["entries"], "question")
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["status"], "open")
        self.assertEqual(questions[0]["label"], "Should we do Y?")

    def test_superseded_typed_tombstone(self):
        text = _map(superseded=(
            "- decision: Old claim (retired 2026-06) → replaced "
            "<!-- bindle:context-id: context-node:%s:55555555555555555555555555555555 -->\n"
            "  why: old\n  so: old\n  revisit-when: old\n  evidence: old.md\n" % SLUG
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        superseded = _by_kind(result["entries"], "decision")
        self.assertEqual(len(superseded), 1)
        self.assertEqual(superseded[0]["status"], "superseded")
        self.assertEqual(superseded[0]["evidence_raw"], "old.md")

    # 2. Owner-authored unrelated HTML comments are preserved and ignored.
    def test_unrelated_html_comment_preserved_in_entry_bytes(self):
        text = _map(decisions=(
            "### Ship it (2026-07, settled) <!-- an unrelated note --> "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: reasons\nso: answer\nrevisit-when: never\nevidence: docs/x.md\n" % SLUG
        ))
        result = map_parser.parse_project_map(text)
        d = _by_kind(result["entries"], "decision")[0]
        self.assertIn(b"<!-- an unrelated note -->", d["entry_bytes"])
        self.assertNotIn(b"bindle:context-id", d["entry_bytes"])


class Tensions(unittest.TestCase):
    # 3. A valid two-sided tension parses as one tension node with two
    # ordered sides.
    def test_two_sided_tension(self):
        text = _map(assumptions=(
            "- Speed vs correctness — confidence: high "
            "<!-- bindle:context-id: context-node:%s:66666666666666666666666666666666 -->\n"
            "  - Speed matters — evidence: sessions/a.md\n"
            "  - Correctness matters — evidence: sessions/b.md\n" % SLUG
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        tensions = _by_kind(result["entries"], "tension")
        self.assertEqual(len(tensions), 1)
        t = tensions[0]
        self.assertEqual(len(t["sides"]), 2)
        self.assertEqual(t["sides"][0]["label"], "Speed matters")
        self.assertEqual(t["sides"][1]["evidence_raw"], "sessions/b.md")

    # 4. Malformed tension cardinality is reported.
    def test_one_sided_is_a_conflict_not_a_tension(self):
        text = _map(assumptions=(
            "- Speed vs correctness — confidence: high "
            "<!-- bindle:context-id: context-node:%s:66666666666666666666666666666666 -->\n"
            "  - Only one side — evidence: sessions/a.md\n" % SLUG
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(_by_kind(result["entries"], "tension"), [])
        self.assertEqual(_by_kind(result["entries"], "assumption"), [])
        codes = [c["code"] for c in result["conflicts"]]
        self.assertIn("tension-cardinality", codes)

    def test_three_sided_is_a_conflict(self):
        text = _map(assumptions=(
            "- Three-way split — confidence: low "
            "<!-- bindle:context-id: context-node:%s:77777777777777777777777777777777 -->\n"
            "  - side one — evidence: a.md\n"
            "  - side two — evidence: b.md\n"
            "  - side three — evidence: c.md\n" % SLUG
        ))
        result = map_parser.parse_project_map(text)
        codes = [c["code"] for c in result["conflicts"]]
        self.assertIn("tension-cardinality", codes)

    # 5. An identity marker on a child side is reported.
    def test_marker_on_tension_side_is_a_conflict(self):
        text = _map(assumptions=(
            "- Speed vs correctness — confidence: high "
            "<!-- bindle:context-id: context-node:%s:66666666666666666666666666666666 -->\n"
            "  - Speed matters — evidence: sessions/a.md "
            "<!-- bindle:context-id: context-node:%s:88888888888888888888888888888888 -->\n"
            "  - Correctness matters — evidence: sessions/b.md\n" % (SLUG, SLUG)
        ))
        result = map_parser.parse_project_map(text)
        codes = [c["code"] for c in result["conflicts"]]
        self.assertIn("misplaced-marker", codes)


class Retirement(unittest.TestCase):
    # 6. Typed retirement with and without replacement.
    def test_retirement_without_replacement(self):
        text = _map(superseded=(
            "- learning: Old thing (retired 2026-06) → no longer true "
            "<!-- bindle:context-id: context-node:%s:99999999999999999999999999999999 -->\n"
            "  why: old\n  so: old\n  evidence: old.md\n" % SLUG
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        entries = _by_kind(result["entries"], "learning")
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0]["superseded_by"])

    def test_retirement_with_replacement(self):
        replacement_id = "context-node:%s:11111111111111111111111111111111" % SLUG
        retired_id = "context-node:%s:99999999999999999999999999999999" % SLUG
        text = _map(
            decisions=(
                "### New claim (2026-07, settled) "
                "<!-- bindle:context-id: %s -->\n"
                "why: x\nso: y\nrevisit-when: z\nevidence:\n" % replacement_id
            ),
            superseded=(
                "- decision: Old claim (retired 2026-06) → replaced by New claim "
                "<!-- bindle:context-id: %s --> "
                "<!-- bindle:superseded-by: %s -->\n"
                "  why: old\n  so: old\n  revisit-when: old\n  evidence:\n"
                % (retired_id, replacement_id)
            ),
        )
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        retired = [e for e in result["entries"] if e["id"] == retired_id][0]
        self.assertEqual(retired["superseded_by"], replacement_id)

    # 8. Unresolved and self-referential replacement IDs are conflicts.
    def test_unresolved_superseded_by(self):
        text = _map(superseded=(
            "- decision: Old claim (retired 2026-06) → replaced "
            "<!-- bindle:context-id: context-node:%s:99999999999999999999999999999999 --> "
            "<!-- bindle:superseded-by: context-node:%s:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->\n"
            "  why: old\n  so: old\n  revisit-when: old\n  evidence:\n" % (SLUG, SLUG)
        ))
        result = map_parser.parse_project_map(text)
        codes = [c["code"] for c in result["conflicts"]]
        self.assertIn("superseded-by-unresolved", codes)

    def test_self_referential_superseded_by(self):
        own_id = "context-node:%s:99999999999999999999999999999999" % SLUG
        text = _map(superseded=(
            "- decision: Old claim (retired 2026-06) → replaced "
            "<!-- bindle:context-id: %s --> "
            "<!-- bindle:superseded-by: %s -->\n"
            "  why: old\n  so: old\n  revisit-when: old\n  evidence:\n" % (own_id, own_id)
        ))
        result = map_parser.parse_project_map(text)
        codes = [c["code"] for c in result["conflicts"]]
        self.assertIn("superseded-by-self-referential", codes)


class DuplicateIds(unittest.TestCase):
    # 9. Duplicate IDs spanning active and Superseded sections are conflicts.
    def test_duplicate_id_across_sections(self):
        dup_id = "context-node:%s:11111111111111111111111111111111" % SLUG
        text = _map(
            decisions=(
                "### Live claim (2026-07, settled) <!-- bindle:context-id: %s -->\n"
                "why: x\nso: y\nrevisit-when: z\nevidence:\n" % dup_id
            ),
            superseded=(
                "- decision: Also this (retired 2026-06) → dup "
                "<!-- bindle:context-id: %s -->\n"
                "  why: x\nso: y\nrevisit-when: z\nevidence:\n" % dup_id
            ),
        )
        result = map_parser.parse_project_map(text)
        codes = [c["code"] for c in result["conflicts"]]
        self.assertIn("duplicate-id", codes)


class Unanchored(unittest.TestCase):
    def test_unanchored_entry_included_with_no_id(self):
        text = _map(assumptions=(
            "- An unanchored assumption — confidence: low — evidence: docs/w.md\n"
        ))
        result = map_parser.parse_project_map(text)
        self.assertEqual(result["conflicts"], [])
        assumptions = _by_kind(result["entries"], "assumption")
        self.assertEqual(len(assumptions), 1)
        self.assertFalse(assumptions[0]["anchored"])
        self.assertIsNone(assumptions[0]["id"])


class MissingSections(unittest.TestCase):
    def test_missing_required_section_is_a_conflict(self):
        text = (
            "## Brief\n\n## Decisions\n\n## Assumptions & tensions\n\n"
            "## Open questions\n\n## Superseded\n\n"
        )
        result = map_parser.parse_project_map(text)
        missing = [c for c in result["conflicts"] if c["code"] == "missing-section"]
        self.assertEqual(len(missing), 1)
        self.assertIn("learnings", missing[0]["message"])

    def test_all_six_sections_present_no_conflict(self):
        text = _map()
        result = map_parser.parse_project_map(text)
        self.assertEqual(
            [c for c in result["conflicts"] if c["code"] == "missing-section"], []
        )


if __name__ == "__main__":
    unittest.main()
