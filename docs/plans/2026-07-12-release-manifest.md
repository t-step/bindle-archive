# Release manifest with provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bin/release.sh` produces `RELEASE-MANIFEST.json`, a deterministic,
provenance-rich record of what a Bindle release shipped, drawn from
`capabilities.json`/`install-manifest.tsv` rather than hand-duplicated, and
the release aborts before committing if the manifest can't be regenerated
consistently (issue #33).

**Architecture:** A new stdlib-only `bin/release-manifest.py` (mirroring
`bin/check-inventory.py`'s style) builds the manifest from repo state; a new
additive step in `bin/release.sh` runs it in `--verify-determinism` mode
(generate twice, diff every field except `timestamp`, abort on mismatch)
then `--emit`s the file into the same `Release vX.Y.Z` commit as
`VERSION`/`CHANGELOG.md`.

**Tech Stack:** Bash (`bin/release.sh`, tests), stdlib-only Python 3
(`bin/release-manifest.py`, matching `bin/check-inventory.py`'s no-dependency
convention).

## Global Constraints

- Design doc: `docs/design/2026-07-12-release-manifest.md` (approved) — every
  task below implements a section of it; don't improvise beyond it.
- stdlib-only Python — no `pip install`, no third-party imports, matching
  `bin/check-inventory.py`.
- Never push, never auto-publish a GitHub release, no signing/checksums
  beyond the plain `self_checksum` content hash already approved in the
  design. Non-goals per issue #33.
- `bin/release.sh`'s existing tag-cutting behavior is not restructured —
  only one new additive step is inserted.
- `RELEASE-MANIFEST.json` is NOT drift-checked by `make check` against HEAD
  (unlike `install-manifest.tsv`) — it's a point-in-time record of a past
  release, expected to diverge from a fresh regeneration the moment a new
  commit lands. Do not wire a `--check-manifest`-style gate for it into
  `bin/check.sh`.
- Shell scripts: 2-space indent, `shfmt -i 2 -ci`; must pass `shellcheck`.
- Every tracked text file must end in a newline, no trailing whitespace
  (`bin/check.sh` checks 3).
- Branch `feature/33-release-manifest` already exists and is checked out
  (cut from `main` at `e58e0d3`); `no-commit-to-branch` blocks direct commits
  to `main`. One PR, closes #33.
- `bin/check-inventory.py`'s fuzzy-candidate set is `bin/*.sh` **and**
  `bin/*.py`; both `bin/release-manifest.py` (ledger — internal machinery,
  same precedent as `bin/check-inventory.py`/`bin/release.sh`) and
  `docs/release-manifest.md` (capabilities.json row, type `contract`, same
  precedent as `docs/capability-inventory.md`) must be classified or
  `make check` fails. `bin/test-release-manifest.sh` is auto-excluded by the
  existing `^bin/test-.*\.sh$` rule.
- Verify-before-commit: run `bin/check.sh` (or `make check`) before every
  commit in this plan; never `--no-verify`.

---

### Task 1: `bin/release-manifest.py` generator + its test suite

**Files:**
- Create: `bin/release-manifest.py`
- Create: `bin/test-release-manifest.sh`
- Modify: `docs/plans/2026-07-12-release-manifest.md` (this file — none, already committed)

**Interfaces:**
- Produces (consumed by Task 2's `bin/release.sh` wiring):
  - CLI: `bin/release-manifest.py --root DIR --version V --previous V [--emit [PATH]] [--verify-determinism]`
  - `--emit` with no `PATH`: writes `RELEASE-MANIFEST.json` under `--root`.
    `--emit -`: writes to stdout. `--emit PATH`: writes to that path.
  - `--verify-determinism`: prints `"release manifest generation is
    deterministic"` and exits 0 if two back-to-back generations agree on
    every field except `timestamp`; otherwise prints the differing field
    names and exits 1. Writes nothing.
  - Exit code 1 (with a one-line message on stdout) on any of: missing
    `capabilities.json`, missing `install-manifest.tsv`, no matching
    `## [<version>]` section in `CHANGELOG.md`.

This task is one cohesive TDD unit — the script's functions are too
interdependent (nearly everything feeds `build_manifest`) to review or test
independently, so the "smallest unit with its own test cycle" here is the
whole script plus its fixture-repo test suite.

- [ ] **Step 1: Write `bin/release-manifest.py`**

```python
#!/usr/bin/env python3
"""Generate RELEASE-MANIFEST.json — a deterministic, provenance-rich record
of what a Bindle release shipped (issue #33). Stdlib-only.

Usage:
  bin/release-manifest.py --version V --previous V [--root DIR] --emit [PATH]
  bin/release-manifest.py --version V --previous V [--root DIR] --verify-determinism
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

# By the time bin/release.sh calls this script, bin/check.sh and
# bin/test-install.sh have already run under `set -euo pipefail` — a
# nonzero exit would have aborted the release before this script is ever
# invoked. This is a truthful provenance record of that invariant, not a
# live-executed signal (re-running both here on every release would also be
# slow: check.sh scans the whole repo).
VERIFICATION = [
    {"command": "bin/check.sh", "exit_code": 0},
    {"command": "bin/test-install.sh", "exit_code": 0},
]

TOOLS = ["git", "bash", "python3", "shellcheck", "shfmt"]


def _default_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_capabilities(root):
    path = os.path.join(root, "capabilities.json")
    if not os.path.isfile(path):
        raise ValueError("capabilities.json: missing at repo root")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        raise ValueError("capabilities.json: 'capabilities' must be an array")
    return caps


def capability_snapshot(caps):
    rows = []
    for c in caps:
        if not isinstance(c, dict):
            continue
        rows.append({
            "name": c.get("name"),
            "type": c.get("type"),
            "provider": c.get("provider"),
            "maturity": c.get("maturity"),
            "version_introduced": c.get("version_introduced"),
        })
    rows.sort(key=lambda r: (r["name"] or ""))
    return rows


def load_install_manifest(root):
    path = os.path.join(root, "install-manifest.tsv")
    if not os.path.isfile(path):
        raise ValueError("install-manifest.tsv: missing (run 'make manifest')")
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 5:
                continue
            provider, category, name, src, dest = parts
            rows.append({"provider": provider, "category": category,
                         "name": name, "src": src, "dest": dest})
    rows.sort(key=lambda r: (r["provider"], r["category"], r["name"]))
    return rows


def tool_versions():
    versions = {}
    for tool in TOOLS:
        try:
            out = subprocess.run([tool, "--version"], capture_output=True,
                                 text=True, check=True)
            versions[tool] = (out.stdout.strip() or out.stderr.strip()
                              or "unknown")
        except (OSError, subprocess.CalledProcessError):
            versions[tool] = "not installed"
    return versions


def git_commit_sha(root):
    out = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def changelog_section(root, version):
    path = os.path.join(root, "CHANGELOG.md")
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    header_prefix = "## [%s]" % version
    start = None
    for i, line in enumerate(lines):
        if line.startswith(header_prefix):
            start = i
            break
    if start is None:
        raise ValueError("CHANGELOG.md: no '%s' section found" % header_prefix)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## ["):
            end = i
            break
    return "".join(lines[start:end]).rstrip("\n")


def _canonical(manifest, exclude):
    trimmed = {k: v for k, v in manifest.items() if k not in exclude}
    return json.dumps(trimmed, sort_keys=True, separators=(",", ":"))


def self_checksum(manifest):
    # Excludes 'timestamp' from the hashed content (not just 'self_checksum'
    # itself), so the checksum represents shipped content, not when the
    # manifest happened to be generated — this also makes self_checksum
    # identical across the two --verify-determinism passes below.
    digest = hashlib.sha256(
        _canonical(manifest, {"self_checksum", "timestamp"}).encode("utf-8")
    ).hexdigest()
    return "sha256:" + digest


def build_manifest(root, version, previous, timestamp):
    caps = load_capabilities(root)
    manifest = {
        "generated_by": "bin/release-manifest.py — do not edit by hand",
        "version": version,
        "previous_version": previous,
        "commit_sha": git_commit_sha(root),
        "timestamp": timestamp,
        "changelog": changelog_section(root, version),
        "capabilities": capability_snapshot(caps),
        "installed_surfaces": load_install_manifest(root),
        "verification": VERIFICATION,
        "tool_versions": tool_versions(),
    }
    manifest["self_checksum"] = self_checksum(manifest)
    return manifest


def _diff_manifests(m1, m2):
    """Field names that differ between two manifests, ignoring 'timestamp'
    (the one field expected to vary between generations)."""
    diffs = []
    for key in sorted(set(m1) | set(m2)):
        if key == "timestamp":
            continue
        if m1.get(key) != m2.get(key):
            diffs.append(key)
    return diffs


def verify_determinism(root, version, previous):
    # Fixed, distinct dummy timestamps — real wall-clock calls could
    # coincidentally match at low time resolution, which would silently
    # weaken this check. The timestamps are deliberately never equal.
    m1 = build_manifest(root, version, previous, "t1")
    m2 = build_manifest(root, version, previous, "t2")
    return _diff_manifests(m1, m2)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    parser.add_argument("--version", required=True)
    parser.add_argument("--previous", required=True)
    parser.add_argument("--emit", nargs="?", const="", default=None,
                        metavar="PATH",
                        help="write the release manifest (default "
                             "RELEASE-MANIFEST.json under --root; '-' = stdout)")
    parser.add_argument("--verify-determinism", action="store_true",
                        help="generate the manifest twice and diff every "
                             "field except timestamp; nonzero exit on mismatch")
    args = parser.parse_args(argv)
    root = args.root or _default_root()

    if not args.verify_determinism and args.emit is None:
        parser.error("pass --emit or --verify-determinism")

    try:
        if args.verify_determinism:
            diffs = verify_determinism(root, args.version, args.previous)
            if diffs:
                print("release manifest is not deterministic — differing "
                     "fields: %s" % ", ".join(diffs))
                return 1
            print("release manifest generation is deterministic")
        if args.emit is not None:
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            manifest = build_manifest(root, args.version, args.previous,
                                      timestamp)
            text = json.dumps(manifest, indent=2) + "\n"
            if args.emit == "-":
                sys.stdout.write(text)
            else:
                dest = args.emit or os.path.join(root, "RELEASE-MANIFEST.json")
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(text)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: `chmod +x bin/release-manifest.py`**

```bash
chmod +x bin/release-manifest.py
```

- [ ] **Step 3: Write `bin/test-release-manifest.sh`**

```bash
#!/usr/bin/env bash
#
# test-release-manifest.sh — exercise bin/release-manifest.py against
# throwaway fixture repos. Mirrors bin/test-check-inventory.sh's shape.
#
set -uo pipefail

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GENERATOR="$REPO_ROOT/bin/release-manifest.py"
PY="$(command -v python3)"

pass=0 fail=0
check() { # check "description" command...
  local desc="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  ✗ %s\n' "$desc"
    fail=$((fail + 1))
  fi
}
contains() { grep -qF -- "$1" <<<"$2"; }
not_contains() { ! grep -qF -- "$1" <<<"$2"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# mkfixture DIR — a minimal, fully valid fixture repo the generator
# succeeds against: capabilities.json, install-manifest.tsv, a CHANGELOG.md
# with a [0.1.0] section, and a real git repo (git_commit_sha needs one).
mkfixture() {
  local r="$1"
  mkdir -p "$r"
  cat >"$r/capabilities.json" <<'JSON'
{
  "capabilities": [
    {"name": "demo", "type": "skill", "path": "skills/demo",
     "description": "Demo skill.",
     "provider": {"claude": "installed", "codex": "untested"},
     "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"}
  ],
  "not_a_capability": []
}
JSON
  cat >"$r/install-manifest.tsv" <<'TSV'
# GENERATED from capabilities.json — do not edit; run 'make manifest'
claude	skill	demo	skills/demo	skills/demo
TSV
  cat >"$r/CHANGELOG.md" <<'MD'
# Changelog

## [Unreleased]

## [0.1.0] - 2026-01-01

### Added

- Initial release.

## [0.0.9] - 2025-12-01

### Added

- Prehistory.
MD
  (cd "$r" && git init -q && git symbolic-ref HEAD refs/heads/main &&
    git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m init)
}

# --- happy path: --emit to a file -------------------------------------------
REPO="$TMP/happy"
mkfixture "$REPO"
"$PY" "$GENERATOR" --root "$REPO" --version 0.1.0 --previous 0.0.9 --emit >/dev/null
check "writes RELEASE-MANIFEST.json" test -f "$REPO/RELEASE-MANIFEST.json"
out="$(cat "$REPO/RELEASE-MANIFEST.json")"
check "records version" bash -c 'contains "\"version\": \"0.1.0\"" "$1"' _ "$out"
check "records previous_version" bash -c 'contains "\"previous_version\": \"0.0.9\"" "$1"' _ "$out"
check "records commit_sha" bash -c 'contains "\"commit_sha\":" "$1"' _ "$out"
check "records demo capability" bash -c 'contains "\"name\": \"demo\"" "$1"' _ "$out"
check "records installed surface" bash -c 'contains "\"dest\": \"skills/demo\"" "$1"' _ "$out"
check "records verification commands" bash -c 'contains "bin/check.sh" "$1"' _ "$out"
check "records self_checksum" bash -c 'contains "\"self_checksum\": \"sha256:" "$1"' _ "$out"
check "records changelog section text" bash -c 'contains "Initial release." "$1"' _ "$out"

# --- happy path: --emit - (stdout) ------------------------------------------
out2="$("$PY" "$GENERATOR" --root "$REPO" --version 0.1.0 --previous 0.0.9 --emit -)"
check "--emit - writes to stdout" bash -c 'contains "\"version\": \"0.1.0\"" "$1"' _ "$out2"

# --- happy path: --verify-determinism ---------------------------------------
det_out="$("$PY" "$GENERATOR" --root "$REPO" --version 0.1.0 --previous 0.0.9 --verify-determinism)"
check "verify-determinism succeeds on an unchanged fixture" \
  bash -c 'contains "deterministic" "$1"' _ "$det_out"

# --- error: missing capabilities.json ---------------------------------------
REPO2="$TMP/no-caps"
mkfixture "$REPO2"
rm "$REPO2/capabilities.json"
err="$("$PY" "$GENERATOR" --root "$REPO2" --version 0.1.0 --previous 0.0.9 --emit - 2>&1)"
check "errors on missing capabilities.json" \
  bash -c 'contains "capabilities.json: missing" "$1"' _ "$err"

# --- error: missing install-manifest.tsv ------------------------------------
REPO3="$TMP/no-manifest"
mkfixture "$REPO3"
rm "$REPO3/install-manifest.tsv"
err3="$("$PY" "$GENERATOR" --root "$REPO3" --version 0.1.0 --previous 0.0.9 --emit - 2>&1)"
check "errors on missing install-manifest.tsv" \
  bash -c 'contains "install-manifest.tsv: missing" "$1"' _ "$err3"

# --- error: no matching CHANGELOG section ------------------------------------
REPO4="$TMP/no-changelog-section"
mkfixture "$REPO4"
err4="$("$PY" "$GENERATOR" --root "$REPO4" --version 9.9.9 --previous 0.1.0 --emit - 2>&1)"
check "errors on missing CHANGELOG section" \
  bash -c 'contains "no .\[9.9.9\]. section found" "$1"' _ "$err4"

# --- tool_versions: "not installed" when absent from PATH -------------------
STUB="$TMP/stubpath"
mkdir -p "$STUB"
for bin in git bash python3; do
  real="$(command -v "$bin")"
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$real" >"$STUB/$bin"
  chmod +x "$STUB/$bin"
done
stub_out="$(PATH="$STUB" "$PY" "$GENERATOR" --root "$REPO" --version 0.1.0 --previous 0.0.9 --emit - 2>&1)"
check "shellcheck reports not installed when absent from PATH" \
  bash -c 'contains "\"shellcheck\": \"not installed\"" "$1"' _ "$stub_out"
check "shfmt reports not installed when absent from PATH" \
  bash -c 'contains "\"shfmt\": \"not installed\"" "$1"' _ "$stub_out"
check "git still resolves via the stub PATH" \
  bash -c 'contains "\"git\":" "$1"' _ "$stub_out"

# --- _diff_manifests unit tests (imported directly, not via the CLI) --------
diff_check="$("$PY" - "$GENERATOR" <<'PYEOF'
import importlib.util, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("release_manifest", path)
rm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rm)

d1 = rm._diff_manifests({"a": 1, "timestamp": "t1"}, {"a": 2, "timestamp": "t2"})
assert d1 == ["a"], d1

d2 = rm._diff_manifests({"a": 1, "timestamp": "t1"}, {"a": 1, "timestamp": "t2"})
assert d2 == [], d2

print("ok")
PYEOF
)"
check "_diff_manifests flags a real field mismatch, ignores timestamp" \
  bash -c 'contains "ok" "$1"' _ "$diff_check"

echo
echo "release-manifest tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
```

- [ ] **Step 4: `chmod +x bin/test-release-manifest.sh` and run it**

```bash
chmod +x bin/test-release-manifest.sh
bin/test-release-manifest.sh
```

Expected: every `check` line prints `✓`, final line `release-manifest tests:
N passed, 0 failed`, exit 0.

- [ ] **Step 5: shellcheck/shfmt the new shell test**

```bash
shellcheck bin/test-release-manifest.sh
shfmt -i 2 -ci -d bin/test-release-manifest.sh
```

Expected: no output from either (clean). If `shfmt` reports a diff, run
`shfmt -i 2 -ci -w bin/test-release-manifest.sh` and re-check.

- [ ] **Step 6: Commit**

```bash
git add bin/release-manifest.py bin/test-release-manifest.sh
git commit -m "feat: add bin/release-manifest.py generator + tests (#33)"
```

---

### Task 2: Wire the generator into `bin/release.sh` + `Makefile`

**Files:**
- Modify: `bin/release.sh` (insert a new step between the CHANGELOG roll and
  the commit/tag block — currently lines 76–81, see current content below)
- Modify: `Makefile` (the `test:` target, currently lines 18–29)

**Interfaces:**
- Consumes: `bin/release-manifest.py`'s CLI from Task 1
  (`--version`/`--previous`/`--emit`/`--verify-determinism`).
- Produces: `RELEASE-MANIFEST.json` now exists at repo root after any real
  `bin/release.sh` run, and is included in the `Release vX.Y.Z` commit.

Current `bin/release.sh` (relevant tail, for exact anchoring):

```bash
# --- roll VERSION + CHANGELOG ---------------------------------------------
if ! grep -q '^## \[Unreleased\]' CHANGELOG.md; then
  echo "CHANGELOG.md is missing a '## [Unreleased]' section." >&2
  exit 1
fi
printf '%s\n' "$new" >VERSION

# Insert a dated version header right after the [Unreleased] line; the existing
# Unreleased notes become this release, leaving Unreleased empty for next time.
awk -v ver="$new" -v day="$today" '
  /^## \[Unreleased\]/ && !inserted {
    print
    print ""
    print "## [" ver "] - " day
    inserted = 1
    next
  }
  { print }
' CHANGELOG.md >CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md

# --- commit + tag ----------------------------------------------------------
git add VERSION CHANGELOG.md
git commit -q -m "Release v${new}"
git tag -a "v${new}" -m "Bindle v${new}"
```

- [ ] **Step 1: Insert the release-manifest step into `bin/release.sh`**

Replace the block above with:

```bash
# --- roll VERSION + CHANGELOG ---------------------------------------------
if ! grep -q '^## \[Unreleased\]' CHANGELOG.md; then
  echo "CHANGELOG.md is missing a '## [Unreleased]' section." >&2
  exit 1
fi
printf '%s\n' "$new" >VERSION

# Insert a dated version header right after the [Unreleased] line; the existing
# Unreleased notes become this release, leaving Unreleased empty for next time.
awk -v ver="$new" -v day="$today" '
  /^## \[Unreleased\]/ && !inserted {
    print
    print ""
    print "## [" ver "] - " day
    inserted = 1
    next
  }
  { print }
