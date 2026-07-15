#!/usr/bin/env python3
"""release-evidence.py — deterministic release-evidence collector for the
release-captain contract (docs/workflows/release-captain.md, Step 2).

Given a repo's latest release tag and version source, this gathers the merged
PRs (and their linked issues) since that release — plus, as a fallback, the
commits since the tag — and STRUCTURES them in the contract's evidence-
precedence order:

  1. explicit release labels/metadata on merged PRs
  2. breaking-change metadata
  3. Conventional-Commit-compatible squash PR titles
  4. commits since the latest tag (only when PR evidence is unavailable)
  5. diff inspection — supporting only; never auto-classified here

It emits the structured evidence as machine-readable JSON and a human-readable
summary. It is deliberately the *collection* layer: it classifies each change
ONLY where a deterministic signal exists (a release label, breaking metadata,
or a recognized Conventional-Commit type) and marks everything else
`uncertain`. **It never decides the final version or release timing** — that is
model/maintainer judgment (L3 of #116), which sits on top of this data.

Fail-safe by construction (mirrors bin/issue-dedup-scan.sh and the contract's
Section 2 invariant):
  - if a collection sub-query FAILS (git/gh error), the verdict is `uncertain`
    and no deterministic aggregate class is asserted — a failed query is never
    laundered into "no releasable change";
  - where an explicit maintainer label CONTRADICTS the inferred class, the
    change is flagged `uncertain` with the conflict recorded, rather than
    silently overriding either side;
  - no version number or timing recommendation is ever emitted.

Stdlib-only. No mutation: it never merges, tags, publishes, deploys, creates a
GitHub Release, or writes to the repo (except an explicit --emit target).

Usage:
  bin/release-evidence.py [--root DIR] [--format json|text|both] [--emit PATH]
      Live mode: read VERSION, detect the latest tag, query merged PRs via gh.
  bin/release-evidence.py --fixture PATH [--format ...] [--emit ...]
      Dry-run mode: load pre-recorded raw evidence JSON, skip all git/gh calls.
      This is the deterministic, offline path the fixtures exercise.

Exit codes:
  0  evidence collected (verdict "ok"); the set may still contain `uncertain`
     changes for a downstream judge — that is honest data, not an error.
  0  is also returned for a clean `uncertain` verdict written to output; the
     verdict lives in the JSON `verdict` field, not the process exit code, so a
     caller always gets the structured evidence. Use --strict to make a
     collection-failure `uncertain` verdict exit nonzero instead.
  1  bad input (unreadable/invalid --fixture, unwritable --emit), or --strict
     with an `uncertain` verdict.
  64 usage error.
"""
import argparse
import json
import os
import re
import subprocess
import sys

SCHEMA = "release-evidence/v1"

# Conventional-Commit type -> deterministic version class. Types absent here
# (e.g. an unknown or missing prefix) yield no inference -> `uncertain`; the
# helper never guesses. `refactor`/`style` are treated as non-user-facing
# (`none`); `revert` is intentionally omitted (its effect depends on what was
# reverted) so it falls through to `uncertain`.
CONVENTIONAL = {
    "feat": "minor",
    "fix": "patch",
    "perf": "patch",
    "docs": "none",
    "test": "none",
    "tests": "none",
    "ci": "none",
    "build": "none",
    "chore": "none",
    "style": "none",
    "refactor": "none",
}

# Deterministic classes ordered by release significance. `uncertain` is NOT in
# this list — it is never treated as a concrete class or rolled into "highest".
CLASS_ORDER = ["none", "patch", "minor", "breaking"]

# Which evidence-precedence rank (contract Step 2) a classification basis rests
# on. Lower = stronger. `commits-since-tag` (4) applies to commit-sourced
# changes; diff (5) is never auto-classified.
PRECEDENCE = {
    "release-label": 1,
    "breaking-metadata": 2,
    "conventional-title": 3,
    "commits-since-tag": 4,
    None: 5,
}

