"""Tests for context_graph.evidence — the #181 evidence-reference
normalizer. Test names reference the fixture numbers from issue #181's
"Fixture corpus" list where applicable.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import evidence

PROJECT_ID = "project:5f56c9b95c41c298f70d6dd4e5db8c2a"
OTHER_PROJECT_ID = "project:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
BINDING_ID = "repository-binding:2b0f4e6c9a1d47f38e5c7a02b6d19f4e"
OTHER_BINDING_ID = "repository-binding:" + "c" * 32
REPO = "thomas-estep/bindle"


def norm(value, **kw):
    kw.setdefault("project_id", PROJECT_ID)
    kw.setdefault("repository", REPO)
    return evidence.normalize(value, **kw)


class TypedGitHubReferences(unittest.TestCase):
    # 1. Typed local issue.
    def test_typed_local_issue(self):
        r = norm("Issue #140")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-issue:thomas-estep/bindle#140")
        self.assertEqual(r["class"], "evidence")
        self.assertEqual(r["kind"], "github_issue")
        self.assertEqual(r["repository"], REPO)
        self.assertEqual(r["number"], 140)

    # 2. Typed repository-qualified issue.
    def test_typed_qualified_issue(self):
        r = norm("Issue owner/repo#140")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-issue:owner/repo#140")
        self.assertEqual(r["repository"], "owner/repo")

    # 3. Typed local PR.
    def test_typed_local_pr(self):
        r = norm("PR #143")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-pr:thomas-estep/bindle#143")
        self.assertEqual(r["kind"], "github_pr")

    # 4. Typed repository-qualified PR.
    def test_typed_qualified_pr(self):
        r = norm("PR owner/repo#143")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-pr:owner/repo#143")

    # 5. Canonical issue URL.
    def test_canonical_issue_url(self):
        r = norm("https://github.com/owner/repo/issues/140")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-issue:owner/repo#140")

    # 6. Canonical PR URL.
    def test_canonical_pr_url(self):
        r = norm("https://github.com/owner/repo/pull/143")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-pr:owner/repo#143")

    # 7. Issue and PR with the same number remain distinct.
    def test_issue_and_pr_same_number_distinct(self):
        i = norm("Issue owner/repo#140")
        p = norm("PR owner/repo#140")
        self.assertNotEqual(i["id"], p["id"])

    # 8. Bare local number remains unresolved.
    def test_bare_local_number_unresolved(self):
        r = norm("#140")
        self.assertEqual(r["status"], "unresolved")
        self.assertEqual(r["kind"], "github_number")
        self.assertEqual(r["repository"], REPO)
        self.assertEqual(r["number"], 140)
        self.assertEqual(r["reason"], "artifact_type_missing")

    # 9. Bare qualified number remains unresolved.
    def test_bare_qualified_number_unresolved(self):
        r = norm("owner/repo#140")
        self.assertEqual(r["status"], "unresolved")
        self.assertEqual(r["kind"], "github_number")
        self.assertEqual(r["repository"], "owner/repo")
        self.assertEqual(r["reason"], "artifact_type_missing")

    # 10. Explicit kind hint resolves a bare number.
    def test_kind_hint_resolves_bare_number(self):
        r = norm("#140", kind_hint="github_issue")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-issue:thomas-estep/bindle#140")

        r2 = norm("#140", kind_hint="github_pr")
        self.assertEqual(r2["status"], "normalized")
        self.assertEqual(r2["id"], "github-pr:thomas-estep/bindle#140")

    def test_kind_hint_resolves_bare_qualified_number(self):
        r = norm("owner/repo#140", kind_hint="github_pr")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-pr:owner/repo#140")


class LocalPathReferences(unittest.TestCase):
    # 11. Session path.
    def test_session_path(self):
        r = norm("sessions/2026-07-16-context-graph.md")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(
            r["id"],
            "session:%s:sessions/2026-07-16-context-graph.md" % PROJECT_ID,
        )
        self.assertEqual(r["kind"], "session")

    # 12. Handoff path.
    def test_handoff_path(self):
        r = norm("handoffs/2026-07-16.md")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "handoff:%s:handoffs/2026-07-16.md" % PROJECT_ID)
        self.assertEqual(r["kind"], "handoff")

    # 13. Repository design-document path with binding-qualified identity.
    def test_repository_document_path(self):
        r = norm(
            "docs/design/2026-07-16-context-graph.md",
            binding_ids=[BINDING_ID],
        )
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(
            r["id"],
            "document:%s:%s:docs/design/2026-07-16-context-graph.md"
            % (PROJECT_ID, BINDING_ID),
        )
        self.assertEqual(r["kind"], "document_repository")

    # 14. Absolute path rejected.
    def test_absolute_path_rejected(self):
        r = norm("/etc/passwd")
        self.assertEqual(r["status"], "rejected")

    def test_absolute_session_path_rejected(self):
        r = norm("/sessions/x.md")
        self.assertEqual(r["status"], "rejected")

    # 15. Parent traversal rejected.
    def test_traversal_rejected(self):
        r = norm("sessions/../../etc/passwd.md")
        self.assertEqual(r["status"], "rejected")

    def test_traversal_in_document_path_rejected(self):
        r = norm("docs/../../etc/passwd", binding_ids=[BINDING_ID])
        self.assertEqual(r["status"], "rejected")

    def test_project_local_document(self):
        r = norm("notes/local-thing.md", binding_ids=[])
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(
            r["id"],
            "document:%s:project-local:notes/local-thing.md" % PROJECT_ID,
        )
        self.assertEqual(r["kind"], "document_project_local")


class CommitPointers(unittest.TestCase):
    # 19. Short commit pointer recognized as unsupported.
    def test_backtick_commit_pointer(self):
        r = norm("`8f31d1b`")
        self.assertEqual(r["status"], "recognized_unsupported")
        self.assertEqual(r["kind"], "commit_pointer")
        self.assertEqual(r["value"], "8f31d1b")
        self.assertEqual(r["reason"], "commit_resolution_deferred")

    def test_commit_prefix_pointer(self):
        r = norm("commit 8f31d1b")
        self.assertEqual(r["status"], "recognized_unsupported")
        self.assertEqual(r["value"], "8f31d1b")

    def test_commit_pointer_normalizes_case(self):
        r = norm("`8F31D1B`")
        self.assertEqual(r["status"], "recognized_unsupported")
        self.assertEqual(r["value"], "8f31d1b")

    # 20. Non-hex commit pointer rejected.
    def test_non_hex_commit_pointer_rejected(self):
        r = norm("`nothexxx`")
        self.assertEqual(r["status"], "rejected")

    def test_commit_pointer_too_short_rejected(self):
        r = norm("`abc12`")
        self.assertEqual(r["status"], "rejected")

    def test_commit_pointer_too_long_rejected(self):
        r = norm("`" + "a" * 41 + "`")
        self.assertEqual(r["status"], "rejected")

    def test_commit_pointer_max_length_accepted(self):
        r = norm("`" + "a" * 40 + "`")
        self.assertEqual(r["status"], "recognized_unsupported")


class RejectedUrlsAndNumbers(unittest.TestCase):
    # 16. Non-GitHub URL rejected.
    def test_non_github_url_rejected(self):
        r = norm("https://example.com/owner/repo/issues/140")
        self.assertEqual(r["status"], "rejected")

    # 17. GitHub repository page without artifact rejected.
    def test_github_repo_page_without_artifact_rejected(self):
        r = norm("https://github.com/owner/repo")
        self.assertEqual(r["status"], "rejected")

    # 18. Zero or negative artifact number rejected.
    def test_zero_artifact_number_rejected(self):
        r = norm("Issue #0")
        self.assertEqual(r["status"], "rejected")

    def test_negative_artifact_number_rejected(self):
        r = norm("Issue #-5")
        self.assertEqual(r["status"], "rejected")

    # 21. Query strings and fragments do not change GitHub identity.
    def test_github_url_query_and_fragment_ignored(self):
        r = norm("https://github.com/owner/repo/issues/140?tab=comments#issuecomment-1")
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["id"], "github-issue:owner/repo#140")


class BatchOrdering(unittest.TestCase):
    # 22. Batch output preserves input order.
    def test_batch_preserves_order(self):
        values = ["PR #143", "Issue #140", "sessions/x.md"]
        results = [norm(v) for v in values]
        self.assertEqual(
            [r["id"] for r in results],
            [
                "github-pr:thomas-estep/bindle#143",
                "github-issue:thomas-estep/bindle#140",
                "session:%s:sessions/x.md" % PROJECT_ID,
            ],
        )

    # 23. Running the normalizer twice yields byte-identical output.
    def test_deterministic_repeat(self):
        self.assertEqual(norm("PR #143"), norm("PR #143"))


class MarkdownLinkEquivalence(unittest.TestCase):
    # 25. Session Markdown link normalizes to the same ID as its bare path.
    def test_session_markdown_link_same_id_as_bare(self):
        bare = norm("sessions/2026-07-16-context-graph.md")
        linked = norm("[context-graph session](sessions/2026-07-16-context-graph.md)")
        self.assertEqual(bare["status"], "normalized")
        self.assertEqual(linked["status"], "normalized")
        self.assertEqual(bare["id"], linked["id"])

    # 26. Handoff Markdown link normalizes to the same ID as its bare path.
    def test_handoff_markdown_link_same_id_as_bare(self):
        bare = norm("handoffs/2026-07-16.md")
        linked = norm("[handoff](handoffs/2026-07-16.md)")
        self.assertEqual(bare["id"], linked["id"])

    # 27. Document Markdown link normalizes to the same ID as its bare path.
    def test_document_markdown_link_same_id_as_bare(self):
        bare = norm("docs/design/2026-07-16-context-graph.md", binding_ids=[BINDING_ID])
        linked = norm(
            "[design](docs/design/2026-07-16-context-graph.md)",
            binding_ids=[BINDING_ID],
        )
        self.assertEqual(bare["id"], linked["id"])

    # 28. GitHub issue URL wrapped in a Markdown link normalizes to the same
    # ID as the bare URL.
    def test_github_url_markdown_link_same_id_as_bare(self):
        bare = norm("https://github.com/owner/repo/issues/140")
        linked = norm("[Issue #140](https://github.com/owner/repo/issues/140)")
        self.assertEqual(bare["id"], linked["id"])

    # 29. Changing only the Markdown label does not change identity.
    def test_markdown_label_does_not_affect_identity(self):
        a = norm("[renamed label](sessions/2026-07-16-context-graph.md)")
        b = norm("[a totally different label](sessions/2026-07-16-context-graph.md)")
        self.assertEqual(a["id"], b["id"])

    # 30. A local fragment does not change file identity and is retained
    # only as a locator.
    def test_local_fragment_retained_as_locator_not_identity(self):
        plain = norm("sessions/2026-07-16-context-graph.md")
        fragmented = norm("sessions/2026-07-16-context-graph.md#section-2")
        self.assertEqual(plain["id"], fragmented["id"])
        self.assertEqual(fragmented.get("fragment"), "section-2")
        self.assertNotIn("fragment", plain)

    # 31. Traversal inside a Markdown destination is rejected.
    def test_traversal_inside_markdown_destination_rejected(self):
        r = norm("[evil](sessions/../../etc/passwd.md)")
        self.assertEqual(r["status"], "rejected")

    # 32. A link embedded in surrounding prose is rejected.
    def test_link_embedded_in_prose_rejected(self):
        r = norm("see [label](sessions/x.md) for details")
        self.assertEqual(r["status"], "rejected")

    # 33. Markdown image syntax is rejected.
    def test_markdown_image_syntax_rejected(self):
        r = norm("![alt](sessions/x.md)")
        self.assertEqual(r["status"], "rejected")

    # 34. Reference-style Markdown links are rejected.
    def test_reference_style_markdown_rejected(self):
        r = norm("[label][ref]")
        self.assertEqual(r["status"], "rejected")

    # 35. Multiple links in one evidence atom are rejected.
    def test_multiple_links_in_one_atom_rejected(self):
        r = norm("[a](sessions/a.md) [b](sessions/b.md)")
        self.assertEqual(r["status"], "rejected")

    # 36. A malformed Markdown wrapper does not fall back to substring
    # extraction.
    def test_malformed_wrapper_does_not_extract_substring(self):
        r = norm("[label](sessions/x.md")
        self.assertEqual(r["status"], "rejected")
        self.assertNotIn("id", r)

    def test_local_query_string_rejected(self):
        r = norm("[bad](sessions/x.md?foo=bar)")
        self.assertEqual(r["status"], "rejected")

    def test_autolink_rejected(self):
        r = norm("<https://github.com/owner/repo/issues/140>")
        self.assertEqual(r["status"], "rejected")


class FieldLevelTokenization(unittest.TestCase):
    def nf(self, value, **kw):
        kw.setdefault("project_id", PROJECT_ID)
        kw.setdefault("repository", REPO)
        return evidence.normalize_field(value, **kw)

    # 37. A single evidence pointer in a field.
    def test_single_pointer(self):
        r = self.nf("PR #143")
        self.assertEqual(r["status"], "field_ok")
        self.assertEqual(len(r["results"]), 1)
        self.assertEqual(r["results"][0]["id"], "github-pr:thomas-estep/bindle#143")

    # 38. Two bare references in one field.
    def test_two_bare_references(self):
        r = self.nf("#140, #141")
        self.assertEqual(r["status"], "field_ok")
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][0]["number"], 140)
        self.assertEqual(r["results"][1]["number"], 141)

    # 39. A Markdown link plus a typed PR in one field.
    def test_markdown_link_plus_typed_pr(self):
        r = self.nf("[session](sessions/x.md), PR #143")
        self.assertEqual(r["status"], "field_ok")
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][0]["kind"], "session")
        self.assertEqual(r["results"][1]["kind"], "github_pr")

    # 40. A comma inside a Markdown link label is not a separator.
    def test_comma_inside_link_label_not_separator(self):
        r = self.nf("[a, b, c](sessions/x.md), PR #143")
        self.assertEqual(r["status"], "field_ok")
        self.assertEqual(len(r["results"]), 2)

    # 41. A comma inside a Markdown link destination is not a separator.
    def test_comma_inside_link_destination_not_separator(self):
        # The destination itself is not a valid path once it contains a
        # comma, so it will be individually rejected -- but it must not be
        # SPLIT into two field members.
        r = self.nf("[a](sessions/x,y.md), PR #143")
        self.assertEqual(r["status"], "field_ok")
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][1]["kind"], "github_pr")

    # 42. A comma inside a backtick commit atom is not a separator.
    def test_comma_inside_backtick_not_separator(self):
        r = self.nf("`8f3,1d1b`, PR #143")
        self.assertEqual(r["status"], "field_ok")
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][1]["kind"], "github_pr")

    # 43. Repeated references normalize to one evidence node while
    # preserving occurrence basis.
    def test_repeated_references_preserve_occurrence(self):
        r = self.nf("PR #143, PR #143")
        self.assertEqual(r["status"], "field_ok")
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][0]["id"], r["results"][1]["id"])

    # 44. Empty list members rejected with a precise field-level reason.
    def test_empty_list_member_rejected(self):
        r = self.nf("PR #143, , Issue #140")
        self.assertEqual(r["status"], "field_rejected")
        self.assertIn("reason", r)

    def test_trailing_comma_rejected(self):
        r = self.nf("PR #143,")
        self.assertEqual(r["status"], "field_rejected")

    # 45. Malformed or embedded wrappers rejected at field level.
    def test_malformed_wrapper_in_field(self):
        r = self.nf("see [label](sessions/x.md) for details, PR #143")
        self.assertEqual(r["status"], "field_ok")
        self.assertEqual(r["results"][0]["status"], "rejected")
        self.assertEqual(r["results"][1]["kind"], "github_pr")

    # 46. Unbalanced wrappers rejected without substring recovery.
    def test_unbalanced_wrapper_field_rejected(self):
        r = self.nf("[label](sessions/x.md, PR #143")
        self.assertEqual(r["status"], "field_rejected")

    # 47. Deterministic order across repeated runs.
    def test_deterministic_field_order(self):
        r1 = self.nf("PR #143, Issue #140")
        r2 = self.nf("PR #143, Issue #140")
        self.assertEqual(r1, r2)


class ProjectAndRepositoryIdentity(unittest.TestCase):
    # 48. The same session path under two different opaque project IDs
    # produces different evidence IDs.
    def test_same_path_different_project_ids(self):
        a = norm("sessions/x.md", project_id=PROJECT_ID)
        b = norm("sessions/x.md", project_id=OTHER_PROJECT_ID)
        self.assertNotEqual(a["id"], b["id"])

    # 49. Changing repository coordinates leaves session and handoff
    # identities unchanged.
    def test_repository_change_does_not_affect_session_identity(self):
        a = norm("sessions/x.md", repository="owner/repo")
        b = norm("sessions/x.md", repository="other-owner/other-repo")
        self.assertEqual(a["id"], b["id"])

    # 50. Repositoryless project: project-local document form validates.
    def test_repositoryless_project_local_document(self):
        r = norm("docs/design/x.md", binding_ids=[])
        self.assertEqual(r["status"], "normalized")
        self.assertEqual(r["kind"], "document_project_local")

    # 51. Two configured repositories containing the same relative document
    # path produce distinct binding-qualified identities.
    def test_two_bindings_same_path_distinct_identity(self):
        a = norm("docs/x.md", binding_ids=[BINDING_ID])
        b = norm("docs/x.md", binding_ids=[OTHER_BINDING_ID])
        self.assertNotEqual(a["id"], b["id"])

    # 52. Repository rename with unchanged binding ID preserves document
    # identity.
    def test_repository_rename_preserves_document_identity(self):
        a = norm("docs/x.md", binding_ids=[BINDING_ID], repository="old/name")
        b = norm("docs/x.md", binding_ids=[BINDING_ID], repository="new/name")
        self.assertEqual(a["id"], b["id"])

    # 53. Binding ambiguity leaves a repository-document reference
    # unresolved.
    def test_binding_ambiguity_unresolved(self):
        r = norm("docs/x.md", binding_ids=[BINDING_ID, OTHER_BINDING_ID])
        self.assertEqual(r["status"], "unresolved")
        self.assertEqual(r["reason"], "binding_ambiguous")

    # 54. A repository-shaped --project-id such as
    # project:thomas-estep/bindle is rejected.
    def test_repository_shaped_project_id_rejected(self):
        with self.assertRaises(ValueError):
            norm("sessions/x.md", project_id="project:thomas-estep/bindle")


class CommandSurfaceBehavior(unittest.TestCase):
    def test_missing_default_repository_bare_number_unresolved(self):
        r = norm("#140", repository=None)
        self.assertEqual(r["status"], "unresolved")
        self.assertEqual(r["reason"], "repository_not_configured")

    def test_missing_default_repository_typed_local_unresolved(self):
        r = norm("Issue #140", repository=None)
        self.assertEqual(r["status"], "unresolved")
        self.assertEqual(r["reason"], "repository_not_configured")

    def test_batch_helper_preserves_order(self):
        records = [{"value": "PR #143"}, {"value": "Issue #140"}]
        results = evidence.normalize_batch(
            records, project_id=PROJECT_ID, repository=REPO
        )
        self.assertEqual(
            [r["id"] for r in results],
            [
                "github-pr:thomas-estep/bindle#143",
                "github-issue:thomas-estep/bindle#140",
            ],
        )


if __name__ == "__main__":
    unittest.main()