' CHANGELOG.md >CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md

# --- release manifest -------------------------------------------------------
# Generate twice and diff (ignoring timestamp) before writing anything —
# a release fails here rather than commit an inconsistent manifest.
echo "Verifying the release manifest can be generated deterministically..."
python3 bin/release-manifest.py --version "$new" --previous "$cur" --verify-determinism
python3 bin/release-manifest.py --version "$new" --previous "$cur" --emit

# --- commit + tag ----------------------------------------------------------
git add VERSION CHANGELOG.md RELEASE-MANIFEST.json
git commit -q -m "Release v${new}"
git tag -a "v${new}" -m "Bindle v${new}"
```

Use the Edit tool with the "Current" block above as `old_string` and this as
`new_string` (both blocks are copied verbatim from/for `bin/release.sh`).

- [ ] **Step 2: shellcheck/shfmt `bin/release.sh`**

```bash
shellcheck bin/release.sh
shfmt -i 2 -ci -d bin/release.sh
```

Expected: clean (no output). `bin/release.sh` already runs under
`set -euo pipefail`, so the two new `python3` calls need no explicit `||
exit` — a nonzero exit from either aborts the script automatically, same as
the existing `bin/check.sh`/`bin/test-install.sh` calls above them.

- [ ] **Step 3: Add the new test to `Makefile`'s `test:` target**

Current (`Makefile` lines 18–29):

```makefile
test:
	bin/test-install.sh
	bin/test-check.sh
	bin/test-check-frontmatter.sh
	bin/test-check-inventory.sh
	bin/test-manifest-lib.sh
	bin/test-doctor.sh
	bin/test-notes-home.sh
	bin/test-nested-notes-guard.sh
	bin/test-session-context.sh
	bin/test-session-hooks.sh
	bin/test-install-session-hooks.sh
