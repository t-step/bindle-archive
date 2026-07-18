"""Tests for context_graph.github_adapter — the #183 read-only GitHub
resolver. No fixture makes a real network call; every test substitutes a
stub `run` callable."""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from context_graph import github_adapter


class FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stub(responses):
    """responses: list of (returncode, stdout, stderr) consumed in call
    order, or a single tuple reused for every call."""
    calls = []

    def run(args, timeout):
        calls.append(args)
        if isinstance(responses, list):
            rc, out, err = responses[len(calls) - 1]
        else:
            rc, out, err = responses
        return FakeProc(rc, out, err)

    run.calls = calls
    return run


class FetchIssue(unittest.TestCase):
    def test_ok(self):
        run = _stub((0, json.dumps({
            "number": 140, "title": "Epic", "state": "OPEN", "url": "https://x",
        }), ""))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_issue("thomas-estep", "bindle", 140)
        self.assertEqual(result, {
            "status": "ok", "number": 140, "title": "Epic", "state": "OPEN",
            "url": "https://x",
        })

    def test_missing(self):
        run = _stub((1, "", "GraphQL: Could not resolve to an Issue with the number of 9."))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_issue("thomas-estep", "bindle", 9)
        self.assertEqual(result, {"status": "missing"})

    def test_timeout(self):
        def run(args, timeout):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=timeout)
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_issue("thomas-estep", "bindle", 1)
        self.assertEqual(result, {"status": "unavailable", "reason": "timeout"})

    def test_gh_not_available(self):
        def run(args, timeout):
            raise OSError("no such file or directory: gh")
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_issue("thomas-estep", "bindle", 1)
        self.assertEqual(result, {"status": "unavailable", "reason": "gh_not_available"})

    def test_malformed_response(self):
        run = _stub((0, "not json", ""))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_issue("thomas-estep", "bindle", 1)
        self.assertEqual(result, {"status": "unavailable", "reason": "malformed_response"})

    def test_authentication_failure(self):
        run = _stub((1, "", "To get started with GitHub CLI, please run: gh auth login"))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_issue("thomas-estep", "bindle", 1)
        self.assertEqual(result, {"status": "unavailable", "reason": "authentication_failed"})


class RateLimit(unittest.TestCase):
    def test_stops_further_calls_for_the_run(self):
        run = _stub((1, "", "API rate limit exceeded for installation ID 1."))
        adapter = github_adapter.GitHubAdapter(run=run)
        first = adapter.fetch_issue("thomas-estep", "bindle", 1)
        self.assertEqual(first, {"status": "unavailable", "reason": "rate_limited"})
        self.assertTrue(adapter.rate_limited)
        second = adapter.fetch_pr("thomas-estep", "bindle", 2)
        self.assertEqual(second, {"status": "unavailable", "reason": "rate_limited"})
        self.assertEqual(len(run.calls), 1, "must not make a second gh call once rate-limited")


class FetchPr(unittest.TestCase):
    def test_ok_merged(self):
        run = _stub((0, json.dumps({
            "number": 205, "title": "feat", "state": "MERGED", "url": "https://x",
            "isDraft": False, "mergedAt": "2026-07-17T00:00:00Z",
        }), ""))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_pr("thomas-estep", "bindle", 205)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["merged"])
        self.assertFalse(result["draft"])

    def test_ok_open_draft(self):
        run = _stub((0, json.dumps({
            "number": 1, "title": "wip", "state": "OPEN", "url": "https://x",
            "isDraft": True, "mergedAt": None,
        }), ""))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_pr("thomas-estep", "bindle", 1)
        self.assertFalse(result["merged"])
        self.assertTrue(result["draft"])


class FetchPrCloses(unittest.TestCase):
    def test_closes_same_repo_only(self):
        run = _stub((0, json.dumps({
            "number": 205,
            "closingIssuesReferences": [
                {"number": 191, "repository": {"owner": {"login": "thomas-estep"}, "name": "bindle"}},
                {"number": 7, "repository": {"owner": {"login": "someone-else"}, "name": "other-repo"}},
            ],
        }), ""))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_pr_closes("thomas-estep", "bindle", 205)
        self.assertEqual(result, {"status": "ok", "closes": [191]})

    def test_no_closing_references(self):
        run = _stub((0, json.dumps({"number": 1, "closingIssuesReferences": []}), ""))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_pr_closes("thomas-estep", "bindle", 1)
        self.assertEqual(result, {"status": "ok", "closes": []})

    def test_propagates_failure(self):
        run = _stub((1, "", "some gh failure"))
        adapter = github_adapter.GitHubAdapter(run=run)
        result = adapter.fetch_pr_closes("thomas-estep", "bindle", 1)
        self.assertEqual(result["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
