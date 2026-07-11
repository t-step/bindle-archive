# Capability Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hand-authored `capabilities.json` inventory plus a stdlib-Python CI validator that keeps it reconciled with the actual Bindle repository.

**Architecture:** One authored JSON file (`capabilities.json`) is the source of truth for non-derivable metadata (provider, maturity, mutation, version). `bin/check-inventory.py` (Python 3, stdlib-only) validates it against the filesystem: schema + enums, completeness (bijection for skills/commands/agents/global-guidance, a `not_a_capability` classified ledger for scripts/contracts), path existence, frontmatter/maturity cross-checks, and a drift check against `docs/skill-portability-audit.md`. `check.sh` runs the validator; `new.sh` appends a stub row on scaffold.

**Tech Stack:** Bash (bash-3.2-compatible), Python 3 stdlib, JSON, git.

## Global Constraints

- **Branch:** `feature/29-capability-inventory` (already created and holding the design spec).
- **Python:** Python 3 **stdlib-only** — no `pip install`, no third-party imports. Degrade gracefully if `python3` is absent (skip with a notice, exactly like the existing `skill-scripts` section).
- **Shell:** bash-3.2-compatible (macOS default); new `*.sh` must pass `shellcheck` and `shfmt -i 2 -ci`.
- **Format:** the inventory is JSON at repo root: `capabilities.json`.
- **Frontmatter is off-limits:** never add fields to any `skills/*/SKILL.md`, `commands/*.md`, or `agents/*.md` frontmatter (Phase-1 rule). All metadata lives in `capabilities.json`.
- **Verify before commit:** `make check` must pass before each commit; never `--no-verify`.
- **Commits:** conventional (`feat:`, `test:`, `docs:`, `chore:`); each commit ends with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Enums (canonical values, copy verbatim):**
  - `type`: `skill · command · agent · global-guidance · script · contract`
  - `provider.{claude,codex}`: `installed · manual · untested · unsupported · n/a`
  - `maturity`: `draft · documented · tested`
  - `mutation`: subset of `{disk, network, external}` (`[]` = read-only)

---

### Task 1: Validator skeleton — load + schema/enum validation

**Files:**
- Create: `bin/check-inventory.py`
- Create/Test: `bin/test-check-inventory.sh`

**Interfaces:**
- Produces: `load_inventory(root) -> (caps: list, ledger: list)` (raises `ValueError` with a message); `read_version(root) -> str`; `check_schema(caps, version) -> list[str]`; `main(argv=None) -> int`. Every check function returns a list of error strings; `main` aggregates, prints one per line, exits `1` if any, else prints a one-line OK and exits `0`. Later tasks add `check_*` functions and one `errors += ...` line each in `main`.

- [ ] **Step 1: Write the failing test** — create `bin/test-check-inventory.sh` with a fixture builder and the first assertions:

```bash
#!/usr/bin/env bash
#
# test-check-inventory.sh — exercise bin/check-inventory.py against throwaway
# fixture repos. The validator takes --root, so each test builds a tiny fake
# Bindle repo and points the validator at it. Nothing touches this repo.
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="$REPO_ROOT/bin/check-inventory.py"

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

# mkfixture DIR — a minimal, fully VALID fixture repo the validator passes.
# Individual tests copy it and perturb one thing.
mkfixture() {
  local r="$1"
  mkdir -p "$r/skills/demo" "$r/commands" "$r/global" "$r/docs"
  printf '0.3.0\n' >"$r/VERSION"
  printf -- '---\nname: demo\ndescription: Demo skill.\n---\n# demo\n' >"$r/skills/demo/SKILL.md"
  printf 'tested\n' >"$r/skills/demo/PRESSURE-TESTS.md"
  printf -- '---\ndescription: Demo command.\n---\n# foo\n' >"$r/commands/foo.md"
  printf '# claude\n' >"$r/global/CLAUDE.md"
  printf '# agents\n' >"$r/global/AGENTS.md"
  printf '## Audit\n\n| Skill | X |\n|---|---|\n| `demo` | ok |\n' >"$r/docs/skill-portability-audit.md"
  cat >"$r/capabilities.json" <<'JSON'
{
  "capabilities": [
    {"name": "demo", "type": "skill", "path": "skills/demo",
     "description": "Demo skill.",
     "provider": {"claude": "installed", "codex": "untested"},
     "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "foo", "type": "command", "path": "commands/foo.md",
     "description": "Demo command.",
     "provider": {"claude": "installed", "codex": "unsupported"},
     "maturity": "documented", "mutation": ["disk"], "version_introduced": "0.1.0"},
    {"name": "claude", "type": "global-guidance", "path": "global/CLAUDE.md",
     "description": "Global Claude guidance.",
     "provider": {"claude": "installed", "codex": "n/a"},
     "maturity": "documented", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "agents", "type": "global-guidance", "path": "global/AGENTS.md",
     "description": "Global Codex guidance.",
     "provider": {"claude": "n/a", "codex": "manual"},
     "maturity": "documented", "mutation": [], "version_introduced": "0.1.0"}
  ],
  "not_a_capability": [
    {"path": "docs/skill-portability-audit.md", "reason": "audit doc, not a shipped capability"}
  ]
}
JSON
  (cd "$r" && git init -q && git symbolic-ref HEAD refs/heads/main &&
    git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m init)
}

echo "valid fixture passes:"
REPO="$TMP/ok"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "valid inventory exits 0" test "$status" -eq 0
check "reports the capability count" contains "capability inventory OK" "$out"

echo "schema violations are caught:"
REPO="$TMP/bad-enum"
mkfixture "$REPO"
# break the maturity enum on the demo skill
sed -i.bak 's/"maturity": "tested"/"maturity": "bogus"/' "$REPO/capabilities.json"
rm -f "$REPO/capabilities.json.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "invalid maturity exits nonzero" test "$status" -ne 0
check "names the bad maturity value" contains "invalid maturity 'bogus'" "$out"

REPO="$TMP/bad-json"
mkfixture "$REPO"
printf 'not json\n' >"$REPO/capabilities.json"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "invalid JSON is reported cleanly" contains "invalid JSON" "$out"

echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
```