```

New:

```makefile
test:
	bin/test-install.sh
	bin/test-check.sh
	bin/test-check-frontmatter.sh
	bin/test-check-inventory.sh
	bin/test-manifest-lib.sh
	bin/test-doctor.sh
	bin/test-notes-home.sh
	bin/test-nested-notes-guard.sh
	bin/test-session-context.sh
	bin/test-session-hooks.sh
	bin/test-install-session-hooks.sh
	bin/test-release-manifest.sh
```

- [ ] **Step 4: Run `make test` and confirm the new test executes**

```bash
make test 2>&1 | tail -20
```

Expected: `bin/test-release-manifest.sh` runs as part of the list and ends
with `release-manifest tests: N passed, 0 failed`; overall `make test`
still exits 0.

- [ ] **Step 5: Sanity-check the wiring without cutting a real release**

Run the two new `bin/release.sh` lines by hand against the real repo (read
current `VERSION` first so the values are realistic; do NOT actually run
`bin/release.sh` in this task — that's deferred to Task 5's final
verification, after everything else is in place):

```bash
cur="$(cat VERSION)"
python3 bin/release-manifest.py --version "$cur" --previous "$cur" --verify-determinism
python3 bin/release-manifest.py --version "$cur" --previous "$cur" --emit -
```

Expected: `verify-determinism` prints "release manifest generation is
deterministic" and exits 0; `--emit -` prints a full JSON manifest for the
current repo state to stdout (using `$cur` for both version and previous is
fine here — this is a syntax/wiring smoke test, not a real release; it will
work because `CHANGELOG.md`'s current `## [0.3.0]` section exists).

