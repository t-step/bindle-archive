# Portable Package Release-Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a clean-room, defer-aware portable package release-integrity workflow (issue #59) — a provider-neutral contract doc, a Claude-native skill, and a stdlib-Python deterministic helper — that mechanically validates a Python package release and defers to DomI where DomI owns release governance.

**Architecture:** A single stdlib-Python helper (`skills/package-release-integrity/scripts/release_integrity.py`) exposes a `check` verb that runs mechanical checks (version-source consistency, tag==version, changelog presence, semver movement given a declared change class) and returns per-check verdicts `pass`/`fail`/`uncertain`. Change classification and track routing are never guessed — they return `uncertain` unless the caller declares them. Before running, the skill detects DomI release authority (reusing the `domi-consumer` skill) and defers when DomI owns the policy. A pure-logic `selftest.py` is auto-run by `bin/check.sh`; a fixture suite `bin/test-package-release-integrity.sh` drives the CLI over 7 synthetic package layouts.

**Tech Stack:** Python 3.11+ (stdlib only: `tomllib`, `re`, `subprocess`, `argparse`, `json`, `pathlib`), Bash (test harness), Markdown (contract doc + skill).

## Global Constraints

- **Stdlib only.** No third-party Python deps (no `packaging`). `tomllib` is 3.11+.
- **Clean-room.** No code or prose copied from DomI's `release-integrity` skill. Structural similarity is convergent, not vendored.
- **Never guess judgment.** Change classification (#1) and track routing (#8) return `uncertain` unless the caller supplies `--change-class`. The helper never infers a breaking change.
- **`uncertain` never fails the run.** Exit code is non-zero only on a `fail`. `uncertain` is a "human must decide" signal.
- **No mutation, no publish authority.** The helper never bumps a version, writes a tag, or publishes. A green check is not authorization to publish.
- **Degraded, never false-positive.** A tool/network failure yields `uncertain` or a degraded report, never a false `pass`/`ready`.
- **Triple-touch registration** (or `make check` fails): every new skill needs a `capabilities.json` row, a `docs/skill-portability-audit.md` matrix row, and (for a new doc) a `type:"contract"` row. Every new `docs/**/*.md` and `bin/*.sh` needs an inventory row or a `not_a_capability` entry.
- **New files staged before trusting `make check`** — `make check` scans `git ls-files`; pre-commit scans staged content.
- **Skill stays a CHANGELOG draft** until pressure-tested per superpowers:writing-skills.
- **Branch discipline:** all work on `feature/package-release-integrity-59`; `make check` green before every commit; never commit to `main`, never `--no-verify`, never push.

---

### Task 1: Helper core — semver + version-movement pure logic

The foundational pure functions, unit-tested via `selftest.py` (auto-run by `bin/check.sh`). No fixtures needed. Scaffolds the skill dir via `bin/new.sh`.

**Files:**
- Create: `skills/package-release-integrity/scripts/release_integrity.py`
- Create: `skills/package-release-integrity/scripts/selftest.py`
- Modify (auto): `skills/package-release-integrity/SKILL.md` (scaffolded by `bin/new.sh`; rewritten in Task 8), `capabilities.json` (draft skill row appended by `bin/new.sh`)

**Interfaces:**
- Produces: `parse_version(s: str) -> tuple[int,int,int] | None`; `is_pre_1_0(ver: tuple) -> bool`; `bump_type(old: tuple, new: tuple) -> str | None` (returns `"major"|"minor"|"patch"|None`); `required_movement(change_class: str, pre_1_0: bool) -> str | None`.

- [ ] **Step 1: Scaffold the skill directory**

Run:
```bash
bin/new.sh skill package-release-integrity
```
Expected: creates `skills/package-release-integrity/SKILL.md`, appends a draft skill row to `capabilities.json`, runs `check-inventory`. (SKILL.md body is rewritten in Task 8; leave it for now.)

- [ ] **Step 2: Write the failing pure-logic selftest**

Create `skills/package-release-integrity/scripts/selftest.py`:
```python
#!/usr/bin/env python3
"""Pure-logic self-test for release_integrity.py. Auto-run by bin/check.sh.
Exits non-zero on any failure; prints a one-line tally."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_integrity as ri

_fail = 0


def check(desc, got, want):
    global _fail
    if got == want:
        print(f"  ok: {desc}")
    else:
        _fail += 1
        print(f"  FAIL: {desc} -> got {got!r}, want {want!r}")


# parse_version
check("parse valid", ri.parse_version("1.2.3"), (1, 2, 3))
check("parse strips ws", ri.parse_version("  0.3.0 "), (0, 3, 0))
check("parse rejects non-semver", ri.parse_version("1.2"), None)
check("parse rejects suffix", ri.parse_version("1.2.3rc1"), None)

# is_pre_1_0
check("pre-1.0 true", ri.is_pre_1_0((0, 4, 0)), True)
check("pre-1.0 false", ri.is_pre_1_0((1, 0, 0)), False)

# bump_type
check("bump major", ri.bump_type((1, 2, 3), (2, 0, 0)), "major")
check("bump minor", ri.bump_type((1, 2, 3), (1, 3, 0)), "minor")
check("bump patch", ri.bump_type((1, 2, 3), (1, 2, 4)), "patch")
check("bump none (equal)", ri.bump_type((1, 2, 3), (1, 2, 3)), None)
check("bump none (decrease)", ri.bump_type((1, 2, 3), (1, 2, 2)), None)

# required_movement — post-1.0
check("post breaking->major", ri.required_movement("breaking", False), "major")
check("post additive->minor", ri.required_movement("additive", False), "minor")
check("post patch->patch", ri.required_movement("patch", False), "patch")
# required_movement — pre-1.0 (0.x: breaking bumps minor, additive/fix bump patch)
check("pre breaking->minor", ri.required_movement("breaking", True), "minor")
check("pre additive->patch", ri.required_movement("additive", True), "patch")
check("pre patch->patch", ri.required_movement("patch", True), "patch")
# data-only never moves the package version
check("data-only->none post", ri.required_movement("data-only", False), None)
check("data-only->none pre", ri.required_movement("data-only", True), None)

print(f"selftest: {'PASS' if _fail == 0 else 'FAIL'} ({_fail} failing)")
sys.exit(1 if _fail else 0)
```

- [ ] **Step 3: Run the selftest to verify it fails**

Run: `python3 skills/package-release-integrity/scripts/selftest.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'release_integrity'` (module not created yet).

- [ ] **Step 4: Write the minimal helper with the pure functions**

Create `skills/package-release-integrity/scripts/release_integrity.py`:
```python
#!/usr/bin/env python3
"""Portable package release-integrity checker (issue #59).

Deterministic, mechanical checks for a Python package release. Judgment checks
(change classification, track routing) return 'uncertain' — never guessed.
Stdlib only. Never mutates; a green check is not authorization to publish.
"""
import re

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# change class -> required bump component, split by pre/post 1.0.
# Pre-1.0 (0.x): a breaking change bumps the MINOR; additive/fix bump PATCH.
# Post-1.0: standard semver.
_MOVEMENT = {
    False: {"breaking": "major", "additive": "minor", "patch": "patch"},
    True: {"breaking": "minor", "additive": "patch", "patch": "patch"},
}


def parse_version(s):
    """Parse an exact MAJOR.MINOR.PATCH string. Returns a tuple or None."""
    if s is None:
        return None
    m = SEMVER_RE.match(s.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def is_pre_1_0(ver):
    """True when the version is in the 0.x unstable series."""
    return ver[0] == 0


def bump_type(old, new):
    """Which single component increased old->new. None if no clean increase."""
    if new[0] > old[0]:
        return "major"
    if new[0] == old[0] and new[1] > old[1]:
        return "minor"
    if new[0] == old[0] and new[1] == old[1] and new[2] > old[2]:
        return "patch"
    return None


def required_movement(change_class, pre_1_0):
    """Required bump component for a change class. data-only -> None (no move)."""
    if change_class == "data-only":
        return None
    return _MOVEMENT[bool(pre_1_0)].get(change_class)
```

- [ ] **Step 5: Run the selftest to verify it passes**

Run: `python3 skills/package-release-integrity/scripts/selftest.py`
Expected: PASS — `selftest: PASS (0 failing)`.

- [ ] **Step 6: Confirm the gate discovers and runs the selftest**

Run: `make check 2>&1 | grep -A1 package-release-integrity`
Expected: `bin/check.sh` auto-discovers `skills/package-release-integrity/scripts/selftest.py` and reports it passing.

- [ ] **Step 7: Commit**

```bash
git add skills/package-release-integrity/ capabilities.json
git commit -m "feat(#59): release-integrity helper core — semver + version-movement logic"
```

---

### Task 2: Version-source discovery + consistency check (#3), CLI `check` verb, test harness

Discovers the package version from `pyproject.toml` (and an optional module `__version__`) and checks all sources agree. Introduces the `check` CLI verb and the fixture-driven Bash test harness (wired into `make check`'s `test:` list and pre-commit).

**Files:**
- Modify: `skills/package-release-integrity/scripts/release_integrity.py`
- Create: `skills/package-release-integrity/tests/fixtures/consistent/pyproject.toml`
- Create: `skills/package-release-integrity/tests/fixtures/inconsistent/pyproject.toml`
- Create: `skills/package-release-integrity/tests/fixtures/inconsistent/pkg/__init__.py`
- Create: `bin/test-package-release-integrity.sh`
- Modify: `Makefile` (add script to `test:` list)
- Modify: `.pre-commit-config.yaml` (add hook)

**Interfaces:**
- Consumes: `parse_version` (Task 1).
- Produces: `discover_version_sources(repo: Path) -> dict[str, str]` (maps a source label like `"pyproject:[project].version"` or `"module:pkg/__init__.py"` to a raw version string); `check_version_source_consistency(sources: dict) -> dict` (a verdict record `{"check": "version_source_consistency", "verdict": "pass|fail|uncertain", "detail": str}`); `run_check(repo: Path, args) -> dict` (top-level report `{"verdicts": [...], "ready": bool}`); a `main()` argparse entrypoint with a `check` verb and `--repo`, `--json` flags.

- [ ] **Step 1: Write the failing harness with the consistency assertions**

Create `skills/package-release-integrity/tests/fixtures/consistent/pyproject.toml`:
```toml
[project]
name = "consistent-pkg"
version = "1.2.0"
```

Create `skills/package-release-integrity/tests/fixtures/inconsistent/pyproject.toml`:
```toml
[project]
name = "inconsistent-pkg"
version = "1.2.0"
```

Create `skills/package-release-integrity/tests/fixtures/inconsistent/pkg/__init__.py`:
```python
__version__ = "1.1.0"
```

Create `bin/test-package-release-integrity.sh`:
```bash
#!/usr/bin/env bash
# Fixture-driven tests for the release-integrity helper (issue #59).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$REPO_ROOT/skills/package-release-integrity/scripts/release_integrity.py"
FIX="$REPO_ROOT/skills/package-release-integrity/tests/fixtures"
pass=0
fail=0

# check <desc> <expected-exit> <cmd...>: run cmd, compare exit code.
run() { OUT="$("$@" 2>&1)"; RC=$?; }
contains() { echo "$OUT" | grep -qF "$1"; }

expect_contains() {
  local desc="$1" needle="$2"
  if contains "$needle"; then echo "  ok: $desc"; pass=$((pass+1));
  else echo "  FAIL: $desc (missing: $needle)"; echo "$OUT" | sed 's/^/    | /'; fail=$((fail+1)); fi
}
expect_rc() {
  local desc="$1" want="$2"
  if [ "$RC" -eq "$want" ]; then echo "  ok: $desc"; pass=$((pass+1));
  else echo "  FAIL: $desc (rc=$RC want=$want)"; fail=$((fail+1)); fi
}

echo "version-source consistency:"
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "consistent -> pass" "version_source_consistency: pass"
run python3 "$HELPER" check --repo "$FIX/inconsistent"
expect_contains "inconsistent -> fail" "version_source_consistency: fail"

echo "test-package-release-integrity: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
```

Make it executable:
```bash
chmod +x bin/test-package-release-integrity.sh
```

- [ ] **Step 2: Run the harness to verify it fails**

Run: `bin/test-package-release-integrity.sh`
Expected: FAIL — the helper has no `check` verb yet (`error: argument command: invalid choice` or `main` missing), both assertions fail.

- [ ] **Step 3: Implement discovery, the consistency check, and the CLI**

Append to `skills/package-release-integrity/scripts/release_integrity.py`:
```python
import argparse
import json
import sys
import tomllib
from pathlib import Path


def _verdict(check, verdict, detail):
    return {"check": check, "verdict": verdict, "detail": detail}


def discover_version_sources(repo):
    """Find declared package versions. Maps a source label -> raw version str.

    Sources: pyproject.toml [project].version, [tool.poetry].version, and any
    top-level package `__init__.py` defining `__version__`.
    """
    repo = Path(repo)
    sources = {}
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text())
        proj = data.get("project", {}).get("version")
        if proj is not None:
            sources["pyproject:[project].version"] = proj
        poetry = data.get("tool", {}).get("poetry", {}).get("version")
        if poetry is not None:
            sources["pyproject:[tool.poetry].version"] = poetry
    # (["'])([^"']+)\1 — backreferenced quote; avoids a "]" + "(" adjacency
    # that the repo's file-wide link checker would misread as a broken link.
    ver_re = re.compile(r"""^__version__\s*=\s*(["'])([^"']+)\1""", re.M)
    for init in sorted(repo.glob("*/__init__.py")):
        m = ver_re.search(init.read_text())
        if m:
            sources[f"module:{init.relative_to(repo)}"] = m.group(2)
    return sources


def check_version_source_consistency(sources):
    if not sources:
        return _verdict(
            "version_source_consistency", "uncertain", "no version source found"
        )
    distinct = set(sources.values())
    if len(distinct) == 1:
        return _verdict(
            "version_source_consistency", "pass",
            f"all sources agree on {next(iter(distinct))}",
        )
    return _verdict(
        "version_source_consistency", "fail",
        "version sources disagree: "
        + ", ".join(f"{k}={v}" for k, v in sorted(sources.items())),
    )


def run_check(repo, args):
    repo = Path(repo)
    verdicts = []
    sources = discover_version_sources(repo)
    verdicts.append(check_version_source_consistency(sources))
    ready = all(v["verdict"] != "fail" for v in verdicts)
    return {"verdicts": verdicts, "ready": ready}


def _print_report(report, as_json):
    if as_json:
        print(json.dumps(report, indent=2))
        return
    for v in report["verdicts"]:
        print(f"{v['check']}: {v['verdict']} — {v['detail']}")
    print(f"ready: {report['ready']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Portable package release-integrity checker")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="run release-integrity checks on a repo")
    c.add_argument("--repo", default=".", help="path to the package repo")
    c.add_argument("--json", action="store_true", help="emit JSON")
    args = p.parse_args(argv)
    if args.command == "check":
        report = run_check(args.repo, args)
        _print_report(report, args.json)
        # Exit non-zero only on a hard fail; 'uncertain' does not fail.
        return 1 if any(v["verdict"] == "fail" for v in report["verdicts"]) else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the harness to verify it passes**

Run: `bin/test-package-release-integrity.sh`
Expected: PASS — `test-package-release-integrity: 2 passed, 0 failed`.

- [ ] **Step 5: Wire the harness into the Makefile and pre-commit**

In `Makefile`, add `bin/test-package-release-integrity.sh` to the `test:` target's script list (alongside `bin/test-check.sh` etc.), matching the existing indentation/style.

In `.pre-commit-config.yaml`, add a local hook mirroring the `bin/test-check.sh` hook block:
```yaml
      - id: bindle-test-package-release-integrity
        name: package release-integrity helper tests
        entry: bin/test-package-release-integrity.sh
        language: system
        pass_filenames: false
        always_run: true
```
(Match the exact structure of the sibling `bin/test-check.sh` hook in that file — copy its keys, change `id`/`name`/`entry`.)

- [ ] **Step 6: Verify the gate runs the new suite**

Run: `make test 2>&1 | grep -A2 package-release-integrity`
Expected: the suite runs and reports `2 passed, 0 failed`.

- [ ] **Step 7: Commit**

```bash
git add skills/package-release-integrity/ bin/test-package-release-integrity.sh Makefile .pre-commit-config.yaml
git commit -m "feat(#59): version-source discovery + consistency check, CLI, test harness"
```

---

### Task 3: Tag consistency (#4) + changelog presence (#5)

Adds two mechanical checks. Tag consistency compares a caller-supplied `--tag` (normalized, leading `v` stripped) against the discovered package version. Changelog presence requires a `CHANGELOG.md` with a section for the version or `[Unreleased]`.

**Files:**
- Modify: `skills/package-release-integrity/scripts/release_integrity.py`
- Create: `skills/package-release-integrity/tests/fixtures/tag-mismatch/pyproject.toml`
- Create: `skills/package-release-integrity/tests/fixtures/missing-changelog/pyproject.toml`
- Create: `skills/package-release-integrity/tests/fixtures/consistent/CHANGELOG.md`
- Modify: `bin/test-package-release-integrity.sh`

**Interfaces:**
- Consumes: `discover_version_sources`, `parse_version`, `_verdict`, `run_check` (Tasks 1-2).
- Produces: `resolved_package_version(sources: dict) -> str | None`; `check_tag_consistency(pkg_version: str, tag: str | None) -> dict`; `check_changelog_present(repo: Path, pkg_version: str, required: bool) -> dict`. `run_check` gains `--tag` and `--no-changelog-required` handling.

- [ ] **Step 1: Add fixtures and failing assertions**

Create `skills/package-release-integrity/tests/fixtures/tag-mismatch/pyproject.toml`:
```toml
[project]
name = "tag-mismatch-pkg"
version = "1.2.0"
```

Create `skills/package-release-integrity/tests/fixtures/missing-changelog/pyproject.toml`:
```toml
[project]
name = "missing-changelog-pkg"
version = "1.2.0"
```

Create `skills/package-release-integrity/tests/fixtures/consistent/CHANGELOG.md`:
```markdown
# Changelog

## [1.2.0] - 2026-07-14
- initial
```

Append to `bin/test-package-release-integrity.sh` (before the final tally line):
```bash
echo "tag consistency:"
run python3 "$HELPER" check --repo "$FIX/consistent" --tag v1.2.0
expect_contains "matching tag -> pass" "tag_consistency: pass"
run python3 "$HELPER" check --repo "$FIX/tag-mismatch" --tag v1.1.0
expect_contains "mismatched tag -> fail" "tag_consistency: fail"
expect_rc "mismatched tag -> rc 1" 1

echo "changelog presence:"
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "changelog present -> pass" "changelog_present: pass"
run python3 "$HELPER" check --repo "$FIX/missing-changelog"
expect_contains "changelog absent -> fail" "changelog_present: fail"
```

- [ ] **Step 2: Run the harness to verify the new assertions fail**

Run: `bin/test-package-release-integrity.sh`
Expected: FAIL — no `tag_consistency`/`changelog_present` lines yet.

- [ ] **Step 3: Implement the two checks**

Add to `release_integrity.py`:
```python
def resolved_package_version(sources):
    """The agreed package version, or None if absent/conflicting."""
    distinct = set(sources.values())
    return next(iter(distinct)) if len(distinct) == 1 else None


def check_tag_consistency(pkg_version, tag):
    if tag is None:
        return _verdict("tag_consistency", "uncertain", "no --tag supplied")
    if pkg_version is None:
        return _verdict("tag_consistency", "uncertain", "no resolved package version")
    norm = tag[1:] if tag.startswith("v") else tag
    if norm == pkg_version:
        return _verdict("tag_consistency", "pass", f"tag {tag} == version {pkg_version}")
    return _verdict(
        "tag_consistency", "fail", f"tag {tag} (={norm}) != version {pkg_version}"
    )


def check_changelog_present(repo, pkg_version, required):
    changelog = Path(repo) / "CHANGELOG.md"
    if not changelog.is_file():
        verdict = "fail" if required else "uncertain"
        return _verdict("changelog_present", verdict, "CHANGELOG.md not found")
    text = changelog.read_text()
    if f"[{pkg_version}]" in text or "[Unreleased]" in text:
        return _verdict(
            "changelog_present", "pass", f"section for {pkg_version} or [Unreleased]"
        )
    verdict = "fail" if required else "uncertain"
    return _verdict(
        "changelog_present", verdict, f"no section for {pkg_version} or [Unreleased]"
    )
```

Update `run_check` to call them:
```python
def run_check(repo, args):
    repo = Path(repo)
    verdicts = []
    sources = discover_version_sources(repo)
    verdicts.append(check_version_source_consistency(sources))
    pkg_version = resolved_package_version(sources)
    verdicts.append(check_tag_consistency(pkg_version, getattr(args, "tag", None)))
    required = not getattr(args, "no_changelog_required", False)
    verdicts.append(check_changelog_present(repo, pkg_version, required))
    ready = all(v["verdict"] != "fail" for v in verdicts)
    return {"verdicts": verdicts, "ready": ready}
```

Add the CLI flags in `main`'s `check` parser:
```python
    c.add_argument("--tag", default=None, help="proposed/existing release tag")
    c.add_argument(
        "--no-changelog-required", action="store_true",
        help="treat a missing changelog section as uncertain, not fail",
    )
```

- [ ] **Step 4: Run the harness to verify it passes**

Run: `bin/test-package-release-integrity.sh`
Expected: PASS — all assertions pass.

- [ ] **Step 5: Commit**

```bash
git add skills/package-release-integrity/ bin/test-package-release-integrity.sh
git commit -m "feat(#59): tag-consistency + changelog-presence checks"
```

---

### Task 4: Change classification (#1), version movement (#2), track routing (#8)

Wires the judgment-vs-mechanical boundary. Without `--change-class`, classification and track routing return `uncertain`. With it, the helper verifies the semver movement between `--prev-version` and the package version, and that a `data-only` change did not move the package version.

**Files:**
- Modify: `skills/package-release-integrity/scripts/release_integrity.py`
- Create fixtures (each `pyproject.toml`): `pre-1.0-breaking` (v0.4.0), `post-1.0-breaking` (v2.0.0), `additive` (v1.3.0), `patch` (v1.2.1), `data-only` (v1.2.0)
- Modify: `bin/test-package-release-integrity.sh`

**Interfaces:**
- Consumes: `bump_type`, `required_movement`, `is_pre_1_0`, `parse_version`, `resolved_package_version` (Tasks 1-3).
- Produces: `check_change_classification(change_class: str | None) -> dict`; `check_version_movement(prev: str | None, pkg_version: str | None, change_class: str | None) -> dict`; `check_track_routing(change_class: str | None, version_moved: bool) -> dict`. `run_check` gains `--change-class` and `--prev-version`.

- [ ] **Step 1: Add fixtures and failing assertions**

Create these `pyproject.toml` files (only `name`/`version` differ):
- `.../fixtures/pre-1.0-breaking/pyproject.toml` → `version = "0.4.0"`
- `.../fixtures/post-1.0-breaking/pyproject.toml` → `version = "2.0.0"`
- `.../fixtures/additive/pyproject.toml` → `version = "1.3.0"`
- `.../fixtures/patch/pyproject.toml` → `version = "1.2.1"`
- `.../fixtures/data-only/pyproject.toml` → `version = "1.2.0"`

Each in the form:
```toml
[project]
name = "case-pkg"
version = "X.Y.Z"
```

Append to `bin/test-package-release-integrity.sh`:
```bash
echo "classification + movement (judgment gated):"
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "no class -> classification uncertain" "change_classification: uncertain"
expect_contains "no class -> movement uncertain" "version_movement: uncertain"

run python3 "$HELPER" check --repo "$FIX/pre-1.0-breaking" --prev-version 0.3.0 --change-class breaking
expect_contains "pre-1.0 breaking minor -> pass" "version_movement: pass"
run python3 "$HELPER" check --repo "$FIX/post-1.0-breaking" --prev-version 1.2.0 --change-class breaking
expect_contains "post-1.0 breaking major -> pass" "version_movement: pass"
run python3 "$HELPER" check --repo "$FIX/additive" --prev-version 1.2.0 --change-class additive
expect_contains "additive minor -> pass" "version_movement: pass"
run python3 "$HELPER" check --repo "$FIX/patch" --prev-version 1.2.0 --change-class patch
expect_contains "patch -> pass" "version_movement: pass"

run python3 "$HELPER" check --repo "$FIX/data-only" --prev-version 1.2.0 --change-class data-only
expect_contains "data-only no move -> track pass" "track_routing: pass"
run python3 "$HELPER" check --repo "$FIX/additive" --prev-version 1.2.0 --change-class data-only
expect_contains "data-only but moved -> track fail" "track_routing: fail"
```

- [ ] **Step 2: Run the harness to verify the new assertions fail**

Run: `bin/test-package-release-integrity.sh`
Expected: FAIL — no `change_classification`/`version_movement`/`track_routing` lines yet.

- [ ] **Step 3: Implement the three checks**

Add to `release_integrity.py`:
```python
_CLASSES = ("breaking", "additive", "patch", "data-only")


def check_change_classification(change_class):
    if change_class is None:
        return _verdict(
            "change_classification", "uncertain",
            "no --change-class supplied; a human must classify the change",
        )
    if change_class not in _CLASSES:
        return _verdict(
            "change_classification", "fail",
            f"unknown class {change_class!r}; expected one of {_CLASSES}",
        )
    return _verdict("change_classification", "pass", f"declared {change_class}")


def check_version_movement(prev, pkg_version, change_class):
    if change_class is None:
        return _verdict(
            "version_movement", "uncertain", "movement depends on the change class"
        )
    if change_class == "data-only":
        return _verdict(
            "version_movement", "uncertain", "data-only: routed under track_routing"
        )
    pv, nv = parse_version(prev or ""), parse_version(pkg_version or "")
    if pv is None or nv is None:
        return _verdict(
            "version_movement", "uncertain",
            "need valid --prev-version and package version to check movement",
        )
    want = required_movement(change_class, is_pre_1_0(nv))
    got = bump_type(pv, nv)
    if got == want:
        return _verdict(
            "version_movement", "pass",
            f"{change_class} moved {prev}->{pkg_version} ({got}) as required",
        )
    return _verdict(
        "version_movement", "fail",
        f"{change_class} requires a {want} bump; {prev}->{pkg_version} was {got}",
    )


def check_track_routing(change_class, version_moved):
    if change_class != "data-only":
        return _verdict(
            "track_routing", "uncertain",
            "track routing only auto-checked for data-only changes",
        )
    if version_moved:
        return _verdict(
            "track_routing", "fail",
            "data-only change moved the package version",
        )
    return _verdict("track_routing", "pass", "data-only change left the version unmoved")
```

Update `run_check`:
```python
def run_check(repo, args):
    repo = Path(repo)
    verdicts = []
    sources = discover_version_sources(repo)
    verdicts.append(check_version_source_consistency(sources))
    pkg_version = resolved_package_version(sources)
    verdicts.append(check_tag_consistency(pkg_version, getattr(args, "tag", None)))
    required = not getattr(args, "no_changelog_required", False)
    verdicts.append(check_changelog_present(repo, pkg_version, required))
    change_class = getattr(args, "change_class", None)
    prev = getattr(args, "prev_version", None)
    verdicts.append(check_change_classification(change_class))
    verdicts.append(check_version_movement(prev, pkg_version, change_class))
    pv, nv = parse_version(prev or ""), parse_version(pkg_version or "")
    moved = bool(pv and nv and bump_type(pv, nv) is not None)
    verdicts.append(check_track_routing(change_class, moved))
    ready = all(v["verdict"] != "fail" for v in verdicts)
    return {"verdicts": verdicts, "ready": ready}
```

Add CLI flags in `main`'s `check` parser:
```python
    c.add_argument(
        "--change-class", default=None, choices=_CLASSES,
        help="declared change class; omitted => classification is uncertain",
    )
    c.add_argument("--prev-version", default=None, help="previously released version")
```

- [ ] **Step 4: Run the harness to verify it passes**

Run: `bin/test-package-release-integrity.sh`
Expected: PASS — all classification/movement/routing assertions pass.

- [ ] **Step 5: Commit**

```bash
git add skills/package-release-integrity/ bin/test-package-release-integrity.sh
git commit -m "feat(#59): change-classification, version-movement, track-routing checks"
```

---

### Task 5: Build + test gate shell-out (#6, #7) + degraded-never-false-positive

Runs the repo's own build (#6) and verification (#7) commands via `--build-cmd`/`--test-cmd`. A missing command is `uncertain` (not `pass`); a non-zero exit is `fail`; an execution error (command not found) is `uncertain` with a degraded note — never a false `pass`.

**Files:**
- Modify: `skills/package-release-integrity/scripts/release_integrity.py`
- Modify: `bin/test-package-release-integrity.sh`

**Interfaces:**
- Consumes: `_verdict`, `run_check` (Tasks 1-4).
- Produces: `run_gate(name: str, cmd: str | None, repo: Path) -> dict` (used for both build and test gates; `verdict` is `pass` on exit 0, `fail` on non-zero, `uncertain` when `cmd` is None or execution raises). `run_check` gains `--build-cmd`, `--test-cmd`.

- [ ] **Step 1: Add failing assertions**

Append to `bin/test-package-release-integrity.sh`:
```bash
echo "build/test gates (shell-out):"
run python3 "$HELPER" check --repo "$FIX/consistent" --test-cmd "true"
expect_contains "passing test-cmd -> pass" "verification_gate: pass"
run python3 "$HELPER" check --repo "$FIX/consistent" --test-cmd "false"
expect_contains "failing test-cmd -> fail" "verification_gate: fail"
expect_rc "failing test-cmd -> rc 1" 1
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "no test-cmd -> uncertain" "verification_gate: uncertain"
run python3 "$HELPER" check --repo "$FIX/consistent" --test-cmd "definitely-not-a-real-cmd-xyz"
expect_contains "broken test-cmd -> uncertain (degraded)" "verification_gate: uncertain"
```

- [ ] **Step 2: Run the harness to verify the assertions fail**

Run: `bin/test-package-release-integrity.sh`
Expected: FAIL — no `verification_gate` line yet.

- [ ] **Step 3: Implement the gate runner**

Add to `release_integrity.py`:
```python
import subprocess


def run_gate(name, cmd, repo):
    """Shell out to a repo-supplied command. pass=0, fail=nonzero,
    uncertain=absent or unexecutable (degraded, never a false pass)."""
    if not cmd:
        return _verdict(name, "uncertain", "no command supplied for this gate")
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=str(repo),
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _verdict(name, "uncertain", f"could not run {cmd!r}: {exc} (degraded)")
    if proc.returncode == 0:
        return _verdict(name, "pass", f"{cmd!r} exited 0")
    return _verdict(name, "fail", f"{cmd!r} exited {proc.returncode}")
```

Update `run_check` to append the two gates (before computing `ready`):
```python
    verdicts.append(run_gate("build_gate", getattr(args, "build_cmd", None), repo))
    verdicts.append(
        run_gate("verification_gate", getattr(args, "test_cmd", None), repo)
    )
```

Add CLI flags in `main`'s `check` parser:
```python
    c.add_argument("--build-cmd", default=None, help="repo build/metadata command")
    c.add_argument("--test-cmd", default=None, help="repo verification command")
```

- [ ] **Step 4: Run the harness to verify it passes**

Run: `bin/test-package-release-integrity.sh`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/package-release-integrity/ bin/test-package-release-integrity.sh
git commit -m "feat(#59): build/verification gate shell-out with degraded-never-false-positive"
```

---

### Task 6: DomI defer path — authority detection reusing domi-consumer (#58)

Before running checks, detect whether the target repo declares DomI release-governance authoritative. If so, the report's mode is `defer` (advisory-only), and the CLI prints a clear "DomI authoritative — run DomI's release-integrity" line without claiming to replace it.

**Files:**
- Modify: `skills/package-release-integrity/scripts/release_integrity.py`
- Create: `skills/package-release-integrity/tests/fixtures/domi-governed/.domi-pin`
- Create: `skills/package-release-integrity/tests/fixtures/domi-governed/pyproject.toml`
- Modify: `bin/test-package-release-integrity.sh`

**Interfaces:**
- Consumes: `run_check` (Tasks 1-5).
- Produces: `detect_domi_authority(repo: Path) -> bool`; `run_check` returns an added `"mode": "portable"|"defer"` key; `main` prints the defer banner when mode is `defer`.

- [ ] **Step 1: Confirm the domi-consumer detection contract**

Before implementing, read `skills/domi-consumer/SKILL.md` and `bin/domi-status.sh` (the repo-root executable the domi-consumer skill uses) to learn how it detects a `.domi-pin` and reports owned policy categories. The `detect_domi_authority` implementation below reads `.domi-pin` directly (dependency-light) but MUST match domi-consumer's notion of "release-integrity is an owned category." If `domi-status.sh` exposes a machine-readable mode, prefer calling it; otherwise the direct read below is the fallback. Record which mechanism you used in the commit message.

- [ ] **Step 2: Add fixtures and a failing assertion**

Create `skills/package-release-integrity/tests/fixtures/domi-governed/pyproject.toml`:
```toml
[project]
name = "domi-governed-pkg"
version = "1.2.0"
```

Create `skills/package-release-integrity/tests/fixtures/domi-governed/.domi-pin` with content that domi-consumer recognizes as declaring release-integrity ownership (match the real `.domi-pin` schema you confirmed in Step 1). Minimal illustrative form:
```
domi_sha=0000000000000000000000000000000000000000
owned_categories=release-integrity,branch-policy
```

Append to `bin/test-package-release-integrity.sh`:
```bash
echo "DomI defer path:"
run python3 "$HELPER" check --repo "$FIX/domi-governed"
expect_contains "domi-governed -> defer mode" "mode: defer"
expect_contains "domi-governed -> defer banner" "DomI authoritative"
run python3 "$HELPER" check --repo "$FIX/consistent"
expect_contains "plain repo -> portable mode" "mode: portable"
```

- [ ] **Step 3: Run the harness to verify the assertions fail**

Run: `bin/test-package-release-integrity.sh`
Expected: FAIL — no `mode:` line / defer banner yet.

- [ ] **Step 4: Implement authority detection and the defer branch**

Add to `release_integrity.py`:
```python
def detect_domi_authority(repo):
    """True when the repo declares DomI release-integrity governance.

    Reads .domi-pin directly (dependency-light). Mirrors the domi-consumer
    skill's notion of an owned policy category; see that skill for the schema.
    """
    pin = Path(repo) / ".domi-pin"
    if not pin.is_file():
        return False
    for line in pin.read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "owned_categories":
            cats = {c.strip() for c in value.split(",")}
            return "release-integrity" in cats
    return False
```

Update `run_check` to set the mode and short-circuit checks under defer:
```python
def run_check(repo, args):
    repo = Path(repo)
    if detect_domi_authority(repo):
        return {"mode": "defer", "verdicts": [], "ready": None}
    report = {"mode": "portable"}
    # ... existing verdict-building body, then:
    report["verdicts"] = verdicts
    report["ready"] = ready
    return report
```
(Refactor the existing body so the `portable` branch builds `verdicts`/`ready` exactly as before; only the early `defer` return and the `"mode"` key are new.)

Update `_print_report` and `main` to surface the mode:
```python
def _print_report(report, as_json):
    if as_json:
        print(json.dumps(report, indent=2))
        return
    print(f"mode: {report['mode']}")
    if report["mode"] == "defer":
        print(
            "DomI authoritative — run DomI's release-integrity; "
            "Bindle's checks are advisory-only here and do not replace it."
        )
        return
    for v in report["verdicts"]:
        print(f"{v['check']}: {v['verdict']} — {v['detail']}")
    print(f"ready: {report['ready']}")
```
In `main`, a `defer` report exits 0 (deferral is not a failure):
```python
        if report["mode"] == "defer":
            return 0
        return 1 if any(v["verdict"] == "fail" for v in report["verdicts"]) else 0
```

- [ ] **Step 5: Run the harness to verify it passes**

Run: `bin/test-package-release-integrity.sh`
Expected: PASS — defer + portable modes both asserted.

- [ ] **Step 6: Commit**

```bash
git add skills/package-release-integrity/ bin/test-package-release-integrity.sh
git commit -m "feat(#59): DomI defer-path detection reusing domi-consumer contract"
```

---

### Task 7: Contract doc + capability contract row

The provider-neutral contract `docs/package-release-integrity.md`, flat in `docs/`, matching the existing contract-doc skeleton. Registers it as a `type:"contract"` capability.

**Files:**
- Create: `docs/package-release-integrity.md`
- Modify: `capabilities.json` (add a `type:"contract"` row)

**Interfaces:** none (prose + registration). Gated by `make check` (frontmatter/links/private-info/inventory).

- [ ] **Step 1: Write the contract doc**

Create `docs/package-release-integrity.md` following the house skeleton (status line → the nine checks → the defer rule → 3 worked examples → "Where this fits"). Required content:
- **Status line:** `**Status:** Contract, v1 · **Issue:** thomas-estep/bindle#59`
- **The nine checks**, each: what it asserts, whether it is mechanical (helper) or judgment (human), and the pass/fail/uncertain meaning. Copy the ownership split from the design spec's table verbatim.
- **The defer rule:** when a repo declares DomI release governance authoritative (a `.domi-pin` with `release-integrity` owned), defer — Bindle's checks are advisory-only and never claim to replace DomI. Cross-reference the `domi-consumer` skill by name.
- **The helper contract:** verbs/flags (`check --repo --tag --prev-version --change-class --build-cmd --test-cmd --json`), the `pass`/`fail`/`uncertain` semantics, exit codes, and that `uncertain` never fails.
- **Three worked examples** (mirroring the sibling docs' "always 3" rhythm): (1) a clean post-1.0 additive release → all pass, ready; (2) a data-only change that wrongly moved the version → `track_routing: fail`; (3) a DomI-governed repo → defer.
- **Boundaries:** never bumps a version; a green check is not publish authorization; repo-local + inherited-DomI policy beat generic defaults; network/tool failure → uncertain/degraded.
- **"Where this fits":** cross-reference `docs/release-manifest.md` (#33, distinct concern — records what a *Bindle* release shipped), the `domi-consumer` skill, and the `skills/package-release-integrity/` skill.

Use inline-code refs (`` `docs/x.md` ``) or repo-absolute `/docs/...` links only — never a relative bracket-then-paren Markdown link (a `]` immediately followed by `(target)`) to another doc, because the link checker resolves those relative to `docs/` and greps inside code fences too.

- [ ] **Step 2: Add the contract capability row**

In `capabilities.json`, add to the `capabilities` array a row modeled on the existing `release-manifest → docs/release-manifest.md` contract row:
```json
{
  "name": "package-release-integrity",
  "type": "contract",
  "path": "docs/package-release-integrity.md",
  "description": "Provider-neutral contract for validating a Python package release (version-source, tag, changelog, semver movement, tracks) before publish; defers to DomI where DomI owns release governance.",
  "provider": { "claude": "supported", "codex": "supported" },
  "maturity": "documented",
  "mutation": [],
  "version_introduced": "0.3.0"
}
```
(Confirm the exact enum values against a sibling contract row before committing — `provider` status strings and `maturity` values are validated by `bin/check-inventory.py`.)

- [ ] **Step 3: Verify the gate**

Run:
```bash
git add docs/package-release-integrity.md capabilities.json
make check
```
Expected: green — links resolve, capability inventory reconciles (contract row present), private-info scan clean.

- [ ] **Step 4: Commit**

```bash
git commit -m "docs(#59): provider-neutral package-release-integrity contract"
```

---

### Task 8: Skill body, portability-audit row, CHANGELOG draft, pressure tests

Rewrites the scaffolded `SKILL.md` into the real skill that drives the control flow, adds the portability-audit matrix row, and records the feature as a **draft** in the CHANGELOG until pressure tests pass.

**Files:**
- Modify: `skills/package-release-integrity/SKILL.md`
- Create: `skills/package-release-integrity/PRESSURE-TESTS.md`
- Modify: `docs/skill-portability-audit.md` (add matrix row)
- Modify: `capabilities.json` (promote the skill row `description`/`maturity` if needed)
- Modify: `CHANGELOG.md` (draft entry)

**Interfaces:** none (prose + registration). Gated by `make check`.

- [ ] **Step 1: Write the SKILL.md body**

Rewrite `skills/package-release-integrity/SKILL.md` (keep the scaffolded frontmatter `name` + a precise `description`). Body sections, following the in-repo data/check-skill shape (`## Overview` → `## When to Use` → `## The gate`/`## Steps`):
- **Overview:** one paragraph — validate a Python package release before publish; defer to DomI where it governs release integrity; never authorizes publishing.
- **When to Use:** before cutting/publishing a package release; when asked "is this release consistent/safe to cut."
- **Steps** = the six-step control flow (detect authority → discover → mechanical checks → judgment steps → gate → report), naming the helper invocation:
  `python3 skills/package-release-integrity/scripts/release_integrity.py check --repo <path> [--tag ...] [--prev-version ...] [--change-class ...] [--build-cmd ...] [--test-cmd ...]`
- **Judgment boundary:** the skill (or a human) supplies `--change-class` after classifying the change; the helper never guesses breaking. `uncertain` means "decide, then re-run."
- **Boundaries/red flags:** a green check is not publish authorization; never bump a version to satisfy the check; under defer, do not override DomI.

- [ ] **Step 2: Add the portability-audit matrix row**

In `docs/skill-portability-audit.md`, add an 11-column row for `package-release-integrity` (match the header at the matrix top and the `domi-consumer` row's style). Disposition: helper is stdlib Python + shells to repo tools → **Codex-portable**; `SKILL.md` invocation wording stays Claude-native (Phase 1). Evidence level reflects the fixture suite (and, once done, the pressure tests).

- [ ] **Step 3: Add the CHANGELOG draft entry**

In `CHANGELOG.md`'s `## [Unreleased]`, add an entry marking the skill a **draft** until pressure-tested, e.g.:
```markdown
- **package-release-integrity (draft, #59):** portable, clean-room, defer-aware
  package release-integrity workflow — contract doc, Claude-native skill, and a
  stdlib-Python helper (version-source, tag, changelog, semver-movement checks;
  judgment checks return `uncertain`; defers to DomI where it governs release
  integrity). Draft until pressure-tested per superpowers:writing-skills.
```

- [ ] **Step 4: Verify the gate**

Run:
```bash
git add skills/package-release-integrity/ docs/skill-portability-audit.md capabilities.json CHANGELOG.md
make check
```
Expected: green — frontmatter valid, inventory reconciles (skill + contract rows, audit row present), links resolve.

- [ ] **Step 5: Commit**

```bash
git commit -m "docs(#59): package-release-integrity skill body, portability row, draft changelog"
```

- [ ] **Step 6: Pressure-test the skill (RED → GREEN)**

Per the repo rule, the skill is a draft until pressure-tested. Run the campaign per `skills/<name>/PRESSURE-TESTS.md` conventions:
- Fresh subagents in throwaway fixture repos (copies of the fixtures), ~5 reps/variant.
- **RED arm:** confirm the skill is genuinely absent first (a probe subagent returns "Unknown skill"); use fixture dirs NOT named after the skill; a hard "do NOT invoke the Skill tool" baseline.
- **GREEN arm:** the skill triggers on a release-consistency request and drives the helper.
- Score the filesystem/verdict output (grep the subagent transcript `tasks/<id>.output` for `"name":"Skill"`), not the self-report.
- Record results in `skills/package-release-integrity/PRESSURE-TESTS.md`.

- [ ] **Step 7: Promote from draft and validate the DomI defer path on a real repo**

- Once pressure tests pass, drop the `draft` marker in the CHANGELOG and set the skill row `maturity` to `tested` in `capabilities.json`.
- Run a read-only dry-run against a real `.domi-pin` repo (DomI) confirming `detect_domi_authority` returns the defer mode there (acceptance criterion 3, defer path). Record the outcome.
- `make check`; commit `docs(#59): promote package-release-integrity from draft (pressure-tested)`.

---

## Notes for the executor

- **Refactor discipline (Task 6):** the `run_check` refactor must preserve the exact verdict list and `ready` computation from Tasks 2-5 in the `portable` branch — only the early `defer` return and the `"mode"` key are new. Re-run the full harness after refactoring.
- **Every commit:** `make check` green first; branch `feature/package-release-integrity-59`; never `--no-verify`; never push (the operator pushes).
- **Registration drift:** if `make check` fails on inventory drift after adding the skill/doc, the fix is a missing `capabilities.json` row, `docs/skill-portability-audit.md` row, or `not_a_capability` entry — not a code change.