Make it executable:

```bash
chmod +x bin/test-check-inventory.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — `python3: can't open file '.../bin/check-inventory.py'` (validator doesn't exist yet), assertions fail.

- [ ] **Step 3: Write minimal implementation** — create `bin/check-inventory.py`:

```python
#!/usr/bin/env python3
"""Validate capabilities.json against the Bindle repo. Stdlib-only.

Usage: check-inventory.py [--root DIR]
Exits 0 if the inventory is consistent, 1 (with per-line diagnostics) otherwise.
"""
import argparse
import json
import os
import re
import sys

TYPES = {"skill", "command", "agent", "global-guidance", "script", "contract"}
PROVIDER_STATUS = {"installed", "manual", "untested", "unsupported", "n/a"}
MATURITY = {"draft", "documented", "tested"}
MUTATION_FLAGS = {"disk", "network", "external"}
REQUIRED = ["name", "type", "path", "description", "provider", "maturity",
            "mutation", "version_introduced"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load_inventory(root):
    path = os.path.join(root, "capabilities.json")
    if not os.path.isfile(path):
        raise ValueError("capabilities.json: missing at repo root")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError("capabilities.json: invalid JSON (%s)" % exc)
    if not isinstance(data, dict):
        raise ValueError("capabilities.json: top level must be an object")
    caps = data.get("capabilities")
    ledger = data.get("not_a_capability", [])
    if not isinstance(caps, list):
        raise ValueError("capabilities.json: 'capabilities' must be an array")
    if not isinstance(ledger, list):
        raise ValueError("capabilities.json: 'not_a_capability' must be an array")
    return caps, ledger


def read_version(root):
    with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
        return fh.read().strip()


def _semver_tuple(v):
    return tuple(int(x) for x in v.split("."))


def check_schema(caps, version):
    errors = []
    seen = set()
    for i, cap in enumerate(caps):
        label = cap.get("name", "<row %d>" % i)
        for field in REQUIRED:
            if field not in cap:
                errors.append("%s: missing required field '%s'" % (label, field))
        if cap.get("type") not in TYPES:
            errors.append("%s: invalid type '%s'" % (label, cap.get("type")))
        key = (cap.get("type"), cap.get("name"))
        if key in seen:
            errors.append("%s: duplicate (type, name) %s" % (label, key))
        seen.add(key)
        prov = cap.get("provider")
        if isinstance(prov, dict):
            for p in ("claude", "codex"):
                if prov.get(p) not in PROVIDER_STATUS:
                    errors.append("%s: provider.%s '%s' not in %s"
                                  % (label, p, prov.get(p), sorted(PROVIDER_STATUS)))
        else:
            errors.append("%s: provider must be an object with claude+codex" % label)
        if cap.get("maturity") not in MATURITY:
            errors.append("%s: invalid maturity '%s'" % (label, cap.get("maturity")))
        mut = cap.get("mutation")
        if not isinstance(mut, list) or any(m not in MUTATION_FLAGS for m in mut):
            errors.append("%s: mutation must be a subset of %s"
                          % (label, sorted(MUTATION_FLAGS)))
        vi = str(cap.get("version_introduced", ""))
        if not SEMVER.match(vi):
            errors.append("%s: version_introduced '%s' is not semver" % (label, vi))
        elif _semver_tuple(vi) > _semver_tuple(version):
            errors.append("%s: version_introduced %s is ahead of VERSION %s"
                          % (label, vi, version))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        caps, ledger = load_inventory(root)
        version = read_version(root)
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1
    errors = []
    errors += check_schema(caps, version)
    # NOTE: later tasks append more checks here.
    if errors:
        for e in errors:
            print(e)
        return 1
    print("capability inventory OK (%d capabilities, %d ledgered exclusions)"
          % (len(caps), len(ledger)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Make it executable:

```bash
chmod +x bin/check-inventory.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — `tests: 5 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add bin/check-inventory.py bin/test-check-inventory.sh
git commit -m "feat: capability-inventory validator skeleton (schema + enums)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Completeness — bijection for clean types

**Files:**
- Modify: `bin/check-inventory.py`
- Modify: `bin/test-check-inventory.sh`

**Interfaces:**
- Consumes: `caps` list from Task 1.
- Produces: `check_completeness_clean(caps, root) -> list[str]` and helper `_bijection(type_name, inventory_names, fs_names) -> list[str]`.

- [ ] **Step 1: Write the failing test** — append to `bin/test-check-inventory.sh` before the final result block:

```bash
echo "clean-type bijection:"
REPO="$TMP/missing-skill"
mkfixture "$REPO"
mkdir -p "$REPO/skills/extra"
printf -- '---\nname: extra\ndescription: Extra.\n---\n# extra\n' >"$REPO/skills/extra/SKILL.md"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m extra)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "on-disk skill absent from inventory fails" contains "skill 'extra' exists on disk but is missing from the inventory" "$out"