- [ ] **Step 6: Commit**

```bash
git add bin/release.sh Makefile
git commit -m "feat: wire bin/release-manifest.py into bin/release.sh (#33)"
```

---

### Task 3: Documentation, capability-inventory classification, CHANGELOG

**Files:**
- Create: `docs/release-manifest.md`
- Modify: `README.md` (the `## Versioning` section, currently lines 205–209)
- Modify: `CONTRIBUTING.md` (the `## Versioning & release` section, currently
  lines 69–74)
- Modify: `capabilities.json` (one `not_a_capability` ledger entry for
  `bin/release-manifest.py`; one `contract`-type capability row for
  `docs/release-manifest.md`)
- Modify: `CHANGELOG.md` (`## [Unreleased]` section)

**Interfaces:**
- None new — this task only adds documentation and inventory classification
  for artifacts Tasks 1–2 already created.

- [ ] **Step 1: Write `docs/release-manifest.md`**

```markdown
# Release manifest

**Status:** Contract, v1 · **Issue:** [thomas-estep/bindle#33](https://github.com/thomas-estep/bindle/issues/33)

Every real `bin/release.sh` run produces `RELEASE-MANIFEST.json` at the repo
root, committed alongside `VERSION` and `CHANGELOG.md` in the same
`Release vX.Y.Z` commit — a self-contained, provenance-rich record of what
that release actually shipped. It is generated by `bin/release-manifest.py`
(stdlib-only Python) from `capabilities.json` and `install-manifest.tsv`;
nothing in it is hand-duplicated.

## Schema

| Field | Meaning |
|---|---|
| `generated_by` | Fixed string identifying the generator; a reminder not to hand-edit the file. |
| `version` | The version this release bumped to. |
| `previous_version` | The version before this release's bump. |
| `commit_sha` | `git rev-parse HEAD` at manifest-generation time — the parent commit, immediately before the release commit that carries this file (that commit's own SHA doesn't exist yet when the manifest is generated). |
| `timestamp` | UTC ISO-8601 generation time. The one field excluded from the determinism guarantee below. |
| `changelog` | The literal `CHANGELOG.md` section text for this release (from its `## [version]` header to the next one). |
| `capabilities` | A snapshot projected from `capabilities.json`: `name`, `type`, `provider`, `maturity`, `version_introduced` for every capability, sorted by name. |
| `installed_surfaces` | The provider-specific install rows from `install-manifest.tsv` (`provider`, `category`, `name`, `src`, `dest`), sorted by `(provider, category, name)`. |
| `verification` | The commands `bin/release.sh` already ran before generating the manifest (`bin/check.sh`, `bin/test-install.sh`) and their exit codes. By construction these are always `0` — `bin/release.sh` runs under `set -euo pipefail` and would have aborted before reaching this step otherwise. |
| `tool_versions` | Raw, trimmed `<tool> --version` output for `git`, `bash`, `python3`, `shellcheck`, `shfmt`. An optional tool absent from `PATH` reports `"not installed"` rather than failing generation. |
| `self_checksum` | `sha256:<hex>` over the manifest's canonical JSON with `self_checksum` and `timestamp` excluded from the hashed content — a plain content hash for tamper-evidence if the file is copied elsewhere, not a signature. No keys or identities are involved. |

