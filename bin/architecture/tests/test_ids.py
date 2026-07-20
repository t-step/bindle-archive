"""Unit tests for architecture.ids — the arch-node identity grammar (#228)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from architecture import ids as arch_ids
from context_graph import ids as cg_ids

PROJECT_ID = "project:" + "a" * 32
NODE_HEX = "b" * 32
ARCH_ID = "arch-node:%s:%s" % (PROJECT_ID, NODE_HEX)


class TestRoundTrip(unittest.TestCase):
    def test_format_then_parse_recovers_components(self):
        formatted = arch_ids.format_arch_node_id(PROJECT_ID, NODE_HEX)
        self.assertEqual(formatted, ARCH_ID)
        parsed = arch_ids.parse_arch_node_id(formatted)
        self.assertEqual(parsed["type"], "arch_node")
        self.assertEqual(parsed["id"], ARCH_ID)
        self.assertEqual(parsed["project_id"], PROJECT_ID)
        self.assertEqual(parsed["hex"], NODE_HEX)

    def test_parse_carries_the_full_project_token_not_the_bare_hex(self):
        # The frozen grammar embeds the whole `project:<hex>` token, so a
        # consumer can hand project_id straight back to context_graph.ids
        # without reassembling it.
        parsed = arch_ids.parse_arch_node_id(ARCH_ID)
        self.assertEqual(
            cg_ids.parse_typed_id(parsed["project_id"])["type"], "project"
        )

    def test_is_arch_node_id_agrees_with_parse(self):
        self.assertTrue(arch_ids.is_arch_node_id(ARCH_ID))
        self.assertFalse(arch_ids.is_arch_node_id("context-node:bindle:" + NODE_HEX))


class TestMalformedRejected(unittest.TestCase):
    MALFORMED = (
        ("empty string", ""),
        ("not a string", None),
        ("bare prefix", "arch-node:"),
        ("no project token", "arch-node:%s" % NODE_HEX),
        ("bare project hex", "arch-node:%s:%s" % ("a" * 32, NODE_HEX)),
        ("uppercase node hex", "arch-node:%s:%s" % (PROJECT_ID, "B" * 32)),
        ("uppercase project hex", "arch-node:project:%s:%s" % ("A" * 32, NODE_HEX)),
        ("short node hex", "arch-node:%s:%s" % (PROJECT_ID, "b" * 31)),
        ("long node hex", "arch-node:%s:%s" % (PROJECT_ID, "b" * 33)),
        ("trailing segment", "%s:extra" % ARCH_ID),
        ("leading whitespace", " %s" % ARCH_ID),
        ("trailing newline", "%s\n" % ARCH_ID),
        ("context-node id", "context-node:bindle:%s" % NODE_HEX),
        ("project id", PROJECT_ID),
        ("unknown prefix", "arch:%s:%s" % (PROJECT_ID, NODE_HEX)),
    )

    def test_malformed_inputs_raise(self):
        for label, value in self.MALFORMED:
            with self.subTest(case=label):
                with self.assertRaises(arch_ids.MalformedArchIdError):
                    arch_ids.parse_arch_node_id(value)

    def test_malformed_error_carries_structured_detail(self):
        with self.assertRaises(arch_ids.MalformedArchIdError) as caught:
            arch_ids.parse_arch_node_id("arch-node:nope")
        self.assertEqual(caught.exception.id_str, "arch-node:nope")
        self.assertTrue(caught.exception.reason)

    def test_is_arch_node_id_never_raises(self):
        for _, value in self.MALFORMED:
            self.assertFalse(arch_ids.is_arch_node_id(value))


class TestFormatValidation(unittest.TestCase):
    def test_bad_project_id_rejected(self):
        for bad in ("a" * 32, "project:" + "A" * 32, "project:" + "a" * 31, ""):
            with self.subTest(project_id=bad):
                with self.assertRaises(ValueError):
                    arch_ids.format_arch_node_id(bad, NODE_HEX)

    def test_bad_hex_rejected(self):
        for bad in ("b" * 31, "b" * 33, "B" * 32, "", "g" * 32):
            with self.subTest(hex32=bad):
                with self.assertRaises(ValueError):
                    arch_ids.format_arch_node_id(PROJECT_ID, bad)


class TestContextGraphIdentityStaysSeparate(unittest.TestCase):
    """#228 frozen: the arch-node parser is ABSENT from context_graph.ids, so
    an arch-node id can never pass context-graph node validation."""

    def test_arch_node_parser_absent_from_context_graph_ids(self):
        source_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "context_graph", "ids.py"
        )
        with open(source_path, "r") as handle:
            source = handle.read()
        self.assertNotIn("arch-node", source)
        self.assertNotIn("arch_node", source)

    def test_parse_typed_id_rejects_an_arch_node_id(self):
        with self.assertRaises(cg_ids.MalformedIdError):
            cg_ids.parse_typed_id(ARCH_ID)

    def test_context_graph_validation_rejects_an_arch_node_id(self):
        from context_graph import validation

        findings = validation._check_nodes(
            [{"id": ARCH_ID, "class": "concept", "kind": "component"}], None
        )
        self.assertIn(
            "E_NODE_MALFORMED_ID", [finding["code"] for finding in findings]
        )

    def test_a_context_node_id_is_not_an_arch_node_id(self):
        context_node_id = cg_ids.format_context_node_id("bindle", NODE_HEX)
        self.assertFalse(arch_ids.is_arch_node_id(context_node_id))
        with self.assertRaises(arch_ids.MalformedArchIdError):
            arch_ids.parse_arch_node_id(context_node_id)


if __name__ == "__main__":
    unittest.main()