_LABEL_RE = re.compile(r"^release:\s*(none|patch|minor|breaking)$")
_CONV_RE = re.compile(r"^\s*([a-zA-Z]+)(\([^)]*\))?(!)?:\s")
_BREAKING_RE = re.compile(r"BREAKING[ -]CHANGE")
_ISSUE_REF_RE = re.compile(r"#(\d+)")


def _label_class(labels):
    """The class named by an explicit `release: <class>` label, or None."""
    for lb in labels or []:
        norm = str(lb).strip().lower().replace("release-", "release: ")
        m = _LABEL_RE.match(norm)
        if m:
            return m.group(1)
    return None


def _conventional_class(title):
    """(base_class_or_None, is_breaking) parsed from a Conventional-Commit
    title. base_class is None for an unrecognized/missing type."""
    m = _CONV_RE.match(title or "")
    if not m:
        return None, False
    typ = m.group(1).lower()
    breaking = bool(m.group(3))
    return CONVENTIONAL.get(typ), breaking


def classify_change(item):
    """Deterministically classify one change from explicit signals only.

    Returns a dict: {class, basis, precedence, rationale, contradiction}.
    `class` is one of CLASS_ORDER or "uncertain". A change with no explicit
    label, no breaking metadata, and no recognized Conventional-Commit type is
    `uncertain` — never guessed. An explicit label that disagrees with the
    inferred class is flagged as a contradiction and the change is `uncertain`,
    not silently overridden (contract Step 3)."""
    labels = item.get("labels") or []
    title = item.get("title") or ""
    body = item.get("body") or ""
    source = item.get("source") or "merged-pr"

    label_cls = _label_class(labels)
    conv_cls, title_breaking = _conventional_class(title)
    breaking = title_breaking or bool(_BREAKING_RE.search(body)) or \
        bool(item.get("breaking"))

    if breaking:
        inferred, inferred_basis = "breaking", "breaking-metadata"
    elif conv_cls is not None:
        inferred, inferred_basis = conv_cls, "conventional-title"
    else:
        inferred, inferred_basis = None, None

    # For a commit-sourced change, the precedence rank is "commits-since-tag"
    # (4) regardless of how it happened to classify — PR evidence outranks it.
    def _rank(basis):
        if source == "commit" and basis in ("conventional-title",
                                            "breaking-metadata"):
            return PRECEDENCE["commits-since-tag"]
        return PRECEDENCE[basis]

    if label_cls is not None:
        if inferred is not None and inferred != label_cls:
            return {
                "class": "uncertain",
                "basis": "release-label",
                "precedence": PRECEDENCE["release-label"],
                "rationale": ("explicit label 'release: %s' conflicts with "
                              "inferred '%s' (%s) — flagged, not overridden"
                              % (label_cls, inferred, inferred_basis)),
                "contradiction": True,
            }
        return {
            "class": label_cls,
            "basis": "release-label",
            "precedence": PRECEDENCE["release-label"],
            "rationale": "explicit maintainer label 'release: %s'" % label_cls,
            "contradiction": False,
        }

    if inferred is not None:
        return {
            "class": inferred,
            "basis": inferred_basis,
            "precedence": _rank(inferred_basis),
            "rationale": "inferred from %s" % inferred_basis,
            "contradiction": False,
        }

    return {
        "class": "uncertain",
        "basis": None,
        "precedence": PRECEDENCE[None],
        "rationale": ("no explicit label, breaking metadata, or recognized "
                      "Conventional-Commit type — needs judgment"),
        "contradiction": False,
    }


def _linked_issues(item):
    """Explicit linked_issues if present, else #-refs parsed from title+body."""
    if item.get("linked_issues"):
        return ["#%s" % str(n).lstrip("#") for n in item["linked_issues"]]
    text = "%s %s" % (item.get("title") or "", item.get("body") or "")
    seen, out = set(), []
    for m in _ISSUE_REF_RE.finditer(text):
        ref = "#" + m.group(1)
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return out