## Determinism

Every field except `timestamp` must be a pure function of repo state at
generation time. `bin/release.sh` proves this on every real release by
running `bin/release-manifest.py --verify-determinism` (which generates the
manifest twice internally and diffs every field but `timestamp`) before
writing or committing anything — a real mismatch aborts the release. This is
the mechanical answer to "a release fails if the manifest cannot be
generated consistently."

`RELEASE-MANIFEST.json` is **not** drift-checked by `make check` against the
current repo state the way `install-manifest.tsv` is. It's a point-in-time
record of a *past* release — it is expected to differ from a fresh
regeneration the moment any commit lands after the release it documents.

## Inspecting and verifying a release

1. Read the file directly — it's self-contained; you don't need to check
   out the release commit's `capabilities.json`/`install-manifest.tsv`
   separately to see what shipped.
2. To confirm it hasn't been altered since generation, recompute the
   checksum the same way the generator does — canonical JSON (sorted keys,
   `:`/`,` separators, no extra whitespace) of every field except
   `self_checksum` and `timestamp`, SHA256-hashed:

   ```bash
   python3 - <<'PY'
   import json, hashlib
   m = json.load(open("RELEASE-MANIFEST.json"))
   trimmed = {k: v for k, v in m.items() if k not in ("self_checksum", "timestamp")}
   canon = json.dumps(trimmed, sort_keys=True, separators=(",", ":"))
   print("sha256:" + hashlib.sha256(canon.encode()).hexdigest())
   PY
   ```

   Compare the output to the file's own `self_checksum` field — a mismatch
   means the content changed after generation.
