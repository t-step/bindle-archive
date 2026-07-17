import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import ids


class TestParseTypedId(unittest.TestCase):
    def test_project_id(self):
        r = ids.parse_typed_id("project:5f56c9b95c41c298f70d6dd4e5db8c2a")
        self.assertEqual(r["type"], "project")
        self.assertEqual(r["hex"], "5f56c9b95c41c298f70d6dd4e5db8c2a")

    def test_project_id_repo_shaped_is_malformed(self):
        with self.assertRaises(ids.MalformedIdError):
            ids.parse_typed_id("project:thomas-estep/bindle")

    def test_context_node_id(self):
        r = ids.parse_typed_id(
            "context-node:bindle:8ef8f9a58ac1046c7fd772a83a21e311"
        )
        self.assertEqual(r["type"], "context_node")
        self.assertEqual(r["creation_project_slug"], "bindle")
        self.assertEqual(r["hex"], "8ef8f9a58ac1046c7fd772a83a21e311")

    def test_context_node_id_short_hex_is_malformed(self):
        with self.assertRaises(ids.MalformedIdError):
            ids.parse_typed_id("context-node:bindle:0123456789abcdef")

    def test_repository_binding_id(self):
        r = ids.parse_typed_id(
            "repository-binding:2b0f4e6c9a1d47f38e5c7a02b6d19f4e"
        )
        self.assertEqual(r["type"], "repository_binding")

    def test_session_id(self):
        r = ids.parse_typed_id(
            "session:project:5f56c9b95c41c298f70d6dd4e5db8c2a:"
            "sessions/2026-07-16-context-graph.md"
        )
        self.assertEqual(r["type"], "session")
        self.assertEqual(
            r["project_id"], "project:5f56c9b95c41c298f70d6dd4e5db8c2a"
        )
        self.assertEqual(
            r["relative_path"], "sessions/2026-07-16-context-graph.md"
        )

    def test_document_repository_id(self):
        r = ids.parse_typed_id(
            "document:project:5f56c9b95c41c298f70d6dd4e5db8c2a:"
            "repository-binding:2b0f4e6c9a1d47f38e5c7a02b6d19f4e:"
            "docs/design/2026-07-16-context-graph.md"
        )
        self.assertEqual(r["type"], "document_repository")
        self.assertEqual(
            r["repository_relative_path"],
            "docs/design/2026-07-16-context-graph.md",
        )

    def test_document_project_local_id(self):
        r = ids.parse_typed_id(
            "document:project:5f56c9b95c41c298f70d6dd4e5db8c2a:"
            "project-local:notes/scratch.md"
        )
        self.assertEqual(r["type"], "document_project_local")
        self.assertEqual(r["project_relative_path"], "notes/scratch.md")

    def test_github_issue_and_pr_ids_stay_distinct(self):
        issue = ids.parse_typed_id("github-issue:thomas-estep/bindle#140")
        pr = ids.parse_typed_id("github-pr:thomas-estep/bindle#140")
        self.assertEqual(issue["type"], "github_issue")
        self.assertEqual(pr["type"], "github_pr")
        self.assertNotEqual(issue["id"], pr["id"])

    def test_candidate_key_and_anchor_candidate_key(self):
        r1 = ids.parse_typed_id("candidate:sha256:" + "a" * 64)
        r2 = ids.parse_typed_id("anchor-candidate:sha256:" + "b" * 64)
        self.assertEqual(r1["type"], "candidate_key")
        self.assertEqual(r2["type"], "anchor_candidate_key")

    def test_unrecognized_string_raises(self):
        with self.assertRaises(ids.MalformedIdError):
            ids.parse_typed_id("not-a-typed-id-at-all")

    def test_empty_string_raises(self):
        with self.assertRaises(ids.MalformedIdError):
            ids.parse_typed_id("")


class TestFormatters(unittest.TestCase):
    def test_format_project_id_roundtrips(self):
        hexval = "5f56c9b95c41c298f70d6dd4e5db8c2a"
        formatted = ids.format_project_id(hexval)
        self.assertEqual(formatted, "project:" + hexval)
        self.assertEqual(ids.parse_typed_id(formatted)["hex"], hexval)

    def test_format_project_id_rejects_bad_hex(self):
        with self.assertRaises(ValueError):
            ids.format_project_id("not-hex")

    def test_format_context_node_id_rejects_bad_slug(self):
        with self.assertRaises(ValueError):
            ids.format_context_node_id("Not A Slug", "a" * 32)

    def test_format_document_project_local_uses_reserved_literal(self):
        formatted = ids.format_document_project_local_id(
            "project:" + "a" * 32, "notes/x.md"
        )
        self.assertIn(":project-local:", formatted)


if __name__ == "__main__":
    unittest.main()