def structure_evidence(raw):
    """Turn raw collected evidence into the structured, precedence-ordered
    result. Pure: no git/gh/network. `raw` carries current_version, latest_tag,
    a collection block ({ok, queries}), and a list of change items."""
    collection = raw.get("collection") or {}
    collection_ok = bool(collection.get("ok", True))

    changes = []
    for item in raw.get("changes") or []:
        verdict = classify_change(item)
        changes.append({
            "ref": item.get("ref"),
            "evidence_source": item.get("source") or "merged-pr",
            "title": item.get("title"),
            "linked_issues": _linked_issues(item),
            "class": verdict["class"],
            "classification_basis": verdict["basis"],
            "precedence": verdict["precedence"],
            "rationale": verdict["rationale"],
            "contradiction": verdict["contradiction"],
        })
    # Stable order: strongest evidence first, then by ref for determinism.
    changes.sort(key=lambda c: (c["precedence"], str(c["ref"])))

    counts = {cls: 0 for cls in CLASS_ORDER}
    counts["uncertain"] = 0
    contradictions = 0
    highest = None
    for c in changes:
        cls = c["class"]
        counts[cls] = counts.get(cls, 0) + 1
        if c["contradiction"]:
            contradictions += 1
        if cls in CLASS_ORDER:
            if highest is None or CLASS_ORDER.index(cls) > CLASS_ORDER.index(highest):
                highest = cls

    # Verdict reflects whether COLLECTION succeeded — never a version/timing
    # call. A failed sub-query blocks a trustworthy set (Section 2 invariant).
    verdict = "ok" if collection_ok else "uncertain"

    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "current_version": raw.get("current_version"),
        "latest_tag": raw.get("latest_tag"),
        "collection": {
            "ok": collection_ok,
            "queries": collection.get("queries") or [],
        },
        "changes": changes,
        "aggregate": {
            "highest_deterministic_class": highest if collection_ok else None,
            "counts": counts,
            "uncertain": counts.get("uncertain", 0),
            "contradictions": contradictions,
        },
        "authority": ("evidence only — no version or timing decided; no merge, "
                      "tag, publish, release, or deploy performed"),
    }


def render_text(result):
    """Human-readable summary of a structured result."""
    lines = []
    lines.append("Release evidence (%s)" % result["schema"])
    lines.append("Current version: %s   Latest tag: %s"
                 % (result.get("current_version") or "?",
                    result.get("latest_tag") or "(none)"))
    col = result["collection"]
    if col["ok"]:
        lines.append("Collection: ok")
    else:
        failed = [q.get("name") for q in col["queries"]
                  if q.get("status") == "failed"]
        lines.append("Collection: FAILED (%s)" % (", ".join(failed) or "unknown"))
    lines.append("Changes since tag: %d" % len(result["changes"]))
    for c in result["changes"]:
        basis = c["classification_basis"] or "no deterministic signal"
        flag = "  [CONTRADICTION]" if c["contradiction"] else ""
        lines.append("  [%s] %s %s (%s)%s"
                     % (c["class"], c.get("ref") or "?",
                        c.get("title") or "", basis, flag))
    agg = result["aggregate"]
    lines.append("Aggregate: highest deterministic class = %s; uncertain = %d; "
                 "contradictions = %d"
                 % (agg["highest_deterministic_class"] or "none",
                    agg["uncertain"], agg["contradictions"]))
    if result["verdict"] == "uncertain":
        lines.append("Verdict: UNCERTAIN — evidence gathering was incomplete "
                     "or contradictory; no version or timing can be supported.")
    if agg["uncertain"]:
        lines.append("Note: %d change(s) need human/model judgment; this helper "
                     "does not guess them." % agg["uncertain"])
    lines.append("Authority: %s." % result["authority"])
    return "\n".join(lines)


# --- live collection (best-effort; the fixture path is the tested contract) --