3. To regenerate a manifest for inspection without cutting a release, run
   `bin/release-manifest.py --version V --previous V --emit -` directly.

## Non-goals

- No artifact signing or provenance attestations — `self_checksum` is a
  plain hash, not a signature; no signing model exists yet.
- No automatic publishing of GitHub releases.
- No capability-level diff between releases (added/removed/changed-maturity
  capabilities) — the manifest embeds a snapshot, not a diff. A diffing
  follow-up is possible once a second manifest exists to diff against.
```

- [ ] **Step 2: Cross-link from `README.md`**

Current (`README.md` lines 205–209):

```markdown
## Versioning

Bindle is versioned as a whole with Semantic Versioning. The current version
lives in `VERSION`, and `bin/release.sh` cuts an annotated local tag. It never
pushes.
```

New:

```markdown
## Versioning

Bindle is versioned as a whole with Semantic Versioning. The current version
lives in `VERSION`, and `bin/release.sh` cuts an annotated local tag. It never
pushes. Every release also produces a deterministic, provenance-rich
manifest recording exactly what shipped — see
`docs/release-manifest.md`.
```

(Write a real markdown link to `docs/release-manifest.md` into `README.md`
itself — this plan quotes it bare only so `bin/check.sh`'s link scanner,
which doesn't skip fenced code blocks, doesn't misread this plan file's own
illustrative quote as one of its outgoing links.)

- [ ] **Step 3: Cross-link from `CONTRIBUTING.md`**

Current (`CONTRIBUTING.md` lines 69–74):

```markdown
## Versioning & release

Toolkit-level SemVer (see the README): a new skill/agent/command is a **minor**
bump. Jot changes under `## [Unreleased]` in `CHANGELOG.md` as you
go; `bin/release.sh` cuts the release (and never pushes — you review first).
```

New:

```markdown
## Versioning & release