REPO="$TMP/phantom-skill"
mkfixture "$REPO"
sed -i.bak 's/"name": "demo", "type": "skill"/"name": "ghost", "type": "skill"/' "$REPO/capabilities.json"
rm -f "$REPO/capabilities.json.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "inventory skill absent from disk fails" contains "skill 'ghost' is in the inventory but not found on disk" "$out"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — the two new assertions fail (no bijection check yet).

- [ ] **Step 3: Write minimal implementation** — add to `bin/check-inventory.py` (above `main`):

```python
def _bijection(type_name, inventory_names, fs_names):
    errors = []
    for missing in sorted(fs_names - inventory_names):
        errors.append("%s '%s' exists on disk but is missing from the inventory"
                      % (type_name, missing))
    for extra in sorted(inventory_names - fs_names):
        errors.append("%s '%s' is in the inventory but not found on disk"
                      % (type_name, extra))
    return errors


def check_completeness_clean(caps, root):
    errors = []

    def names_of(t):
        return {c.get("name") for c in caps if c.get("type") == t}

    fs_skills = set()
    skills_dir = os.path.join(root, "skills")
    if os.path.isdir(skills_dir):
        for entry in os.listdir(skills_dir):
            if entry.startswith(("_", ".")):
                continue
            if os.path.isfile(os.path.join(skills_dir, entry, "SKILL.md")):
                fs_skills.add(entry)
    errors += _bijection("skill", names_of("skill"), fs_skills)

    for t, d in (("command", "commands"), ("agent", "agents")):
        fs = set()
        dd = os.path.join(root, d)
        if os.path.isdir(dd):
            for entry in os.listdir(dd):
                if entry.startswith(("_", ".")) or not entry.endswith(".md"):
                    continue
                fs.add(entry[:-3])
        errors += _bijection(t, names_of(t), fs)

    gg = {"claude": "global/CLAUDE.md", "agents": "global/AGENTS.md"}
    fs_gg = {label for label, rel in gg.items()
             if os.path.isfile(os.path.join(root, rel))}
    errors += _bijection("global-guidance", names_of("global-guidance"), fs_gg)
    return errors
```

Then add to `main`, right after the `check_schema` line:

```python
    errors += check_completeness_clean(caps, root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — `tests: 7 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add bin/check-inventory.py bin/test-check-inventory.sh
git commit -m "feat: bijection completeness check for clean capability types

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Completeness — classified ledger for fuzzy types

**Files:**
- Modify: `bin/check-inventory.py`
- Modify: `bin/test-check-inventory.sh`

**Interfaces:**
- Consumes: `caps`, `ledger` from Task 1.
- Produces: `check_completeness_fuzzy(caps, ledger, root) -> list[str]`, helper `_tracked_under(root, subdir) -> list[str]`, and module constant `AUTO_EXCLUDE`.

- [ ] **Step 1: Write the failing test** — append to `bin/test-check-inventory.sh`:

