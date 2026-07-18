"""Tests for context_graph.compiler -- the #183 deterministic compiler.
Test names reference the fixture numbers from #183's own issue body
"Fixtures and pressure tests" list where applicable.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import compiler
from context_graph import config
from context_graph import github_adapter


class FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stub_adapter(issue_ok=True, issue_title="Issue title"):
    def run(args, timeout):
        # args: [kind, "view", "<number>", "--repo", "<owner/repo>", "--json", "<fields>"]
        number = int(args[2])
        if args[0] == "issue":
            if issue_ok:
                return FakeProc(0, json.dumps({
                    "number": number, "title": issue_title, "state": "OPEN", "url": "https://x",
                }))
            return FakeProc(1, "", "Could not resolve to an Issue")
        if args[0] == "pr" and "closingIssuesReferences" in args[-1]:
            return FakeProc(0, json.dumps({"number": number, "closingIssuesReferences": []}))
        return FakeProc(0, json.dumps({
            "number": number, "title": "PR title", "state": "OPEN", "url": "https://x",
            "isDraft": False, "mergedAt": None,
        }))
    return github_adapter.GitHubAdapter(run=run)


class CompilerTestBase(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)
        self.slug = "proj"

    def write_map(self, text):
        project_dir = os.path.join(self.notes_home, "projects", self.slug)
        os.makedirs(project_dir, exist_ok=True)
        with open(os.path.join(project_dir, "map.md"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def init(self):
        config.init_project(self.notes_home, self.slug)

    def add_repo(self, alias, coordinates, is_default=False):
        return config.add_repository(
            self.notes_home, self.slug, alias=alias, provider="github",
            coordinates=coordinates, is_default=is_default,
        )

    def project_id(self):
        cfg = config.load_config(config.config_path(self.notes_home, self.slug))
        return cfg["project_id"]

    def base_map(self, decisions="", assumptions="", superseded=""):
        return (
            "## Brief\n\n## Decisions\n%s\n## Learnings\n\n"
            "## Assumptions & tensions\n%s\n## Open questions\n\n"
            "## Superseded\n%s\n" % (decisions, assumptions, superseded)
        )


class ConfigurationBoundary(unittest.TestCase):
    def setUp(self):
        self.notes_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.notes_home, ignore_errors=True)

    # 16. Missing or malformed project_id blocks graph construction and
    # allocates nothing.
    def test_missing_configuration_raises(self):
        with self.assertRaises(compiler.CompilerError) as ctx:
            compiler.compile_preview(self.notes_home, "nope")
        self.assertEqual(ctx.exception.findings[0]["code"], "E_CONFIG_MISSING")

    def test_malformed_configuration_raises(self):
        config.init_project(self.notes_home, "proj")
        cfg_path = config.config_path(self.notes_home, "proj")
        with open(cfg_path, "w") as fh:
            json.dump({"schema_version": 1, "project_id": "not-a-project-id",
                       "project_slug": "proj", "repositories": []}, fh)
        with self.assertRaises(compiler.CompilerError):
            compiler.compile_preview(self.notes_home, "proj")


class NoRepositoryConfigured(CompilerTestBase):
    # 11. No repository configured: map, session, and handoff context still
    # compile.
    def test_repositoryless_project_still_compiles(self):
        self.init()
        self.write_map(self.base_map(decisions=(
            "### A decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: x\nso: y\nrevisit-when: z\nevidence: sessions/2026-07-01-x.md\n"
            % self.slug
        )))
        preview = compiler.compile_preview(self.notes_home, self.slug)
        self.assertEqual(preview["conflicts"], [])
        session_nodes = [n for n in preview["nodes"] if n["kind"] == "session"]
        self.assertEqual(len(session_nodes), 1)

    def test_bare_github_reference_unresolved_without_repository(self):
        self.init()
        self.write_map(self.base_map(decisions=(
            "### A decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: x\nso: y\nrevisit-when: z\nevidence: Issue #5\n" % self.slug
        )))
        preview = compiler.compile_preview(self.notes_home, self.slug)
        codes = [c["code"] for c in preview["conflicts"]]
        self.assertIn("unresolved-evidence-pointer", codes)


class MultipleRepositories(CompilerTestBase):
    # 12. Multiple repositories with one default.
    def test_bare_reference_resolves_via_default(self):
        self.init()
        self.add_repo("primary", "thomas-estep/bindle", is_default=True)
        self.add_repo("mirror", "thomas-estep/bindle-mirror")
        self.write_map(self.base_map(decisions=(
            "### A decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: x\nso: y\nrevisit-when: z\nevidence: Issue #5\n" % self.slug
        )))
        preview = compiler.compile_preview(self.notes_home, self.slug, github_adapter=_stub_adapter())
        self.assertEqual(preview["conflicts"], [])
        issue_nodes = [n for n in preview["nodes"] if n["kind"] == "github_issue"]
        self.assertEqual(issue_nodes[0]["id"], "github-issue:thomas-estep/bindle#5")

    # 13. Multiple repositories without a default: bare references
    # unresolved.
    def test_bare_reference_unresolved_without_default(self):
        self.init()
        self.add_repo("primary", "thomas-estep/bindle")
        self.add_repo("mirror", "thomas-estep/bindle-mirror")
        self.write_map(self.base_map(decisions=(
            "### A decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: x\nso: y\nrevisit-when: z\nevidence: Issue #5\n" % self.slug
        )))
        preview = compiler.compile_preview(self.notes_home, self.slug, github_adapter=_stub_adapter())
        codes = [c["code"] for c in preview["conflicts"]]
        self.assertIn("unresolved-evidence-pointer", codes)


class DeterministicEdges(CompilerTestBase):
    def test_contains_supported_by_edges(self):
        self.init()
        self.write_map(self.base_map(decisions=(
            "### A decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: x\nso: y\nrevisit-when: z\nevidence: docs/x.md\n" % self.slug
        )))
        preview = compiler.compile_preview(self.notes_home, self.slug)
        rels = sorted(e["relationship"] for e in preview["edges"])
        self.assertEqual(rels, ["contains", "supported_by"])
        for e in preview["edges"]:
            self.assertEqual(e["origin"], "deterministic")

    # 10. Illegal deterministic edges cannot enter schema-valid preview
    # output while unrelated valid graph portions still compile.
    def test_cross_kind_supersedes_is_rejected_but_rest_compiles(self):
        self.init()
        replacement = "context-node:%s:11111111111111111111111111111111" % self.slug
        retired = "context-node:%s:22222222222222222222222222222222" % self.slug
        self.write_map(self.base_map(
            decisions=(
                "### Replacement decision (2026-07, settled) "
                "<!-- bindle:context-id: %s -->\n"
                "why: x\nso: y\nrevisit-when: z\nevidence:\n" % replacement
            ),
            superseded=(
                "- learning: Old learning (retired 2026-06) → cross-kind "
                "<!-- bindle:context-id: %s --> "
                "<!-- bindle:superseded-by: %s -->\n"
                "  why: old\n  so: old\n  evidence:\n" % (retired, replacement)
            ),
        ))
        preview = compiler.compile_preview(self.notes_home, self.slug)
        self.assertNotIn("supersedes", [e["relationship"] for e in preview["edges"]])
        codes = [c["code"] for c in preview["conflicts"]]
        self.assertIn("illegal-deterministic-edge", codes)
        # the unrelated replacement decision node still compiled
        self.assertTrue(any(n["id"] == replacement for n in preview["nodes"]))

    def test_same_kind_supersedes_succeeds(self):
        self.init()
        replacement = "context-node:%s:11111111111111111111111111111111" % self.slug
        retired = "context-node:%s:22222222222222222222222222222222" % self.slug
        self.write_map(self.base_map(
            decisions=(
                "### Replacement decision (2026-07, settled) "
                "<!-- bindle:context-id: %s -->\n"
                "why: x\nso: y\nrevisit-when: z\nevidence:\n" % replacement
            ),
            superseded=(
                "- decision: Old decision (retired 2026-06) → same-kind "
                "<!-- bindle:context-id: %s --> "
                "<!-- bindle:superseded-by: %s -->\n"
                "  why: old\n  so: old\n  revisit-when: old\n  evidence:\n"
                % (retired, replacement)
            ),
        ))
        preview = compiler.compile_preview(self.notes_home, self.slug)
        supersedes = [e for e in preview["edges"] if e["relationship"] == "supersedes"]
        self.assertEqual(len(supersedes), 1)
        self.assertEqual(supersedes[0]["source"], replacement)
        self.assertEqual(supersedes[0]["target"], retired)

    def test_tension_sides_deduplicate_shared_evidence_into_one_edge(self):
        self.init()
        self.write_map(self.base_map(assumptions=(
            "- Speed vs correctness — confidence: high "
            "<!-- bindle:context-id: context-node:%s:33333333333333333333333333333333 -->\n"
            "  - Speed matters — evidence: docs/shared.md\n"
            "  - Correctness matters — evidence: docs/shared.md\n" % self.slug
        )))
        preview = compiler.compile_preview(self.notes_home, self.slug)
        supported_by = [e for e in preview["edges"] if e["relationship"] == "supported_by"]
        self.assertEqual(len(supported_by), 1)
        self.assertEqual(len(supported_by[0]["basis"]), 1, "duplicate pointer must dedupe to one basis entry")


class GitHubClosesEdges(CompilerTestBase):
    def test_pr_closes_issue_edge(self):
        self.init()
        self.add_repo("primary", "thomas-estep/bindle", is_default=True)
        self.write_map(self.base_map(decisions=(
            "### A decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: x\nso: y\nrevisit-when: z\nevidence: PR #205\n" % self.slug
        )))

        def run(args, timeout):
            if args[0] == "pr" and "closingIssuesReferences" in args[-1]:
                return FakeProc(0, json.dumps({
                    "number": 205,
                    "closingIssuesReferences": [
                        {"number": 191, "repository": {"owner": {"login": "thomas-estep"}, "name": "bindle"}},
                    ],
                }))
            if args[0] == "pr":
                return FakeProc(0, json.dumps({
                    "number": 205, "title": "feat", "state": "MERGED", "url": "https://x",
                    "isDraft": False, "mergedAt": "2026-07-17T00:00:00Z",
                }))
            return FakeProc(0, json.dumps({
                "number": 191, "title": "init", "state": "CLOSED", "url": "https://x",
            }))

        adapter = github_adapter.GitHubAdapter(run=run)
        preview = compiler.compile_preview(self.notes_home, self.slug, github_adapter=adapter)
        closes = [e for e in preview["edges"] if e["relationship"] == "closes"]
        self.assertEqual(len(closes), 1)
        self.assertEqual(closes[0]["source"], "github-pr:thomas-estep/bindle#205")
        self.assertEqual(closes[0]["target"], "github-issue:thomas-estep/bindle#191")


class LedgerIndependence(CompilerTestBase):
    # 17. Deterministic edges bypass the ledger entirely.
    # 21. Deterministic preview succeeds with no ledger present.
    # 23. No judged edge appears in #183 output.
    def test_no_ledger_file_needed(self):
        self.init()
        self.write_map(self.base_map())
        ledger_path = os.path.join(
            self.notes_home, "projects", self.slug, ".bindle", "context", "judgments.jsonl"
        )
        self.assertFalse(os.path.exists(ledger_path))
        preview = compiler.compile_preview(self.notes_home, self.slug)
        self.assertFalse(os.path.exists(ledger_path), "compiler must never create the ledger")
        for e in preview["edges"]:
            self.assertEqual(e["origin"], "deterministic")

    # 22. Adding or editing a ledger does not change #183 deterministic
    # output.
    def test_ledger_presence_does_not_change_output(self):
        self.init()
        self.write_map(self.base_map(decisions=(
            "### A decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: x\nso: y\nrevisit-when: z\nevidence: docs/x.md\n" % self.slug
        )))
        baseline = compiler.compile_preview(self.notes_home, self.slug)

        ledger_dir = os.path.join(self.notes_home, "projects", self.slug, ".bindle", "context")
        os.makedirs(ledger_dir, exist_ok=True)
        with open(os.path.join(ledger_dir, "judgments.jsonl"), "w") as fh:
            fh.write(json.dumps({
                "schema_version": 1, "decision": "accepted",
                "subject_key": "some|relationship|thing", "subject_type": "edge",
                "candidate_key": "candidate:sha256:" + "0" * 64,
                "decided_at": "2026-07-17T00:00:00Z",
            }) + "\n")

        with_ledger = compiler.compile_preview(self.notes_home, self.slug)
        self.assertEqual(
            json.dumps(baseline, sort_keys=True), json.dumps(with_ledger, sort_keys=True)
        )


class AnchorCandidates(CompilerTestBase):
    # 18. Anchor candidates are stable across unchanged previews.
    def test_anchor_candidates_stable_across_runs(self):
        self.init()
        self.write_map(self.base_map(assumptions=(
            "- An unanchored assumption — confidence: low — evidence: docs/w.md\n"
        )))
        first = compiler.compile_preview(self.notes_home, self.slug)
        second = compiler.compile_preview(self.notes_home, self.slug)
        self.assertEqual(
            first["identity_anchor_candidates"], second["identity_anchor_candidates"]
        )
        self.assertEqual(len(first["identity_anchor_candidates"]), 1)

    # 19. Model-authored anchor candidates are not accepted as compiler
    # output (every emitted candidate is compiler-origin by construction).
    # 20. No semantic candidate appears without #184 processing an
    # external proposal.
    def test_every_candidate_is_deterministic_compiler_identity_anchor(self):
        self.init()
        self.write_map(self.base_map(assumptions=(
            "- An unanchored assumption — confidence: low — evidence: docs/w.md\n"
        )))
        preview = compiler.compile_preview(self.notes_home, self.slug)
        for c in preview["identity_anchor_candidates"]:
            self.assertEqual(c["subject_type"], "identity_anchor")
            self.assertEqual(c["candidate_origin"], "deterministic_compiler")


class RepoRootValidation(CompilerTestBase):
    def test_unknown_repo_root_alias_is_a_conflict(self):
        self.init()
        self.write_map(self.base_map())
        preview = compiler.compile_preview(
            self.notes_home, self.slug, repo_roots={"nope": "/tmp/x"}
        )
        codes = [c["code"] for c in preview["conflicts"]]
        self.assertIn("unknown-repo-root-alias", codes)

    def test_known_repo_root_alias_is_not_a_conflict(self):
        self.init()
        self.add_repo("primary", "thomas-estep/bindle")
        self.write_map(self.base_map())
        preview = compiler.compile_preview(
            self.notes_home, self.slug, repo_roots={"primary": "/tmp/x"}
        )
        codes = [c["code"] for c in preview["conflicts"]]
        self.assertNotIn("unknown-repo-root-alias", codes)


class MissingMap(CompilerTestBase):
    def test_missing_map_degrades_gracefully(self):
        self.init()
        preview = compiler.compile_preview(self.notes_home, self.slug)
        self.assertEqual(preview["nodes"], [{
            "id": self.project_id(), "class": "project", "kind": None,
            "label": self.slug, "status": "current",
        }])
        self.assertEqual(preview["coverage"]["project_map"], "unavailable")


class MapTextOverride(CompilerTestBase):
    # Task 7 (#185): compile_preview can compile an in-memory map string
    # instead of reading map.md from disk -- the seam apply's orchestrator
    # (design doc section 12 steps 4-5) uses to preview the planned map
    # bytes for the first-apply anchor, in the same run, without a write.
    def test_map_text_override_used_instead_of_disk(self):
        self.init()
        self.write_map(self.base_map(decisions=(
            "### On-disk decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:22222222222222222222222222222222 -->\n"
            "why: x\nso: y\n" % self.slug
        )))
        override = self.base_map(decisions=(
            "### Overridden decision (2026-07, settled) "
            "<!-- bindle:context-id: context-node:%s:11111111111111111111111111111111 -->\n"
            "why: x\nso: y\n" % self.slug
        ))
        preview = compiler.compile_preview(
            self.notes_home, self.slug, map_text_override=override
        )
        labels = [n["label"] for n in preview["nodes"]]
        self.assertIn("Overridden decision", labels)
        self.assertNotIn("On-disk decision", labels)
        self.assertEqual(preview["coverage"]["project_map"], "complete")


if __name__ == "__main__":
    unittest.main()