Toolkit-level SemVer (see the README): a new skill/agent/command is a **minor**
bump. Jot changes under `## [Unreleased]` in `CHANGELOG.md` as you
go; `bin/release.sh` cuts the release (and never pushes — you review first),
producing a deterministic manifest of what shipped — see
`docs/release-manifest.md`.
```

(Same note as Step 2: write the real markdown links into `CONTRIBUTING.md`
itself; this plan quotes them bare only to stay clean of the link scanner.)

- [ ] **Step 4: Classify `bin/release-manifest.py` in `capabilities.json`**

Find the existing ledger entry for `bin/release.sh` (in the `not_a_capability`
array):

```json
    {
      "path": "bin/release.sh",
      "reason": "rolls the Unreleased CHANGELOG section into a dated version and bumps VERSION; release machinery, not a capability."
    },
```

Add a new entry immediately after it:

```json
    {
      "path": "bin/release.sh",
      "reason": "rolls the Unreleased CHANGELOG section into a dated version and bumps VERSION; release machinery, not a capability."
    },
    {
      "path": "bin/release-manifest.py",
      "reason": "the release-manifest generator itself; machinery invoked by bin/release.sh, not a capability an agent invokes for its own sake (same precedent as bin/check-inventory.py)."
    },
```

- [ ] **Step 5: Add a `capabilities.json` row for `docs/release-manifest.md`**

Find the existing row for `docs/capability-inventory.md` in the
`capabilities` array (it has `"name": "capability-inventory"`) and add a new
object immediately after its closing `}`:

```json
    {
      "name": "release-manifest",
      "type": "contract",
      "path": "docs/release-manifest.md",
      "description": "The schema reference and \"how do I inspect/verify a release\" guide for RELEASE-MANIFEST.json, generated by bin/release-manifest.py from capabilities.json/install-manifest.tsv at release time (issue #33).",
      "provider": {
        "claude": "manual",
        "codex": "manual"
      },
      "maturity": "documented",
      "mutation": [],
      "version_introduced": "0.4.0"
    },
```

(Match the existing file's exact indentation — 2 spaces per level, as shown
in the `capability-inventory` row read earlier in this session.)

- [ ] **Step 6: Add a `CHANGELOG.md` Unreleased entry**

Under the existing `## [Unreleased]` / `### Added` section, add:

```markdown
- `bin/release-manifest.py` + `RELEASE-MANIFEST.json`: `bin/release.sh` now
  produces a deterministic, provenance-rich manifest for every release —
  commit, capability inventory snapshot, installed surfaces, verification
  results, tool versions, and this release's changelog range — drawn from
  `capabilities.json`/`install-manifest.tsv`, never hand-duplicated. The
  release aborts before committing if the manifest can't be regenerated
  consistently. See `docs/release-manifest.md` (issue #33).
```

- [ ] **Step 7: Run `make check` and fix anything it flags**

```bash
make check
```

Expected: all checks pass, including "capability inventory:" (bijection/
ledger/links) and "links:" (the two new `docs/release-manifest.md`
cross-links must resolve). If `capability inventory` fails on schema
validation, re-check the new row/ledger-entry JSON against
`docs/capability-inventory.md`'s field table (read earlier this session) —
common mistakes: wrong `type` enum, `version_introduced` not `<=` the next
allowed release version, missing required field.

- [ ] **Step 8: Commit**

```bash
git add docs/release-manifest.md README.md CONTRIBUTING.md capabilities.json CHANGELOG.md
git commit -m "docs: add release-manifest doc, classify in capabilities.json (#33)"
```

---

### Task 4: Correct `docs/product-boundary.md`'s stale "Later" triage

**Files:**
- Modify: `docs/product-boundary.md`

**Interfaces:** None — documentation-only correction, independent of Tasks
1–3's code changes (can be reviewed/rejected on its own).

This corrects the scope-gate conflict identified before implementation
started: the doc's 2026-07-10 triage classified #33 (and #29, since shipped)
as **Later**, gated on "a consumer materializes for a manifest." `bin/doctor.sh`
now reads `install-manifest.tsv` (generated from `capabilities.json`) via
`bin/lib/manifest.sh` — exactly that trigger, already fired but not yet
reflected in the doc, per the doc's own "revise this document in its own PR
with the evidence cited" rule.

- [ ] **Step 1: Remove the shipped `#29` bullet and the `#33` bullet from "Later"**

Current (`docs/product-boundary.md`, in the `**Later:**` section):

```markdown
**Later:**

- **#29** capability inventory — schema with no present consumer; unlocks
  when #28's `--json` or #33 needs it and the capability set is stable.
  Population is delegable once the schema is set. Verify: CI validates
  referenced paths; one manual table generated from it.
- **#33** release manifest — depends on #29; valuable once releases have
  consumers beyond the owner. Partially delegable. Verify: deterministic
  output, fails on inconsistency.
- **#11** spec-captain — fits the portable-workflow pattern but is a
```

New (delete the `#29` and `#33` bullets, keep everything else — `#11`
onward unchanged):

```markdown
**Later:**

- **#11** spec-captain — fits the portable-workflow pattern but is a
```