```bash
echo "fuzzy-type classified ledger:"
REPO="$TMP/unclassified-script"
mkfixture "$REPO"
mkdir -p "$REPO/bin"
printf '#!/usr/bin/env bash\necho hi\n' >"$REPO/bin/thing.sh"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m thing)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "unclassified bin script fails" contains "bin/thing.sh: unclassified" "$out"

REPO="$TMP/auto-excluded"
mkfixture "$REPO"
mkdir -p "$REPO/bin"
printf '#!/usr/bin/env bash\necho hi\n' >"$REPO/bin/test-thing.sh"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m testthing)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "bin/test-*.sh is auto-excluded (still passes)" test "$status" -eq 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — `bin/thing.sh: unclassified` not present (no fuzzy check yet); the auto-excluded case may already pass.

- [ ] **Step 3: Write minimal implementation** — add to `bin/check-inventory.py` (add `import subprocess` at the top with the other imports):

```python
AUTO_EXCLUDE = [
    re.compile(r"^bin/test-.*\.sh$"),   # the test harness, never a capability
    re.compile(r"^docs/design/"),       # design specs
    re.compile(r"^docs/plans/"),        # implementation plans
]


def _tracked_under(root, subdir):
    """Tracked files under subdir (via git), so untracked scratch never trips
    the check. Returns [] if git is unavailable."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", subdir],
                             capture_output=True, text=True, check=True)
        return [line for line in out.stdout.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        return []


def check_completeness_fuzzy(caps, ledger, root):
    errors = []
    inv_paths = {c.get("path") for c in caps
                 if c.get("type") in ("script", "contract")}
    led_paths = {e.get("path") for e in ledger}
    candidates = [p for p in _tracked_under(root, "bin") if p.endswith(".sh")]
    candidates += [p for p in _tracked_under(root, "docs") if p.endswith(".md")]
    for path in sorted(set(candidates)):
        if any(rx.search(path) for rx in AUTO_EXCLUDE):
            continue
        if path in inv_paths or path in led_paths:
            continue
        errors.append("%s: unclassified — add it to the inventory (type "
                      "script/contract) or to not_a_capability with a reason" % path)
    return errors
```

Then add to `main`, after the `check_completeness_clean` line:

```python
    errors += check_completeness_fuzzy(caps, ledger, root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — `tests: 9 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add bin/check-inventory.py bin/test-check-inventory.sh
git commit -m "feat: classified-ledger completeness check for fuzzy capability types

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Path existence + frontmatter/maturity cross-checks

**Files:**
- Modify: `bin/check-inventory.py`
- Modify: `bin/test-check-inventory.sh`

**Interfaces:**
- Consumes: `caps` from Task 1.
- Produces: `check_paths(caps, root) -> list[str]`, `check_crosschecks(caps, root) -> list[str]`, helpers `_read_fm_value(path, key) -> str | None` and `_frontmatter_description(root, cap) -> str | None`.

- [ ] **Step 1: Write the failing test** — append to `bin/test-check-inventory.sh`:

```bash
echo "path existence + cross-checks:"
REPO="$TMP/dead-path"
mkfixture "$REPO"
sed -i.bak 's#"path": "commands/foo.md"#"path": "commands/gone.md"#' "$REPO/capabilities.json"
rm -f "$REPO/capabilities.json.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "a dead path is reported" contains "path 'commands/gone.md' does not exist" "$out"

REPO="$TMP/desc-drift"
mkfixture "$REPO"
sed -i.bak 's/"description": "Demo skill."/"description": "Wrong."/' "$REPO/capabilities.json"
rm -f "$REPO/capabilities.json.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "description drift vs frontmatter is caught" contains "description does not match skill frontmatter" "$out"

REPO="$TMP/tested-no-pt"
mkfixture "$REPO"
rm -f "$REPO/skills/demo/PRESSURE-TESTS.md"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m rmpt)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "tested skill without PRESSURE-TESTS.md is caught" contains "maturity 'tested' but no PRESSURE-TESTS.md" "$out"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — the three new assertions fail (no path/cross-checks yet).

- [ ] **Step 3: Write minimal implementation** — add to `bin/check-inventory.py`:

```python
def check_paths(caps, root):
    errors = []
    for cap in caps:
        p = cap.get("path")
        if p and not os.path.exists(os.path.join(root, p)):
            errors.append("%s: path '%s' does not exist" % (cap.get("name"), p))
        for rel in cap.get("related_docs", []) or []:
            if not os.path.exists(os.path.join(root, rel)):
                errors.append("%s: related_docs '%s' does not exist"
                              % (cap.get("name"), rel))
    return errors


def _read_fm_value(path, key):
    """Read a single-line `key: value` from a leading --- frontmatter block."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^%s:\s*(.*)$" % re.escape(key), line)
        if m:
            return m.group(1).strip()
    return None


def _frontmatter_description(root, cap):
    t, p = cap.get("type"), cap.get("path")
    if t == "skill":
        f = os.path.join(root, p, "SKILL.md")
    elif t in ("command", "agent"):
        f = os.path.join(root, p)
    else:
        return None
    if not os.path.isfile(f):
        return None
    return _read_fm_value(f, "description")