def _git(root, *args):
    out = subprocess.run(["git", "-C", root, *args],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _read_version(root):
    path = os.path.join(root, "VERSION")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def collect_live(root, gh="gh"):
    """Gather raw evidence from the real repo. Any sub-query error is recorded
    as a failed query so the verdict degrades to `uncertain` rather than
    silently reporting an empty (falsely clean) set."""
    queries = []
    ok = True

    def record(name, status):
        nonlocal ok
        queries.append({"name": name, "status": status})
        if status == "failed":
            ok = False

    current_version = _read_version(root)

    latest_tag = None
    tag_date = None
    try:
        latest_tag = _git(root, "describe", "--tags", "--abbrev=0") or None
        record("git-tag", "ok")
    except (OSError, subprocess.CalledProcessError):
        # No tag is a legitimate "since repo start", not a failure; only a git
        # invocation error is a failed query.
        if _git_available(root):
            latest_tag = None
            record("git-tag", "ok")
        else:
            record("git-tag", "failed")

    if latest_tag:
        try:
            tag_date = _git(root, "log", "-1", "--format=%cI", latest_tag)
        except (OSError, subprocess.CalledProcessError):
            record("git-tag-date", "failed")

    changes = []
    prs_ok = False
    try:
        search = "merged"
        if tag_date:
            search = "merged:>=%s" % tag_date
        out = subprocess.run(
            [gh, "pr", "list", "--state", "merged", "--search", search,
             "--json", "number,title,labels,body", "--limit", "200"],
            capture_output=True, text=True, check=True)
        data = json.loads(out.stdout or "[]")
        for pr in data:
            changes.append({
                "source": "merged-pr",
                "ref": "#%s" % pr.get("number"),
                "title": pr.get("title"),
                "body": pr.get("body") or "",
                "labels": [lb.get("name") for lb in pr.get("labels") or []],
            })
        prs_ok = True
        record("gh-pr-merged", "ok")
    except (OSError, subprocess.CalledProcessError, ValueError):
        record("gh-pr-merged", "failed")

    # Commits-since-tag fallback (rank 4) only when PR evidence is unavailable.
    if prs_ok and not changes and latest_tag:
        try:
            rng = "%s..HEAD" % latest_tag
            out = _git(root, "log", rng, "--format=%H%x1f%s")
            for line in out.splitlines():
                if not line:
                    continue
                sha, _, subject = line.partition("\x1f")
                changes.append({
                    "source": "commit",
                    "ref": sha[:12],
                    "title": subject,
                    "body": "",
                    "labels": [],
                })
            record("git-log-commits", "ok")
        except (OSError, subprocess.CalledProcessError):
            record("git-log-commits", "failed")

    return {
        "current_version": current_version,
        "latest_tag": latest_tag,
        "collection": {"ok": ok, "queries": queries},
        "changes": changes,
    }


def _git_available(root):
    try:
        subprocess.run(["git", "-C", root, "rev-parse", "--git-dir"],
                       capture_output=True, text=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _load_fixture(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None,
                        help="repo root (default: this script's repo)")
    parser.add_argument("--fixture", default=None, metavar="PATH",
                        help="load pre-recorded raw evidence JSON; skip all "
                             "git/gh calls (offline dry-run)")
    parser.add_argument("--format", choices=["json", "text", "both"],
                        default="both")
    parser.add_argument("--emit", default=None, metavar="PATH",
                        help="write output to PATH ('-' = stdout, the default)")
    parser.add_argument("--strict", action="store_true",
                        help="exit nonzero when the verdict is `uncertain`")
    args = parser.parse_args(argv)

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if args.fixture is not None:
        try:
            raw = _load_fixture(args.fixture)
        except (OSError, ValueError) as exc:
            print("release-evidence: cannot read fixture: %s" % exc,
                  file=sys.stderr)
            return 1
    else:
        raw = collect_live(root)

    result = structure_evidence(raw)

    parts = []
    if args.format in ("json", "both"):
        parts.append(json.dumps(result, indent=2))
    if args.format in ("text", "both"):
        parts.append(render_text(result))
    text = "\n".join(parts) + "\n"

    if args.emit in (None, "-"):
        sys.stdout.write(text)
    else:
        try:
            with open(args.emit, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print("release-evidence: cannot write --emit target: %s" % exc,
                  file=sys.stderr)
            return 1

    if args.strict and result["verdict"] == "uncertain":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