- [ ] **Step 2: Add `#33` to the "Next (v0.4 window)" section**

Current (`docs/product-boundary.md`, end of the `**Next (v0.4 window):**`
section):

```markdown
- **#7** first agent — the surface exists with only a template; admission
  criteria apply: needs a friction-justified candidate, enters as draft.
  Choice not delegable; drafting partially. Verify: pressure-tested or
  marked draft.

**Later:**
```

New:

```markdown
- **#7** first agent — the surface exists with only a template; admission
  criteria apply: needs a friction-justified candidate, enters as draft.
  Choice not delegable; drafting partially. Verify: pressure-tested or
  marked draft.
- **#33** release manifest — promoted out of Later (2026-07-12): the
  "consumer materializes" trigger below has fired (`bin/doctor.sh` now
  reads machine-readable capability data via `install-manifest.tsv`,
  generated from `capabilities.json`). #29, its other prerequisite, has
  shipped. Partially delegable. Verify: `bin/release.sh` regenerates and
  diffs the manifest before committing, fails the release on inconsistency.

**Later:**
```

- [ ] **Step 3: Mark the fired trigger**

Current (`docs/product-boundary.md`, in the Triggers section):

```markdown
- **A consumer materializes for a manifest** (dashboard, doctor, or an
  external tool needs machine-readable capability data) — unlocks #29/#33.
```

New:

```markdown
- **A consumer materializes for a manifest** (dashboard, doctor, or an
  external tool needs machine-readable capability data) — unlocks #29/#33.
  **Fired 2026-07-12:** `bin/doctor.sh` reads `install-manifest.tsv` via
  `bin/lib/manifest.sh`. #29 shipped; #33 moved to Next (see above).
```

- [ ] **Step 4: Run `make check`**

```bash
make check
```

Expected: passes (this is a prose-only edit to an already-linked file; the
"links:" check should be unaffected since no links were added/removed).

- [ ] **Step 5: Commit**

```bash
git add docs/product-boundary.md
git commit -m "docs: correct product-boundary.md's stale Later triage for #29/#33"
```

---

### Task 5: Final verification and PR

**Files:** None new — verification only.

- [ ] **Step 1: Full local gate**

```bash
make check
make test
```

Expected: both exit 0. `make test`'s output must include
`bin/test-release-manifest.sh`'s `release-manifest tests: N passed, 0
failed` line.

- [ ] **Step 2: Reproduce CI exactly**

```bash
SKIP=no-commit-to-branch pre-commit run --all-files --show-diff-on-failure
```

Expected: all hooks pass (this matches `.github/workflows/ci.yml`'s single
job).

- [ ] **Step 3: Dry-run the real `bin/release-manifest.py` wiring end-to-end**

This does NOT cut a real release (no `bin/release.sh` invocation) — it just
confirms the exact commands `bin/release.sh` will run succeed against the
real repo, post all Task 1–4 changes:

```bash
cur="$(cat VERSION)"
python3 bin/release-manifest.py --version "$cur" --previous "$cur" --verify-determinism
python3 bin/release-manifest.py --version "$cur" --previous "$cur" --emit -
```

Expected: `verify-determinism` succeeds; `--emit -` prints a complete
manifest to stdout including the real `capabilities.json` snapshot (should
show 33+ capabilities: 32 existing + the new `docs/release-manifest.md`
contract row from Task 3) and real `tool_versions`.

- [ ] **Step 4: git status sanity check**

```bash
git status
git log --oneline main..HEAD
```

Expected: working tree clean; the commit list shows exactly the 5 commits
from Tasks 1–4 plus the earlier design-doc and this plan-doc commits (7
total) — no stray untracked files (per this repo's own recorded lesson:
plan/design docs have twice been left uncommitted until right before PR
creation; this plan's own commit already happened, per the brainstorming
step, immediately after writing it — confirm it's still there).

- [ ] **Step 5: Open the PR** (only after explicit go-ahead — this repo
      never pushes without the operator asking)

Once the user confirms, push the branch and open a PR closing #33:

```bash
git push -u origin feature/33-release-manifest
gh pr create --title "Add a release manifest with provenance (#33)" --body "$(cat <<'EOF'
## Summary
- `bin/release.sh` now produces `RELEASE-MANIFEST.json` (commit, capability
  snapshot, installed surfaces, verification results, tool versions,
  changelog range) as an additive step, aborting before commit if the
  manifest can't be regenerated deterministically.
- New `bin/release-manifest.py` (stdlib-only) + `bin/test-release-manifest.sh`.
- New `docs/release-manifest.md`; cross-linked from README/CONTRIBUTING.
- Corrects `docs/product-boundary.md`'s stale "Later" triage for #29/#33 —
  the doctor.sh consumer trigger has fired.

Closes #33.

## Test plan
- [x] `make check` green
- [x] `make test` green (includes new `bin/test-release-manifest.sh`)
- [x] `SKIP=no-commit-to-branch pre-commit run --all-files --show-diff-on-failure` green
- [x] Dry-run of `bin/release-manifest.py --verify-determinism` / `--emit -`
      against the real repo

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