def check_crosschecks(caps, root):
    errors = []
    for cap in caps:
        t = cap.get("type")
        if t in ("skill", "command", "agent"):
            fm = _frontmatter_description(root, cap)
            if fm is not None and fm != cap.get("description"):
                errors.append("%s: description does not match %s frontmatter"
                              % (cap.get("name"), t))
        if t == "skill" and cap.get("maturity") == "tested":
            pt = os.path.join(root, cap.get("path", ""), "PRESSURE-TESTS.md")
            if not os.path.isfile(pt):
                errors.append("%s: maturity 'tested' but no PRESSURE-TESTS.md"
                              % cap.get("name"))
    return errors
```

Then add to `main`, after the `check_completeness_fuzzy` line:

```python
    errors += check_paths(caps, root)
    errors += check_crosschecks(caps, root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — `tests: 12 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add bin/check-inventory.py bin/test-check-inventory.sh
git commit -m "feat: path-existence and frontmatter/maturity cross-checks

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Bound-table drift check (skill-portability-audit)

**Files:**
- Modify: `bin/check-inventory.py`
- Modify: `bin/test-check-inventory.sh`

**Interfaces:**
- Consumes: `caps` from Task 1.
- Produces: `check_bound_table(caps, root) -> list[str]`, helper `_audit_skill_names(path) -> set[str]`.

- [ ] **Step 1: Write the failing test** — append to `bin/test-check-inventory.sh`:

```bash
echo "bound-table drift (skill-portability-audit):"
REPO="$TMP/audit-drift"
mkfixture "$REPO"
# audit table lists demo; add a second skill to the inventory + disk but NOT the table
mkdir -p "$REPO/skills/second"
printf -- '---\nname: second\ndescription: Second.\n---\n# second\n' >"$REPO/skills/second/SKILL.md"
printf 'x\n' >"$REPO/skills/second/PRESSURE-TESTS.md"
# Author the inventory with `second` present (on disk + inventory) but NOT in
# the audit table, so only the bound-table drift check should fire.
cat >"$REPO/capabilities.json" <<'JSON'
{
  "capabilities": [
    {"name": "demo", "type": "skill", "path": "skills/demo", "description": "Demo skill.", "provider": {"claude": "installed", "codex": "untested"}, "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "second", "type": "skill", "path": "skills/second", "description": "Second.", "provider": {"claude": "installed", "codex": "untested"}, "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "foo", "type": "command", "path": "commands/foo.md", "description": "Demo command.", "provider": {"claude": "installed", "codex": "unsupported"}, "maturity": "documented", "mutation": ["disk"], "version_introduced": "0.1.0"},
    {"name": "claude", "type": "global-guidance", "path": "global/CLAUDE.md", "description": "Global Claude guidance.", "provider": {"claude": "installed", "codex": "n/a"}, "maturity": "documented", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "agents", "type": "global-guidance", "path": "global/AGENTS.md", "description": "Global Codex guidance.", "provider": {"claude": "n/a", "codex": "manual"}, "maturity": "documented", "mutation": [], "version_introduced": "0.1.0"}
  ],
  "not_a_capability": [
    {"path": "docs/skill-portability-audit.md", "reason": "audit doc"}
  ]
}
JSON
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m second)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "inventory skill absent from audit table is caught" contains "skill 'second' in inventory but not in skill-portability-audit table" "$out"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — the drift assertion fails (no bound-table check yet).

- [ ] **Step 3: Write minimal implementation** — add to `bin/check-inventory.py`:

```python
def _audit_skill_names(path):
    names = set()
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    in_table = False
    for line in lines:
        if line.strip().startswith("| Skill |"):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break
            cell = line.split("|")[1].strip().strip("`").strip()
            if not cell or set(cell) <= set("-: "):
                continue  # separator row (|---|)
            names.add(cell)
    return names


def check_bound_table(caps, root):
    errors = []
    audit = os.path.join(root, "docs/skill-portability-audit.md")
    if not os.path.isfile(audit):
        errors.append("docs/skill-portability-audit.md: missing (bound table for "
                      "criterion c)")
        return errors
    inv = {c.get("name") for c in caps if c.get("type") == "skill"}
    tbl = _audit_skill_names(audit)
    for missing in sorted(inv - tbl):
        errors.append("skill '%s' in inventory but not in skill-portability-audit "
                      "table" % missing)
    for extra in sorted(tbl - inv):
        errors.append("skill '%s' in skill-portability-audit table but not in "
                      "inventory" % extra)
    return errors
