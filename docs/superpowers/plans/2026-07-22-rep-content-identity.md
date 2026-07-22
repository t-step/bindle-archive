# Rep Content Identity (#339) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every pressure-test rep a derived content identity for the skill
it tested — a `bin/skill-content-id.sh` helper, a `**Content:**` field in the
protocol, `unrecorded` annotations for all pre-existing series, and a warn-only
stale-reps banner in `check.sh`.

**Architecture:** A skill's content-id is sha256 over the `LC_ALL=C`-sorted
`"<sha256>  <path>"` lines of every tracked file under `skills/<name>/` except
`PRESSURE-TESTS.md`, bytes read from the working tree, recorded as `sha256:` +
first 12 hex. The helper computes and checks it; `check.sh` surfaces drift as a
non-blocking disclosure; the protocol documents the field with the same
granularity and single-source rules as #331's `**Model:**`.

**Tech Stack:** bash 3.2-compatible shell, `shasum -a 256`, the repo's existing
`bin/test-*.sh` harness idiom. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-22-rep-content-identity-design.md`
(operator-approved). Read it before starting.

## Global Constraints

- Work happens in the worktree `.worktrees/feature-339-rep-content-identity`
  on branch `feature/339-rep-content-identity`. Never commit to `main`. Never
  push. Never open a PR — the operator decides disposition.
- All shell must run under macOS bash 3.2: guard every array expansion with
  `[ "${#arr[@]}" -gt 0 ]` before `"${arr[@]}"`; no `${arr[-1]}` negative
  subscripts (use `${arr[$((${#arr[@]} - 1))]}`); no associative arrays.
- Format shell with `shfmt -i 2 -ci -w <files>` (bare `shfmt -w` uses
  different defaults and fails `make check`). Run `shellcheck` on new scripts.
- Never `cmd | grep -q PATTERN` under pipefail where the pattern can match
  early — capture first: `out="$(cmd)"; grep -q PATTERN <<<"$out"`.
- `capabilities.json` is insertion-ordered and stores non-ASCII escaped: edit
  it **textually only** (no `json.load`/`json.dumps` round-trip); keep added
  text ASCII; after editing, `git diff --stat capabilities.json` must show
  exactly the lines you added.
- `git add` every new `bin/test-*.sh` before running `bin/run-test-suites.sh`
  — discovery is `git ls-files 'bin/test-*.sh'`; an untracked suite is
  silently skipped while the run still reports all-green.
- Before every commit: `make check` green with **no PARTIAL banner** (stage
  new files first), then commit — the pre-commit hook runs every discovered
  suite and exceeds 2 minutes; run commits in the foreground with a generous
  timeout.
- New `bin/*.sh` files must be executable (`chmod +x`) — `run-test-suites.sh`
  reports non-executable suites as failures.

---

### Task 1: `bin/skill-content-id.sh` + its test suite + ledger entries

**Files:**
- Create: `bin/skill-content-id.sh`
- Create: `bin/test-skill-content-id.sh`
- Modify: `capabilities.json` (two textual insertions)

**Interfaces:**
- Produces: `bin/skill-content-id.sh <skill>` → prints `sha256:<12 hex>`,
  exit 0. `--check <skill>` → per-line `  sha256:<hex> MATCH|STALE` report,
  then one verdict line `<name>: FRESH (newest hashed series matches current
  <id>)` (exit 0) / `<name>: STALE (current <id>, newest hashed series <id>)`
  (exit 1) / `<name>: NO-HASHED-SERIES (grandfathered-only or no evidence
  file; current <id>)` (exit 2). `--check --all` →
  verdict lines only (no per-line report), skips `_template`, exit 1 if any
  skill is STALE else 0. Environment errors exit 3; usage errors exit 64.
  Task 2's banner greps `--check --all` output for `: STALE`.

- [ ] **Step 1: Write the failing test suite**

Create `bin/test-skill-content-id.sh`:

```bash
#!/usr/bin/env bash
# Tests bin/skill-content-id.sh (#339): identity formula (tracked files under
# skills/<name>/ minus PRESSURE-TESTS.md, working-tree bytes, sorted), --check
# verdicts and exit codes, --all aggregation and _template skip.
set -uo pipefail

# Under a git hook, git exports GIT_DIR and friends to subprocesses; scrub so
# the fixture-repo git calls below cannot hit the real repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ID_SRC="$REPO_ROOT/bin/skill-content-id.sh"

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
contains() { grep -qF -- "$1" <<<"$2"; }       # contains NEEDLE HAYSTACK
not_contains() { ! grep -qF -- "$1" <<<"$2"; } # not_contains NEEDLE HAYSTACK
exit_is() { [ "$1" -eq "$2" ]; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

build_fixture() { # build_fixture <dir> — a minimal repo with three skills
  local d="$1"
  mkdir -p "$d/bin" "$d/skills/demo/references" "$d/skills/_template" \
    "$d/skills/other"
  cp "$ID_SRC" "$d/bin/skill-content-id.sh"
  chmod +x "$d/bin/skill-content-id.sh"
  printf 'demo body v1\n' >"$d/skills/demo/SKILL.md"
  printf 'ref v1\n' >"$d/skills/demo/references/notes.md"
  printf 'evidence v1\n' >"$d/skills/demo/PRESSURE-TESTS.md"
  printf 'template\n' >"$d/skills/_template/SKILL.md"
  printf 'other body\n' >"$d/skills/other/SKILL.md"
  (cd "$d" && git init -q && git add -A &&
    git -c user.email=t@t -c user.name=t commit -qm init)
}

echo "identity formula:"

FIX="$TMP/fix1"
build_fixture "$FIX"
id1="$(cd "$FIX" && bin/skill-content-id.sh demo)"
id2="$(cd "$FIX" && bin/skill-content-id.sh demo)"
case "$id1" in
sha256:????????????) check "prints a sha256:<12 hex> id" true ;;
*) check "prints a sha256:<12 hex> id" false ;;
esac
check "id is stable across runs" test "$id1" = "$id2"

printf 'evidence v2\n' >"$FIX/skills/demo/PRESSURE-TESTS.md"
id3="$(cd "$FIX" && bin/skill-content-id.sh demo)"
check "PRESSURE-TESTS.md edits do not change the id" test "$id1" = "$id3"

printf 'ref v2\n' >"$FIX/skills/demo/references/notes.md"
id4="$(cd "$FIX" && bin/skill-content-id.sh demo)"
check "references/ edits change the id" test "$id1" != "$id4"
printf 'ref v1\n' >"$FIX/skills/demo/references/notes.md"

printf 'untracked scratch\n' >"$FIX/skills/demo/scratch.md"
id5="$(cd "$FIX" && bin/skill-content-id.sh demo)"
check "untracked files do not change the id" test "$id1" = "$id5"
rm "$FIX/skills/demo/scratch.md"

printf 'demo body v2\n' >"$FIX/skills/demo/SKILL.md"
id6="$(cd "$FIX" && bin/skill-content-id.sh demo)"
check "uncommitted working-tree SKILL.md edits change the id" \
  test "$id1" != "$id6"
printf 'demo body v1\n' >"$FIX/skills/demo/SKILL.md"

rm "$FIX/skills/demo/references/notes.md"
(cd "$FIX" && bin/skill-content-id.sh demo >/dev/null 2>&1)
rc=$?
check "tracked file missing from working tree fails loudly (exit 3)" \
  exit_is "$rc" 3
printf 'ref v1\n' >"$FIX/skills/demo/references/notes.md"

(cd "$FIX" && bin/skill-content-id.sh nonexistent >/dev/null 2>&1)
rc=$?
check "unknown skill (no tracked files) is exit 2" exit_is "$rc" 2

echo "--check verdicts:"

FIX2="$TMP/fix2"
build_fixture "$FIX2"
cur="$(cd "$FIX2" && bin/skill-content-id.sh demo)"

out="$(cd "$FIX2" && bin/skill-content-id.sh --check demo)"
rc=$?
check "no hashed series is exit 2" exit_is "$rc" 2
check "verdict names NO-HASHED-SERIES" contains "NO-HASHED-SERIES" "$out"

printf '%s\n' "**Content:** unrecorded" >"$FIX2/skills/demo/PRESSURE-TESTS.md"
out="$(cd "$FIX2" && bin/skill-content-id.sh --check demo)"
rc=$?
check "unrecorded-only series is still exit 2" exit_is "$rc" 2

printf '%s\n%s\n' "**Content:** sha256:000000000000" "**Content:** $cur" \
  >"$FIX2/skills/demo/PRESSURE-TESTS.md"
out="$(cd "$FIX2" && bin/skill-content-id.sh --check demo)"
rc=$?
check "newest (last-in-file) hashed line matching is FRESH exit 0" \
  exit_is "$rc" 0
check "per-line report marks the stale older series" \
  contains "sha256:000000000000 STALE" "$out"

printf '%s\n%s\n' "**Content:** $cur" "**Content:** sha256:000000000000" \
  >"$FIX2/skills/demo/PRESSURE-TESTS.md"
out="$(cd "$FIX2" && bin/skill-content-id.sh --check demo)"
rc=$?
check "newest hashed line differing is STALE exit 1" exit_is "$rc" 1
check "verdict names the newest recorded id" \
  contains "newest hashed series sha256:000000000000" "$out"

echo "--check --all:"

out="$(cd "$FIX2" && bin/skill-content-id.sh --check --all)"
rc=$?
check "aggregate exit is 1 when any skill is stale" exit_is "$rc" 1
check "the stale skill is named" contains "demo: STALE" "$out"
check "_template is skipped" not_contains "_template" "$out"
check "no-hashed-series skills are reported, not fatal" \
  contains "other: NO-HASHED-SERIES" "$out"

printf '%s\n' "**Content:** $cur" >"$FIX2/skills/demo/PRESSURE-TESTS.md"
out="$(cd "$FIX2" && bin/skill-content-id.sh --check --all)"
rc=$?
check "aggregate exit is 0 when nothing is stale" exit_is "$rc" 0

echo "usage:"

(cd "$FIX2" && bin/skill-content-id.sh >/dev/null 2>&1)
rc=$?
check "no args is usage error 64" exit_is "$rc" 64
(cd "$FIX2" && bin/skill-content-id.sh --all >/dev/null 2>&1)
rc=$?
check "--all without --check is usage error 64" exit_is "$rc" 64

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
```

Then: `chmod +x bin/test-skill-content-id.sh && git add bin/test-skill-content-id.sh`
(tracked now so suite discovery sees it from this commit on).

- [ ] **Step 2: Run the suite to verify it fails**

Run: `bash bin/test-skill-content-id.sh`
Expected: FAIL — `cp: .../bin/skill-content-id.sh: No such file or directory`
and/or every `check` red. The point is a nonzero exit before implementation.

- [ ] **Step 3: Write the helper**

Create `bin/skill-content-id.sh`:

```bash
#!/usr/bin/env bash
# skill-content-id.sh — derived content identity for a skill's rep evidence
# (#339). The id is sha256 over the LC_ALL=C-sorted "<sha256>  <path>" lines
# of every TRACKED file under skills/<name>/ except PRESSURE-TESTS.md (the
# evidence file cannot be part of the identity it records). Bytes come from
# the WORKING TREE — reps exercise installed disk content through the
# ~/.claude symlink, so the id describes what actually ran, uncommitted edits
# included. Recorded form: "sha256:" + first 12 hex.
#
# Usage:
#   bin/skill-content-id.sh <skill>          print the current id
#   bin/skill-content-id.sh --check <skill>  compare against the skill's
#                                            recorded **Content:** lines
#   bin/skill-content-id.sh --check --all    every skills/* except _template
#
# --check exits: 0 newest hashed series matches current; 1 drift; 2 no hashed
# series (grandfathered-only, or no evidence file). Environment errors exit 3;
# usage errors exit 64.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 3

usage() {
  echo "usage: bin/skill-content-id.sh <skill> | --check <skill> | --check --all" >&2
  exit 64
}

compute_id() { # compute_id <name> — prints sha256:<12 hex>
  local name="$1" f
  local files=()
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ "$f" = "skills/$name/PRESSURE-TESTS.md" ] && continue
    files+=("$f")
  done < <(git ls-files -- "skills/$name" | LC_ALL=C sort)
  if [ "${#files[@]}" -eq 0 ]; then
    echo "skill-content-id: no tracked files under skills/$name" >&2
    return 2
  fi
  for f in "${files[@]}"; do
    if [ ! -f "$f" ]; then
      echo "skill-content-id: tracked file missing from working tree: $f" >&2
      return 3
    fi
  done
  local stream id
  stream="$(shasum -a 256 "${files[@]}")" || return 3
  id="$(shasum -a 256 <<<"$stream")" || return 3
  printf 'sha256:%s\n' "${id:0:12}"
}

check_skill() { # check_skill <name> [quiet] — verdict line(s); 0/1/2/3
  local name="$1" quiet="${2:-}" current line r rc
  current="$(compute_id "$name")" || {
    rc=$?
    return "$rc"
  }
  local recorded=()
  local pt="skills/$name/PRESSURE-TESTS.md"
  if [ -f "$pt" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      recorded+=("$line")
    done < <(grep -oE '\*\*Content:\*\* sha256:[0-9a-f]{12}' "$pt" |
      grep -oE 'sha256:[0-9a-f]{12}')
  fi
  if [ "${#recorded[@]}" -eq 0 ]; then
    echo "$name: NO-HASHED-SERIES (grandfathered-only or no evidence file; current $current)"
    return 2
  fi
  if [ -z "$quiet" ]; then
    for r in "${recorded[@]}"; do
      if [ "$r" = "$current" ]; then
        echo "  $r MATCH"
      else
        echo "  $r STALE"
      fi
    done
  fi
  local newest="${recorded[$((${#recorded[@]} - 1))]}"
  if [ "$newest" = "$current" ]; then
    echo "$name: FRESH (newest hashed series matches current $current)"
    return 0
  fi
  echo "$name: STALE (current $current, newest hashed series $newest)"
  return 1
}

check=false all=false skill=""
while [ "$#" -gt 0 ]; do
  case "$1" in
  --check) check=true ;;
  --all) all=true ;;
  -*) usage ;;
  *)
    [ -z "$skill" ] || usage
    skill="$1"
    ;;
  esac
  shift
done

if $all; then
  $check || usage
  [ -z "$skill" ] || usage
  worst=0
  for d in skills/*/; do
    name="$(basename "$d")"
    [ "$name" = "_template" ] && continue
    check_skill "$name" quiet
    rc=$?
    [ "$rc" -eq 1 ] && worst=1
    [ "$rc" -ge 3 ] && exit "$rc"
  done
  exit "$worst"
fi

[ -n "$skill" ] || usage
if $check; then
  check_skill "$skill"
  exit "$?"
fi
compute_id "$skill"
exit "$?"
```

Then: `chmod +x bin/skill-content-id.sh`, `shfmt -i 2 -ci -w bin/skill-content-id.sh bin/test-skill-content-id.sh`, `shellcheck bin/skill-content-id.sh bin/test-skill-content-id.sh` (fix any findings), `git add bin/skill-content-id.sh`.

Note the test asserts the verdict substring `newest hashed series sha256:000000000000` — the STALE verdict wording above contains it. Keep wording and test in sync if either changes. The `: STALE` / `: FRESH` / `: NO-HASHED-SERIES` verdict prefixes are the machine surface Task 2 greps; do not reword them.

- [ ] **Step 4: Run the suite to verify it passes**

Run: `bash bin/test-skill-content-id.sh`
Expected: `tests: 22 passed, 0 failed`, exit 0.

Sanity-run against the real tree: `bin/skill-content-id.sh session-continuity`
prints one `sha256:<12 hex>` line; `bin/skill-content-id.sh --check --all`
exits 2-free with every line `NO-HASHED-SERIES` (no `**Content:**` lines exist
yet) and aggregate exit 0.

- [ ] **Step 5: Ledger both files in `capabilities.json`**

Two textual insertions (ASCII only; no JSON round-trip):

(a) In the inventory array, immediately **after** the closing brace-comma of
the `"name": "domi-release-check"` entry (the newest `type: "script"` entry,
near line 398–411), insert:

```json
    {
      "name": "skill-content-id",
      "type": "script",
      "path": "bin/skill-content-id.sh",
      "description": "Derived content identity for a skill's pressure-test evidence (#339): sha256 over the sorted tracked-file hash list under skills/<name>/ minus PRESSURE-TESTS.md, working-tree bytes, recorded as sha256:<12 hex>; --check compares recorded **Content:** lines against current content (0 fresh / 1 stale / 2 no hashed series), --check --all feeds bin/check.sh's warn-only stale-reps banner.",
      "provider": {
        "claude": "manual",
        "codex": "manual"
      },
      "maturity": "tested",
      "mutation": [],
      "version_introduced": "0.10.1"
    },
```

(b) In `not_a_capability`, immediately **after** the
`docs/superpowers/specs/2026-07-22-rep-content-identity-design.md` entry (the
last entry, just before the array's closing `]`), insert (add a comma to the
previous entry's closing brace):

```json
    {
      "path": "bin/test-skill-content-id.sh",
      "reason": "suite for bin/skill-content-id.sh over throwaway fixture repos (identity formula and membership rules, PRESSURE-TESTS.md exclusion, working-tree bytes, --check verdict exit codes, --all aggregation and _template skip, usage errors); test infrastructure, not a capability an agent invokes."
    }
```

Verify: `git add capabilities.json && git diff --cached --stat capabilities.json`
shows ~20 insertions and **0 deletions beyond the one comma line** — a larger
diff means an accidental re-serialization; revert and redo textually.

- [ ] **Step 6: Gates, then commit**

Run: `make check` (foreground, generous timeout)
Expected: `All checks passed.` — **no PARTIAL banner** (everything staged).

Run: `bin/run-test-suites.sh`
Expected: all suites pass, count is one higher than before (the new suite is
discovered — if the count did not go up, the suite is not tracked; fix that).

```bash
git commit -m "feat(#339): add bin/skill-content-id.sh derived content identity

sha256 over the sorted tracked-file hash list under skills/<name>/ minus
PRESSURE-TESTS.md, working-tree bytes; --check compares recorded
**Content:** lines (0 fresh / 1 stale / 2 no hashed series), --check
--all aggregates for check.sh."
```

---

### Task 2: warn-only stale-reps banner in `check.sh`

**Files:**
- Modify: `bin/check.sh` (insert one block between the `# --- scan scope (#347)`
  block, which ends at the `fi` closing its `if [ -n "$skipped" ]`, and the
  `# --- result` block)
- Modify: `bin/test-check.sh` (append one test group before its
  `# --- result` footer)

**Interfaces:**
- Consumes: Task 1's `bin/skill-content-id.sh --check --all` verdict lines
  (`<name>: STALE …` greppable via `: STALE`), aggregate exit 0/1.
- Produces: a `stale reps:` output section in `bin/check.sh`, never touching
  `$fail` or the exit code.

- [ ] **Step 1: Write the failing test**

In `bin/test-check.sh`, insert before the `# --- result` footer. The fixture
skill deliberately does NOT try to satisfy the content/inventory sections —
build_repo fixtures are minimal — so the test compares exit codes between a
grandfathered baseline and a stale state rather than asserting exit 0:

```bash
# A skill whose content changed since its newest hashed rep series carries
# evidence about text that no longer ships (#339). The banner is warn-only by
# the recorded decision: it must name the drift and must not move the exit
# code. Grandfathered (unrecorded-only) series must produce no banner at all.
echo "stale-reps banner (#339):"

REPO="$TMP/repo-stale-reps"
build_repo "$REPO"
cp "$REPO_ROOT/bin/skill-content-id.sh" "$REPO/bin/skill-content-id.sh"
chmod +x "$REPO/bin/skill-content-id.sh"
mkdir -p "$REPO/skills/demo"
printf 'demo body\n' >"$REPO/skills/demo/SKILL.md"
printf '%s\n' '**Content:** unrecorded' >"$REPO/skills/demo/PRESSURE-TESTS.md"
(cd "$REPO" && git add -A &&
  git -c user.email=t@t -c user.name=t commit -qm 'add demo skill')

out="$(cd "$REPO" && bin/check.sh 2>&1)"
base_status=$?
check "grandfathered-only series produce no banner" \
  not_contains "stale reps:" "$out"

printf '%s\n' '**Content:** sha256:000000000000' \
  >"$REPO/skills/demo/PRESSURE-TESTS.md"
(cd "$REPO" && git add -A &&
  git -c user.email=t@t -c user.name=t commit -qm 'hashed series')

out="$(cd "$REPO" && bin/check.sh 2>&1)"
status=$?
check "names the drifted skill in a stale-reps warning" \
  contains "demo: STALE" "$out"
check "says the banner is warn-only" contains "warn-only" "$out"
check "stale reps do not change the exit code" test "$status" -eq "$base_status"
```

(If `build_repo` in `bin/test-check.sh` already creates a `skills/` directory
or a conflicting `demo` entry, adapt the fixture name to `demo339` in all
five places — nothing else may change.)

- [ ] **Step 2: Run it to verify it fails**

Run: `bash bin/test-check.sh`
Expected: the three new stale-reps checks FAIL (`demo: STALE` and `warn-only`
absent — the banner does not exist yet); the no-banner baseline check passes
vacuously. All pre-existing checks still pass.

- [ ] **Step 3: Implement the banner**

In `bin/check.sh`, immediately after the scan-scope block's closing `fi` and
before `# --- result`, insert:

```bash
# --- stale reps (#339) ------------------------------------------------------
# A skill whose content changed since its newest hashed rep series is carrying
# evidence about text that no longer ships. Warn-only by the recorded #339
# decision (docs/superpowers/specs/2026-07-22-rep-content-identity-design.md):
# a hard gate would couple every routine SKILL.md edit to a fresh 5-rep
# campaign (#335 floor) and would be bypassed rather than heeded. Skills whose
# series are all `unrecorded` (grandfathered) exit 2, not 1, so this banner
# starts empty and only ever names genuine post-#339 drift.
if [ -x bin/skill-content-id.sh ]; then
  stale_reps="$(bin/skill-content-id.sh --check --all 2>/dev/null | grep ': STALE' || true)"
  if [ -n "$stale_reps" ]; then
    echo
    echo "stale reps:"
    echo "  WARN (warn-only, #339): skill content changed since the newest hashed rep series —"
    while IFS= read -r p; do echo "    $p"; done <<<"$stale_reps"
    echo "    run bin/skill-content-id.sh --check <skill> for the per-series report."
  fi
fi
```

The `[ -x … ]` guard keeps every existing `bin/test-check.sh` fixture repo
(none of which carry the helper) green without modification. The block never
touches `$fail`. `grep … || true` is safe here: grep consumes all input, so
the pipefail-SIGPIPE hazard does not apply.

Then: `shfmt -i 2 -ci -w bin/check.sh bin/test-check.sh` and confirm
`git diff bin/check.sh` shows only the inserted block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bash bin/test-check.sh`
Expected: all checks pass, including the four new ones.

Run: `bash bin/test-skill-content-id.sh`
Expected: still `22 passed, 0 failed`.

Run: `make check`
Expected: `All checks passed.`, and **no** `stale reps:` section (the real
tree has no hashed `**Content:**` lines yet).

- [ ] **Step 5: Commit**

```bash
git add bin/check.sh bin/test-check.sh
git commit -m "feat(#339): warn-only stale-reps banner in check.sh

Names skills whose current content-id differs from their newest hashed
**Content:** series; never moves the exit code; grandfathered-only
skills are excluded so the banner starts empty."
```

---

### Task 3: protocol amendments (§ Recording, § Grandfathered)

**Files:**
- Modify: `docs/pressure-testing-protocol.md` (three insertions; current
  § Recording is lines 181–217, § Grandfathered 219–238)

**Interfaces:**
- Consumes: Task 1's helper name and recorded-form syntax
  (`**Content:** sha256:<12 hex>` / `**Content:** unrecorded`).
- Produces: the field definition Task 4's sweep annotates against.

- [ ] **Step 1: Add the `**Content:**` bullet to § Recording**

In the § Recording bullet list, insert a new bullet **after** the `**Model:**`
bullet (which ends `…not an invented dated snapshot);`) and **before**
`- a FAIL kept as a FAIL…`:

```markdown
- the **content identity** of the skill under test — a `**Content:**` line
  beside the `**Model:**` line in each series' method statement, recording
  the output of `bin/skill-content-id.sh <skill>` (e.g. "**Content:**
  sha256:3f7a29c04d11"), computed **at dispatch time**, never reconstructed
  afterward. The id covers every tracked file under `skills/<name>/` except
  `PRESSURE-TESTS.md` itself, hashed from the working tree — it describes
  the bytes the reps actually exercised, uncommitted edits included.
  Granularity matches `**Model:**`: per-series, with a per-arm/per-rep
  override — a REFACTOR mid-series edit means the GREEN arms before and
  after the edit carry different ids, recorded per arm. RED (no-skill) arms
  carry no id — nothing was loaded. A series whose id is not known writes
  `**Content:** unrecorded` — an explicit unknown, never silence, never a
  value derived after the fact;
```

- [ ] **Step 2: Extend the single-source paragraph**

Immediately **after** the paragraph beginning `The `**Model:**` field is the
**single source** for model provenance…` (ends `…that is evidence, not a
caveat.`), insert a new paragraph:

```markdown
The `**Content:**` field follows the same single-source rule. It is also the
field tooling keys on: `bin/skill-content-id.sh --check <skill>` is the
one-command answer to "do this skill's hashed reps still apply to its current
content?", and `bin/check.sh` prints a warn-only `stale reps` banner when a
skill's newest hashed series no longer matches — a disclosure, not a gate,
by the recorded #339 decision.
```

- [ ] **Step 3: Add the grandfathering rule to § Grandfathered**

Immediately **after** the paragraph beginning `The `**Model:**` field (#331)
follows the same rule…` (ends `…is still pre-protocol.`) and **before** the
`### What this does to #212's targets` heading, insert:

```markdown
The `**Content:**` field (#339) is stricter still: historical series are
annotated `**Content:** unrecorded`, full stop. The dispatch-time working
tree is unknowable from a `Status:` date — the exact commit was not
recorded, and reps may have run against uncommitted content — so a hash
derived from git archaeology is a guess wearing precision, worse than an
honest unknown. Never re-run a series to learn its id; an annotation is not
a protocol credit.
```

- [ ] **Step 4: Gates, then commit**

Run: `make check`
Expected: `All checks passed.`

```bash
git add docs/pressure-testing-protocol.md
git commit -m "docs(#339): protocol records a Content: identity per rep series

Same granularity and single-source rules as #331's Model: field;
grandfathered series annotate unrecorded, never a hash derived from git
archaeology; staleness surfaced warn-only via check.sh."
```

---

### Task 4: annotate all 13 evidence files, verify counts

**Files:**
- Modify: all 13 `skills/*/PRESSURE-TESTS.md` (every skill except `_template`)

**Interfaces:**
- Consumes: Task 3's field definition; Task 1's `--check --all` (verification).

- [ ] **Step 1: Insert one `**Content:** unrecorded` paragraph per `**Model:**` line**

Mechanical rule: in each file, immediately after the paragraph containing each
`**Model:**` line (paragraphs can wrap 2–3 lines; insert after the paragraph's
final line, then a blank line), add:

```markdown
**Content:** unrecorded (annotated per #339; the dispatch-time content is not
derivable from recorded dates).
```

Worked example (`skills/hands-on-keyboard/PRESSURE-TESTS.md`):

```markdown
**Model:** Sonnet 5, Claude Code — both arms (annotated per #331; exact dated
snapshot not recorded).

**Content:** unrecorded (annotated per #339; the dispatch-time content is not
derivable from recorded dates).
```

Expected insertions per file (the per-file `**Model:**` counts): context-graph
3, fork-pr-flow 2, domi-consumer 1, hands-on-keyboard 4,
license-compliance-auditor 1, issue-work-loop 3, package-release-integrity 5,
maintain-claude-md 1, repo-hygiene-init 1, release-captain 1,
scoped-sequential-prs 1, session-continuity 1, verify-then-commit 6 — total 30.

- [ ] **Step 2: Verify the pairing exactly**

Run:

```bash
for f in skills/*/PRESSURE-TESTS.md; do
  m="$(grep -c '\*\*Model:\*\*' "$f")"
  c="$(grep -c '\*\*Content:\*\*' "$f")"
  [ "$m" = "$c" ] || echo "MISMATCH $f: Model=$m Content=$c"
done
```

Expected: no output. Also run `grep -rn '\*\*Content:\*\* sha256:' skills/` —
expected: no output (every annotation is `unrecorded`; a hashed line here
would light the banner for a series that never recorded one).

- [ ] **Step 3: Confirm the banner stays dark and gates pass**

Run: `bin/skill-content-id.sh --check --all; echo "exit $?"`
Expected: 13 `NO-HASHED-SERIES` lines (every skill with an evidence file),
`exit 0`.

Run: `make check`
Expected: `All checks passed.` with **no** `stale reps:` section.

Run: `bash bin/test-skill-content-id.sh && bash bin/test-check.sh`
Expected: both green (the sweep must not have broken fixture assumptions).

- [ ] **Step 4: Commit**

```bash
git add skills/*/PRESSURE-TESTS.md
git commit -m "docs(#339): annotate all pre-existing rep series Content: unrecorded

One line per **Model:** line, 30 total across 13 files; honest unknowns
per the #261/#331 precedent — never derived from git archaeology, never
a re-run obligation, annotation is not protocol credit."
```

---

### Task 5: final verification (no commit)

- [ ] **Step 1: Full gates from the worktree root**

Run, in order, foreground with generous timeouts:

```bash
make check
bin/run-test-suites.sh
```

Expected: `All checks passed.` (no PARTIAL, no stale-reps banner); all suites
green with the new suite included in the count.

- [ ] **Step 2: On-demand secret scan**

Run: `gitleaks git . --redact`
Expected: no leaks. (Remember its result covers tracked content only; confirm
`git status --porcelain` is empty first.)

- [ ] **Step 3: Report**

Report branch state (`git log --oneline origin/main..HEAD` — expect 6 commits
including the spec and this plan), gate results, and stop. **Do not push, do
not open a PR** — disposition is the operator's call.
