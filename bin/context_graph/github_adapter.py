"""context_graph.github_adapter — thin, read-only GitHub issue/PR resolution
for the #183 deterministic compiler (epic #140).

Owned entirely by #183 (design doc section 9): #184 has no role in GitHub
access or `closes`-edge extraction. Every read goes through exactly three
narrow functions -- `fetch_issue`, `fetch_pr`, `fetch_pr_closes` -- so
fixtures and pressure tests substitute a stub; no fixture makes a real
network call.

Every result is one of three states, never an exception for an ordinary
runtime condition:

  {"status": "ok", ...}
  {"status": "missing", ...}        -- the API confirms no such artifact
  {"status": "unavailable", "reason": <code>, ...}  -- network/auth/timeout/
                                                        rate-limit

`unavailable` and `missing` are never conflated: a transient outage is
uncertainty, a confirmed-absent artifact is real information. No mutation is
ever performed here.
"""
import json
import subprocess

DEFAULT_TIMEOUT_SECONDS = 10


def _run_gh(args, timeout):
    return subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class GitHubAdapter:
    """`run` is an injectable `(args, timeout) -> CompletedProcess`-shaped
    callable, substituted by tests/fixtures. Once a call observes a rate
    limit, every subsequent call this instance makes short-circuits to
    `unavailable`/`reason: rate_limited` without another subprocess call --
    "on a rate-limit response, the adapter stops further GitHub calls for
    the remainder of that run" (design section 9)."""

    def __init__(self, run=None, timeout=DEFAULT_TIMEOUT_SECONDS):
        self._run = run or _run_gh
        self._timeout = timeout
        self._rate_limited = False

    @property
    def rate_limited(self):
        return self._rate_limited

    def _classify_failure(self, returncode, stderr):
        lowered = (stderr or "").lower()
        if "rate limit" in lowered:
            self._rate_limited = True
            return {"status": "unavailable", "reason": "rate_limited"}
        if "could not resolve" in lowered or "not found" in lowered or "404" in lowered:
            return {"status": "missing"}
        if "authentication" in lowered or "gh auth login" in lowered:
            return {"status": "unavailable", "reason": "authentication_failed"}
        return {"status": "unavailable", "reason": "gh_command_failed"}

    def _fetch(self, kind, owner, repo, number, fields):
        if self._rate_limited:
            return {"status": "unavailable", "reason": "rate_limited"}
        repo_slug = "%s/%s" % (owner, repo)
        args = [kind, "view", str(number), "--repo", repo_slug,
                "--json", ",".join(fields)]
        try:
            proc = self._run(args, self._timeout)
        except subprocess.TimeoutExpired:
            return {"status": "unavailable", "reason": "timeout"}
        except OSError:
            return {"status": "unavailable", "reason": "gh_not_available"}
        if proc.returncode != 0:
            return self._classify_failure(proc.returncode, proc.stderr)
        try:
            return {"status": "ok", "data": json.loads(proc.stdout)}
        except ValueError:
            return {"status": "unavailable", "reason": "malformed_response"}

    def fetch_issue(self, owner, repo, number):
        """{"status": "ok", "number", "title", "state", "url"} or a
        missing/unavailable envelope."""
        result = self._fetch(
            "issue", owner, repo, number, ["number", "title", "state", "url"]
        )
        if result["status"] != "ok":
            return result
        data = result["data"]
        return {
            "status": "ok",
            "number": data.get("number", number),
            "title": data.get("title"),
            "state": data.get("state"),
            "url": data.get("url"),
        }

    def fetch_pr(self, owner, repo, number):
        """{"status": "ok", "number", "title", "state", "url", "draft",
        "merged"} or a missing/unavailable envelope."""
        result = self._fetch(
            "pr", owner, repo, number,
            ["number", "title", "state", "url", "isDraft", "mergedAt"],
        )
        if result["status"] != "ok":
            return result
        data = result["data"]
        return {
            "status": "ok",
            "number": data.get("number", number),
            "title": data.get("title"),
            "state": data.get("state"),
            "url": data.get("url"),
            "draft": bool(data.get("isDraft")),
            "merged": data.get("mergedAt") is not None,
        }

    def fetch_pr_closes(self, owner, repo, number):
        """{"status": "ok", "closes": [<issue number>, ...]} -- the closing
        issue numbers GitHub itself reports for this PR, from its own
        closing-reference data -- never inferred from title/body text
        similarity. A closing reference in a different repository is
        excluded: `closes` is deterministic only within the PR's own
        configured repository (design section 9 / issue body "Explicit
        closure-edge extraction")."""
        result = self._fetch(
            "pr", owner, repo, number, ["number", "closingIssuesReferences"]
        )
        if result["status"] != "ok":
            return result
        data = result["data"]
        refs = data.get("closingIssuesReferences") or []
        closes = []
        for ref in refs:
            ref_repo = ref.get("repository") or {}
            ref_owner = (ref_repo.get("owner") or {}).get("login")
            ref_name = ref_repo.get("name")
            if ref_owner is None or ref_name is None or (
                ref_owner == owner and ref_name == repo
            ):
                num = ref.get("number")
                if isinstance(num, int):
                    closes.append(num)
        return {"status": "ok", "closes": sorted(set(closes))}