```

Then add to `main`, after the `check_crosschecks` line:

```python
    errors += check_bound_table(caps, root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — `tests: 13 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add bin/check-inventory.py bin/test-check-inventory.sh
git commit -m "feat: skill-portability-audit bound-table drift check

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Author the real `capabilities.json`

**Files:**
- Create: `capabilities.json`

**Interfaces:**
- Consumes: the complete validator (Tasks 1–5).
- Produces: `capabilities.json` at repo root that the validator passes against the real repo.

The validator IS the completeness spec here: author rows, run it, and fix every reported gap until it exits 0. Do not wire it into `check.sh` yet (Task 7) — until then, run it directly.

- [ ] **Step 1: Enumerate the current capabilities.** Author `capabilities.json` with a `capabilities` array and a `not_a_capability` ledger. Cover, at minimum:
  - **skills** (8): `fork-pr-flow`, `hands-on-keyboard`, `license-compliance-auditor`, `maintain-claude-md`, `repo-hygiene-init`, `scoped-sequential-prs`, `session-continuity`, `verify-then-commit`. Each: `type: skill`, `path: skills/<name>`, `description` copied **verbatim** from that skill's frontmatter, `provider.claude: installed`, `provider.codex` taken from `docs/skill-portability-audit.md`'s `X: Codex status` (use `manual` for shared-after-cleanup / doc-consumable, `unsupported` for blocked, `untested` if unknown), `maturity: tested` (all have `PRESSURE-TESTS.md`), `mutation` per what the skill does (e.g. `verify-then-commit` → `["disk"]`; read-only advisory skills → `[]`), `version_introduced` from the CHANGELOG (default `0.1.0` if it predates recorded history).
  - **commands** (8): `handoff`, `license-audit`, `notes-home`, `project-profile`, `promote-insight`, `session-end`, `session-start`, `workflow-review`. Each: `type: command`, `path: commands/<name>.md`, `description` verbatim from frontmatter, `maturity: documented` unless it has dedicated tests, `mutation` per behavior.
  - **global-guidance** (2): `claude` → `global/CLAUDE.md`, `agents` → `global/AGENTS.md`.
  - **scripts / contracts:** classify every `bin/*.sh` (minus `bin/test-*.sh`) and every `docs/**/*.md` (minus `docs/design/`, `docs/plans/`) as either a `script`/`contract` capability row **or** a `not_a_capability` ledger entry with a `reason`. Genuine capabilities (e.g. `bin/session-context.sh`, `bin/slugify.sh`, portable contract docs like `docs/session-notes-format.md`, `docs/hands-on-keyboard.md`, `docs/delegated-implementation-packets.md`) get rows; machinery (`bin/check.sh`, `bin/install.sh`, `bin/doctor.sh`, `bin/check-private-info.sh`, `bin/check-inventory.py` is `.py` so not a `bin/*.sh` candidate) and reference/prose docs get ledgered with a reason.

Row template (copy per capability, fill every field):

```json
{
  "name": "verify-then-commit",
  "type": "skill",
  "path": "skills/verify-then-commit",
  "description": "<verbatim frontmatter description>",
  "provider": {"claude": "installed", "codex": "manual"},
  "maturity": "tested",
  "mutation": ["disk"],
  "version_introduced": "0.1.0"
}
```

- [ ] **Step 2: Run the validator against the real repo**

Run: `python3 bin/check-inventory.py --root .`
Expected: iterate — it will print missing rows (skills/commands on disk not yet listed), unclassified `bin`/`docs` files, description drift (fix the row to match frontmatter verbatim), and audit-table drift. Fix `capabilities.json` until it prints `capability inventory OK (...)` and exits 0.

- [ ] **Step 3: Confirm the bound table agrees.** If the validator reports a `skill-portability-audit` drift, the audit table and the inventory disagree on the skill set. Reconcile by correcting `capabilities.json` (do **not** edit the audit table's skill rows unless a skill is genuinely missing from it).

- [ ] **Step 4: Commit**

```bash
git add capabilities.json
git commit -m "feat: author capabilities.json inventory for current assets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Wire the validator into `check.sh` and `make test`

**Files:**
- Modify: `bin/check.sh` (add a section after section 6, before section 7)
- Modify: `Makefile` (add `bin/test-check-inventory.sh` to the `test` target)

**Interfaces:**
- Consumes: `bin/check-inventory.py` (Task 1–5), `capabilities.json` (Task 6).

- [ ] **Step 1: Add the check.sh section.** Insert immediately before the `# --- 7. private info ---` block:

```bash
# --- 6b. capability inventory ----------------------------------------------
# Reconcile capabilities.json against the actual repo (bijection for clean
# types, classified ledger for scripts/contracts, path + cross-checks, and the
# skill-portability-audit drift check). Skipped with a notice if python3 is
# absent — CI enforces it.
echo "capability inventory:"
if [ ! -f capabilities.json ]; then
  problem "capabilities.json missing"
elif command -v python3 >/dev/null 2>&1; then
  if inv_out="$(python3 bin/check-inventory.py --root . 2>&1)"; then
    ok "$inv_out"
  else
    printf '%s\n' "$inv_out" | sed 's/^/  /'
    problem "capability inventory check failed (run: python3 bin/check-inventory.py)"
  fi
else
  echo "  - python3 not installed; skipping (CI enforces this)"
fi
```

- [ ] **Step 2: Run check.sh to verify it passes**

Run: `bin/check.sh`
Expected: a new `capability inventory:` section prints `✓ capability inventory OK (...)`, and the run ends `All checks passed.`

- [ ] **Step 3: Add the test to the Makefile `test` target.** In `Makefile`, add the line to the `test:` recipe (after `bin/test-check-frontmatter.sh`):

```makefile
	bin/test-check-inventory.sh
```

- [ ] **Step 4: Run the whole suite**

Run: `make test && make check`
Expected: `test-check-inventory.sh` runs green in the suite; `make check` prints `All checks passed.`

- [ ] **Step 5: Commit**

```bash
git add bin/check.sh Makefile
git commit -m "feat: run capability-inventory validator in check.sh and make test

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `new.sh` appends a stub inventory row

**Files:**
- Modify: `bin/new.sh`
- Modify: `bin/test-check-inventory.sh` (add a new.sh integration assertion)

**Interfaces:**
- Consumes: `capabilities.json` schema (Task 1), the validator (for the assertion).
- Produces: after `bin/new.sh skill|agent|command <name>`, a matching stub row exists in `capabilities.json` and the repo still validates.

A stub row must be a **valid** row so the bijection check stays green immediately after scaffolding: derived fields filled, metadata defaulted to safe placeholders the author later edits (`provider` both `untested`, `maturity: draft`, `mutation: []`, `version_introduced` = current `VERSION`, `description` copied from the freshly scaffolded frontmatter).

- [ ] **Step 1: Write the failing test** — append to `bin/test-check-inventory.sh`:

```bash
echo "new.sh appends a valid stub row:"
REPO="$TMP/newsh"
mkfixture "$REPO"
cp "$REPO_ROOT/bin/new.sh" "$REPO/bin/new.sh"
mkdir -p "$REPO/skills/_template"
printf -- '---\nname: Skill-Name\ndescription: Use when placeholder.\n---\n' >"$REPO/skills/_template/SKILL.md"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m tmpl)
(cd "$REPO" && bin/new.sh skill widget >/dev/null)
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m widget)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "repo still validates after new.sh skill" test "$status" -eq 0
check "stub row present for the new skill" contains '"name": "widget"' "$(cat "$REPO/capabilities.json")"
```

Note: the new skill `widget` also needs an audit-table row to satisfy the bound-table check. In the fixture, `new.sh` only appends to `capabilities.json`; to keep this test green, have `mkfixture`'s audit table include a `widget` row **or** relax the assertion to check the stub-append and validator-minus-bound-table. Simplest: extend the fixture's audit table before running the validator:

```bash
printf '| `widget` | ok |\n' >>"$REPO/docs/skill-portability-audit.md"
```

Insert that line before the `out=$(...)` capture.

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test-check-inventory.sh`
Expected: FAIL — `new.sh` does not touch `capabilities.json` yet, so the stub row is absent and the bijection check fails.

- [ ] **Step 3: Write minimal implementation** — in `bin/new.sh`, add a helper and call it. Add before the final two `echo` lines a function that appends a row, and invoke it for `skill`/`agent`/`command`. Insert this function after the `cd "$REPO_ROOT"` line:

```bash
# append_inventory_row TYPE NAME PATH SKILLFILE — add a valid stub row to
# capabilities.json (description copied verbatim from the scaffolded
# frontmatter). Uses python3 for safe JSON editing; no-op with a notice if
# python3 or capabilities.json is absent.
append_inventory_row() {
  local ctype="$1" cname="$2" cpath="$3" fmfile="$4"
  if [ ! -f capabilities.json ]; then
    echo "Note: capabilities.json not found; skipping inventory row." >&2
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Note: python3 absent; add the capabilities.json row by hand." >&2
    return 0
  fi
  local version
  version="$(cat VERSION 2>/dev/null || echo 0.0.0)"
  CAP_TYPE="$ctype" CAP_NAME="$cname" CAP_PATH="$cpath" \
    CAP_FM="$fmfile" CAP_VERSION="$version" python3 - <<'PY'
import json, os, re, sys
inv = "capabilities.json"
data = json.load(open(inv, encoding="utf-8"))
desc = ""
try:
    lines = open(os.environ["CAP_FM"], encoding="utf-8").read().splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            m = re.match(r"^description:\s*(.*)$", line)
            if m:
                desc = m.group(1).strip()
except OSError:
    pass
data.setdefault("capabilities", []).append({
    "name": os.environ["CAP_NAME"],
    "type": os.environ["CAP_TYPE"],
    "path": os.environ["CAP_PATH"],
    "description": desc,
    "provider": {"claude": "untested", "codex": "untested"},
    "maturity": "draft",
    "mutation": [],
    "version_introduced": os.environ["CAP_VERSION"],
})
with open(inv, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  echo "Added a draft capabilities.json row for $cname (fill in provider/maturity/mutation)."
}
```

Then call it at the end of each relevant `case` arm, just before the closing `;;`:

- `skill)` arm — after the `sed ... >"$dest"` line:
  ```bash
  append_inventory_row skill "$name" "skills/$name" "$dest"
  ```
- `agent)` arm — after its `sed ... >"$dest"` line:
  ```bash
  append_inventory_row agent "$name" "agents/$name.md" "$dest"
  ```
- `command)` arm — after its `cp ... "$dest"` line:
  ```bash
  append_inventory_row command "$name" "commands/$name.md" "$dest"
  ```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test-check-inventory.sh`
Expected: PASS — the stub-append assertions pass. Also run `make check` to confirm the real repo is still green (new.sh change is inert until used).

- [ ] **Step 5: Commit**

```bash
git add bin/new.sh bin/test-check-inventory.sh
git commit -m "feat: new.sh appends a draft capabilities.json row on scaffold

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Documentation

**Files:**
- Create: `docs/capability-inventory.md`
- Modify: `CONTRIBUTING.md` (add a pointer in the "before you call it done" checklist)
- Modify: `CHANGELOG.md` (add an `[Unreleased]` entry)

**Interfaces:** none (docs only).

- [ ] **Step 1: Write `docs/capability-inventory.md`.** Cover: what the inventory is; the schema (fields + enums, copied from the Global Constraints above); the completeness model (bijection vs. classified ledger, with the auto-exclude rules); how to add a capability — for skills/agents/commands, `bin/new.sh` appends a draft row you then fill in; for a new `bin/*.sh` or `docs/*.md`, either add a `script`/`contract` row or a `not_a_capability` entry with a reason, or CI fails; how to run it (`python3 bin/check-inventory.py` / `make check`). Note the deferred follow-ups (doc generation; installer consumption). Because this file lives at `docs/capability-inventory.md` (not under `docs/design/` or `docs/plans/`), it is itself a `docs/*.md` candidate — classify it in `capabilities.json` as a `contract` row (it is the inventory's normative contract) in this step and re-run the validator.

- [ ] **Step 2: Add the CONTRIBUTING pointer.** In `CONTRIBUTING.md`, under "Before you call it done", add a checklist line that links to `docs/capability-inventory.md` (write it as a real markdown link there — it is omitted here so this plan doesn't reference a file that doesn't exist yet). The line reads: "New/renamed capability recorded in `capabilities.json` (see the capability-inventory doc); `make check` reconciles it."

- [ ] **Step 3: Add the CHANGELOG entry.** Under `## [Unreleased]`, add an `### Added` item (create the subsection if absent):

```markdown
- `capabilities.json` + `bin/check-inventory.py` (issue #29): a machine-readable
  capability inventory reconciled against the repo by CI — bijection for
  skills/commands/agents/global-guidance, a `not_a_capability` classified ledger
  for scripts/contracts, path + frontmatter/maturity cross-checks, and a
  `skill-portability-audit.md` drift check. `bin/new.sh` appends a draft row on
  scaffold. See `docs/capability-inventory.md`. Doc generation and installer
  consumption are deferred follow-ups.
```

- [ ] **Step 4: Verify and commit**

Run: `make check && make test`
Expected: `All checks passed.` and the full test suite green (including the new `contract` row for `docs/capability-inventory.md`).

```bash
git add docs/capability-inventory.md CONTRIBUTING.md CHANGELOG.md capabilities.json
git commit -m "docs: capability-inventory guide, CONTRIBUTING pointer, CHANGELOG

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **Order matters:** Tasks 1–5 build the validator against fixtures (independent of the real `capabilities.json`). Task 6 authors the real inventory. Only Task 7 wires the validator into `check.sh` — so intermediate commits never break `make check`.
- **The validator is the completeness oracle:** in Task 6 and Task 9, run `python3 bin/check-inventory.py --root .` and let its diagnostics drive what to add/classify. Don't hand-guess completeness.
- **Frontmatter stays untouched:** the description cross-check pulls from frontmatter; if it drifts, fix the *inventory row*, never the SKILL.md frontmatter.
- **shellcheck/shfmt:** run `shfmt -i 2 -ci -w bin/new.sh bin/test-check-inventory.sh` and `shellcheck` on both before committing any task that touches them.
