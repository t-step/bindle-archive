# Objective Isolation & Deliverable Disposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an objective-isolation gate to the issue work loop's Phase 4 (authorized repository-mutating work runs in a dedicated worktree based on a freshly-fetched `origin/main`, with provenance recorded) and a deliverable-disposition gate to Phase 6 (completion stops at one contextual interactive decision that offers only valid actions and performs no external mutation without an explicit answer).

**Architecture:** Two gates extend existing phases of the `issue-work-loop` contract — no new lifecycle contract. A deterministic shell helper (`bin/objective-worktree.sh`) encodes the isolation git logic and emits the resolved base SHA so a model cannot fake it (the `issue-dedup-scan.sh` honesty pattern). The disposition gate is judgment carried in the Claude adapter (`AskUserQuestion`), with the contract stating the provider-neutral requirement.

**Tech Stack:** Bash (helpers + fixture tests), Markdown (contract + skill + packets docs), `capabilities.json` (inventory), Makefile + `.pre-commit-config.yaml` (test wiring). Validation gate: `make check`.

## Global Constraints

- Branch-and-PR repo: work on `feature/objective-isolation-disposition`, never commit to `main`; `make check` must pass before every commit; never `--no-verify`.
- Provider-neutral contract, Claude-native adapter: normative requirements go in `docs/workflows/issue-work-loop.md` and `docs/delegated-implementation-packets.md`; Claude-specific mechanism (`AskUserQuestion`, the helper invocation) goes in `skills/issue-work-loop/SKILL.md`. Do not neutralize the skill's Claude-native wording (Phase 1 rule).
- Shell formatting: run `shfmt -i 2 -ci -w <files>` before committing — bare `shfmt -w` uses different defaults and fails the gate.
- Helper conventions mirror `bin/session-end-land.sh` and `bin/issue-dedup-scan.sh`: header comment block usable as `--help`, first stdout line is a machine-readable verdict token, distinct exit codes.
- Inventory (the #29 footgun): a new `bin/*.sh` needs a `capabilities.json` row (`type: script`) **and** a `bin/test-*.sh` fixture; a new tracked `docs/**/*.md` needs an inventory row or a `not_a_capability` ledger entry — or `make check` fails on bound-table drift. Scripts do **not** need a `docs/skill-portability-audit.md` row (that bound-table is skills-only).
- `version_introduced` for the new helper capability: `"0.6.0"` (one bump ahead of VERSION `0.5.0`; `bin/check-inventory.py` accepts exactly one bump ahead).
- Link-checker gotcha: `bin/check.sh` greps every markdown link file-wide (including inside code fences) and resolves it relative to the file's own dir. In `docs/superpowers/**` bodies, reference other docs with inline code (`` `docs/x.md` ``) or a repo-absolute `/docs/...` link — never a bare relative markdown link.
- CHANGELOG.md is **not** hand-edited — Release Please owns it; conventional-commit subjects drive it.
- The design spec is `docs/superpowers/specs/2026-07-15-objective-isolation-disposition-design.md` (already committed as `8daea12`).

---

### Task 1: The `bin/objective-worktree.sh` isolation helper + fixture tests + wiring

**Files:**
- Create: `bin/objective-worktree.sh`
- Create: `bin/test-objective-worktree.sh`
- Modify: `Makefile` (add the test to the `test:` target)
- Modify: `.pre-commit-config.yaml` (add the test to the hooks)
- Modify: `capabilities.json` (add a `type: script` row for the helper)

**Interfaces:**
- Produces (the helper's contract, consumed by Task 3's skill bullet and Task 5's pressure tests):
  - CLI: `bin/objective-worktree.sh <branch> [--base <ref>] [--check] [--no-fetch]`
  - First stdout line, on success: `READY: <worktree-path> <branch> <base-ref> <base-sha>` (exit 0)
  - First stdout line, on a fail-closed condition: `BLOCKED: origin-unavailable | base-unavailable | branch-exists | worktree-occupied` (exit 10)
  - First stdout line, on environment/usage error: `ERROR: <reason>` (exit 1) or usage error (exit 64)
  - `<worktree-path>` is `<repo-root>/.worktrees/<branch-leaf>`, where `<branch-leaf>` is the branch name after the last `/` (`feature/foo` → `foo`).
  - Default base ref is `origin/main`; `--base <ref>` overrides it.
  - `--check` prints the `READY:` (or `BLOCKED:`/`ERROR:`) verdict without creating anything.
  - `--no-fetch` skips `git fetch origin` (caller already fetched).
  - The helper does **not** require a clean primary working tree.

- [ ] **Step 1: Write the failing fixture test harness + first cases**

Create `bin/test-objective-worktree.sh`. It builds throwaway git sandboxes (a bare "origin" plus a working clone) in a temp dir and asserts the verdict token, exit code, and side effects. Follow the counter/`fail`/`pass` style of `bin/test-session-end-land.sh`.

```bash
#!/usr/bin/env bash
# test-objective-worktree.sh — fixture tests for bin/objective-worktree.sh.
# Covers issue-work-loop pressure tests 1, 2, 4, 12: fresh-origin base even
# when local main is stale; dirty primary untouched; fail-closed on
# existing branch / occupied worktree; provenance in the READY line.
set -uo pipefail

HELPER="$(cd "$(dirname "$0")" && pwd)/objective-worktree.sh"
PASS=0
FAIL=0

pass() {
  PASS=$((PASS + 1))
  echo "  ✓ $1"
}
fail() {
  FAIL=$((FAIL + 1))
  echo "  ✗ $1"
}

# make_sandbox <dir> — a bare origin with one commit on main, plus a clone.
# Prints the clone path on stdout.
make_sandbox() {
  local root="$1"
  git init -q --bare "$root/origin.git"
  git clone -q "$root/origin.git" "$root/work" 2>/dev/null
  git -C "$root/work" config user.email t@e.st
  git -C "$root/work" config user.name tester
  git -C "$root/work" checkout -q -b main
  echo seed >"$root/work/seed.txt"
  git -C "$root/work" add -A
  git -C "$root/work" commit -qm seed
  git -C "$root/work" push -q origin main 2>/dev/null
  echo "$root/work"
}

# advance_origin <clone> — add a commit to origin/main that the clone's local
# main does not have yet (simulates a stale local main). Prints the new SHA.
advance_origin() {
  local work="$1" tmp
  tmp="$(mktemp -d)"
  git clone -q "$(git -C "$work" remote get-url origin)" "$tmp/c" 2>/dev/null
  git -C "$tmp/c" config user.email t@e.st
  git -C "$tmp/c" config user.name tester
  git -C "$tmp/c" checkout -q main
  echo more >"$tmp/c/more.txt"
  git -C "$tmp/c" add -A
  git -C "$tmp/c" commit -qm more
  git -C "$tmp/c" push -q origin main 2>/dev/null
  git -C "$tmp/c" rev-parse HEAD
  rm -rf "$tmp"
}
```

- [ ] **Step 2: Add the test cases (still failing — the helper does not exist yet)**

Append the cases to `bin/test-objective-worktree.sh`, then a summary/exit footer.

```bash
# Case 1 (PT1): base is the fresh origin/main SHA, even when local main is stale.
T="$(mktemp -d)"; W="$(make_sandbox "$T")"
NEW_SHA="$(advance_origin "$W")"
OUT="$(cd "$W" && "$HELPER" feature/x)"
RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 0 ] && printf '%s' "$LINE1" | grep -q "^READY: " \
  && printf '%s' "$LINE1" | grep -q "$NEW_SHA"; then
  pass "PT1: base SHA is fresh origin/main ($NEW_SHA), not stale local main"
else
  fail "PT1: expected READY with base-sha $NEW_SHA, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 2 (PT2): a dirty primary checkout is left untouched.
T="$(mktemp -d)"; W="$(make_sandbox "$T")"
echo dirty >"$W/uncommitted.txt"
HEAD_BEFORE="$(git -C "$W" rev-parse HEAD)"
OUT="$(cd "$W" && "$HELPER" feature/y)"; RC=$?
STILL_DIRTY="$(git -C "$W" status --porcelain | grep -c uncommitted.txt)"
HEAD_AFTER="$(git -C "$W" rev-parse HEAD)"
if [ "$RC" -eq 0 ] && [ "$STILL_DIRTY" -eq 1 ] && [ "$HEAD_BEFORE" = "$HEAD_AFTER" ] \
  && [ -d "$W/.worktrees/y" ]; then
  pass "PT2: worktree created; primary tree still dirty; primary HEAD unmoved"
else
  fail "PT2: primary checkout disturbed (rc=$RC dirty=$STILL_DIRTY head==$([ "$HEAD_BEFORE" = "$HEAD_AFTER" ] && echo y || echo n))"
fi
rm -rf "$T"

# Case 3 (PT4a): an existing branch fails closed.
T="$(mktemp -d)"; W="$(make_sandbox "$T")"
git -C "$W" branch feature/z
OUT="$(cd "$W" && "$HELPER" feature/z)"; RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 10 ] && printf '%s' "$LINE1" | grep -q "^BLOCKED: branch-exists"; then
  pass "PT4a: existing branch -> BLOCKED: branch-exists (exit 10)"
else
  fail "PT4a: expected BLOCKED: branch-exists exit 10, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 4 (PT4b): an occupied worktree path fails closed.
T="$(mktemp -d)"; W="$(make_sandbox "$T")"
mkdir -p "$W/.worktrees/occupied"
OUT="$(cd "$W" && "$HELPER" feature/occupied)"; RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 10 ] && printf '%s' "$LINE1" | grep -q "^BLOCKED: worktree-occupied"; then
  pass "PT4b: occupied path -> BLOCKED: worktree-occupied (exit 10)"
else
  fail "PT4b: expected BLOCKED: worktree-occupied exit 10, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 5: an unresolvable base fails closed.
T="$(mktemp -d)"; W="$(make_sandbox "$T")"
OUT="$(cd "$W" && "$HELPER" feature/q --base origin/does-not-exist --no-fetch)"; RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 10 ] && printf '%s' "$LINE1" | grep -q "^BLOCKED: base-unavailable"; then
  pass "base-unavailable: unresolvable --base -> BLOCKED (exit 10)"
else
  fail "base-unavailable: expected BLOCKED: base-unavailable, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 6: no origin remote -> ERROR.
T="$(mktemp -d)"; git init -q "$T/solo"
git -C "$T/solo" config user.email t@e.st; git -C "$T/solo" config user.name tester
git -C "$T/solo" checkout -q -b main; echo a >"$T/solo/a"; git -C "$T/solo" add -A
git -C "$T/solo" commit -qm a
OUT="$(cd "$T/solo" && "$HELPER" feature/x --no-fetch)"; RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 1 ] && printf '%s' "$LINE1" | grep -q "^ERROR:"; then
  pass "no-origin: ERROR (exit 1)"
else
  fail "no-origin: expected ERROR exit 1, got: $LINE1 (rc=$RC)"
fi
rm -rf "$T"

# Case 7: --check creates nothing but prints READY.
T="$(mktemp -d)"; W="$(make_sandbox "$T")"
OUT="$(cd "$W" && "$HELPER" feature/dry --check)"; RC=$?
LINE1="$(printf '%s\n' "$OUT" | head -1)"
if [ "$RC" -eq 0 ] && printf '%s' "$LINE1" | grep -q "^READY: " && [ ! -d "$W/.worktrees/dry" ]; then
  pass "--check: prints READY, creates no worktree"
else
  fail "--check: expected READY with nothing created, got: $LINE1 (rc=$RC, dir=$([ -d "$W/.worktrees/dry" ] && echo exists || echo none))"
fi
rm -rf "$T"

# Case 8 (PT12): the READY line carries all four provenance fields.
T="$(mktemp -d)"; W="$(make_sandbox "$T")"
BASE_SHA="$(git -C "$W" rev-parse origin/main)"
OUT="$(cd "$W" && "$HELPER" feature/prov --check)"
LINE1="$(printf '%s\n' "$OUT" | head -1)"
# READY: <path> <branch> <base-ref> <base-sha>  -> 5 fields incl. token
NFIELDS="$(printf '%s' "$LINE1" | awk '{print NF}')"
if [ "$NFIELDS" -eq 5 ] \
  && printf '%s' "$LINE1" | grep -q "\.worktrees/prov" \
  && printf '%s' "$LINE1" | grep -q " feature/prov " \
  && printf '%s' "$LINE1" | grep -q " origin/main " \
  && printf '%s' "$LINE1" | grep -q " $BASE_SHA$"; then
  pass "PT12: READY line carries path, branch, base-ref, base-sha"
else
  fail "PT12: provenance fields missing, got: $LINE1"
fi
rm -rf "$T"

# Case 9: missing <branch> -> usage error (exit 64).
OUT="$("$HELPER" 2>&1)"; RC=$?
if [ "$RC" -eq 64 ]; then
  pass "usage: missing branch -> exit 64"
else
  fail "usage: expected exit 64, got rc=$RC"
fi

echo
echo "objective-worktree: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
```

- [ ] **Step 3: Run the test to verify it fails (helper absent)**

Run: `chmod +x bin/test-objective-worktree.sh && bin/test-objective-worktree.sh`
Expected: FAIL — every case errors because `bin/objective-worktree.sh` does not exist yet (non-zero exit; final line reports failures).

- [ ] **Step 4: Write the helper**

Create `bin/objective-worktree.sh`:

```bash
#!/usr/bin/env bash
#
# objective-worktree.sh — create an isolated worktree for authorized
# repository-mutating objective work, based on a freshly-fetched origin/main
# (or a caller-specified base). Emits the resolved base SHA so a caller cannot
# merely claim the base was fresh. Phase-4 adapter for the issue-work-loop
# contract (docs/workflows/issue-work-loop.md).
#
# Usage: bin/objective-worktree.sh <branch> [--base <ref>] [--check] [--no-fetch]
#   <branch>     objective branch to create (caller decides feature/ vs fix/).
#   --base <ref> base ref to resolve (default: origin/main).
#   --check      inspect + print verdict only; create nothing.
#   --no-fetch   skip git fetch (caller already fetched).
#
# Output: first stdout line is a machine-readable verdict token —
#   READY: <worktree-path> <branch> <base-ref> <base-sha>  created / would-create
#   BLOCKED: origin-unavailable   fetch or origin resolution failed
#   BLOCKED: base-unavailable     base ref does not resolve
#   BLOCKED: branch-exists        branch already exists
#   BLOCKED: worktree-occupied    worktree path already exists
#   ERROR: <reason>               not a git repo, no origin
# followed by human-readable detail.
#
# Exit codes: 0 READY · 10 BLOCKED · 1 ERROR · 64 usage error
#
set -uo pipefail

BRANCH=""
BASE="origin/main"
CHECK=0
FETCH=1

while [ $# -gt 0 ]; do
  case "$1" in
    -h | --help)
      awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
      exit 0
      ;;
    --base)
      BASE="${2:-}"
      [ -n "$BASE" ] || {
        echo "objective-worktree.sh: --base needs a ref" >&2
        exit 64
      }
      shift 2
      ;;
    --check) CHECK=1; shift ;;
    --no-fetch) FETCH=0; shift ;;
    -*)
      echo "objective-worktree.sh: unknown flag '$1'" >&2
      exit 64
      ;;
    *)
      [ -z "$BRANCH" ] || {
        echo "objective-worktree.sh: unexpected argument '$1'" >&2
        exit 64
      }
      BRANCH="$1"
      shift
      ;;
  esac
done

[ -n "$BRANCH" ] || {
  echo "objective-worktree.sh: missing <branch>" >&2
  exit 64
}

verdict() {
  echo "$1"
  [ -n "${2:-}" ] && echo "$2" >&2
  return 0
}

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  verdict "ERROR: not a git repository" ""
  exit 1
}

git -C "$ROOT" remote get-url origin >/dev/null 2>&1 || {
  verdict "ERROR: no origin remote" ""
  exit 1
}

if [ "$FETCH" -eq 1 ]; then
  if ! git -C "$ROOT" fetch --quiet origin 2>/dev/null; then
    verdict "BLOCKED: origin-unavailable" "git fetch origin failed"
    exit 10
  fi
fi

BASE_SHA="$(git -C "$ROOT" rev-parse --verify --quiet "$BASE^{commit}" 2>/dev/null)" || true
if [ -z "$BASE_SHA" ]; then
  verdict "BLOCKED: base-unavailable" "cannot resolve base ref '$BASE'"
  exit 10
fi

if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  verdict "BLOCKED: branch-exists" "branch '$BRANCH' already exists"
  exit 10
fi

LEAF="${BRANCH##*/}"
WT="$ROOT/.worktrees/$LEAF"
if [ -e "$WT" ]; then
  verdict "BLOCKED: worktree-occupied" "path '$WT' already exists"
  exit 10
fi

if [ "$CHECK" -eq 1 ]; then
  verdict "READY: $WT $BRANCH $BASE $BASE_SHA" "would create worktree at base $BASE_SHA (--check)"
  exit 0
fi

if ! git -C "$ROOT" worktree add --quiet "$WT" -b "$BRANCH" "$BASE_SHA" 2>/dev/null; then
  verdict "ERROR: worktree add failed" "git worktree add '$WT' -b '$BRANCH' '$BASE_SHA' failed"
  exit 1
fi

verdict "READY: $WT $BRANCH $BASE $BASE_SHA" "created worktree at base $BASE_SHA"
exit 0
```

- [ ] **Step 5: Make it executable and format it**

Run:
```bash
chmod +x bin/objective-worktree.sh
shfmt -i 2 -ci -w bin/objective-worktree.sh bin/test-objective-worktree.sh
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `bin/test-objective-worktree.sh`
Expected: PASS — final line `objective-worktree: 9 passed, 0 failed`, exit 0.

- [ ] **Step 7: Wire the test into `Makefile`**

In the `test:` target, add the new test after the existing `bin/test-session-end-land.sh` line:

```make
	bin/test-objective-worktree.sh
```

- [ ] **Step 8: Wire the test into `.pre-commit-config.yaml`**

Find the local hook that runs `bin/test-session-end-land.sh` (the `session-end-land.sh helper tests` entry). Add an analogous hook entry immediately after it, matching the surrounding style exactly:

```yaml
      - id: objective-worktree-test
        name: objective-worktree.sh helper tests
        entry: bin/test-objective-worktree.sh
        language: script
        pass_filenames: false
        files: ^bin/(objective-worktree|test-objective-worktree)\.sh$
```

(Copy the exact key set — `id`, `name`, `entry`, `language`, `pass_filenames`, `files` — from the `session-end-land` hook already present; adjust only the values.)

- [ ] **Step 9: Add the `capabilities.json` script row**

In the `capabilities` array, add a row next to the `issue-dedup-scan` script row, copying its field shape exactly:

```json
    {
      "name": "objective-worktree",
      "type": "script",
      "path": "bin/objective-worktree.sh",
      "description": "Isolation helper for authorized repository-mutating objective work: fetches origin, resolves origin/main (or a --base ref) to a commit SHA, and creates the objective branch + a dedicated worktree at that exact SHA, emitting the resolved base SHA so a caller cannot merely claim the base was fresh. First stdout line is a verdict token (READY / BLOCKED: origin-unavailable|base-unavailable|branch-exists|worktree-occupied / ERROR) with the exit code carrying the verdict (0/10/1). Phase-4 adapter for the issue-work-loop contract.",
      "provider": {
        "claude": "installed",
        "codex": "untested"
      },
      "maturity": "tested",
      "mutation": [
        "creates a local branch and a git worktree under .worktrees/"
      ],
      "version_introduced": "0.6.0"
    },
```

(Confirm `mutation`'s shape against a neighboring row — if the schema uses an empty array elsewhere, match the type; the value here documents that the helper creates a branch + worktree.)

- [ ] **Step 10: Run `make check` and the helper test together**

Run: `make check`
Expected: all checks pass, including `capability inventory OK` (now counting the new script row) and the helper test under the pre-commit-style suite.

- [ ] **Step 11: Commit**

```bash
git add bin/objective-worktree.sh bin/test-objective-worktree.sh Makefile .pre-commit-config.yaml capabilities.json
git commit -m "feat: objective-worktree.sh — isolate mutating work on fresh origin/main"
```

---

### Task 2: Extend the issue-work-loop contract (Phase 4, Phase 6, §9, §10)

**Files:**
- Modify: `docs/workflows/issue-work-loop.md` (§6 Phase 4, §8 Phase 6, §9 vocabulary, §10 provider table)

**Interfaces:**
- Consumes: the helper contract from Task 1 (verdict token shape) is named only in the skill (Task 3), not the provider-neutral contract; the contract stays mechanism-agnostic.
- Produces: the normative requirements the skill (Task 3) and packets doc (Task 4) reference.

- [ ] **Step 1: Add the Workspace-isolation subsection to Phase 4 (§6)**

At the end of section `## 6. Phase 4 — Bound & execute`, after the existing final bullet (the `scoped-sequential-prs` / `fork-pr-flow` one), append:

```markdown

### Workspace isolation (authorized repository-mutating passes)

Before the first repository mutation of an *authorized* pass, isolate the
work in a dedicated worktree:

1. Inspect repository and worktree state.
2. Fetch `origin`.
3. Resolve `origin/main` (or a repo-mandated base) to a commit SHA — the base
   is the freshly-fetched remote tip, never a possibly-stale local `main`.
4. Create the objective branch from that exact SHA.
5. Create a dedicated worktree for that branch; perform all objective-related
   mutations inside it, leaving the primary checkout and unrelated worktrees
   untouched.

Record the worktree path, branch, base ref, and base SHA as closeout evidence
(§9; `docs/delegated-implementation-packets.md` §10).

Fail closed and report — never improvise — when `origin` or `origin/main` is
unavailable, the intended branch already exists with incompatible state, the
worktree path is occupied or ambiguous, repository instructions require a
different base branch, or the task cannot safely be isolated.

**Read-only and plan-only passes are exempt.** A pass whose Phase-2
deliverable is `analysis`, or whose delegation profile is Review or Research
(`docs/delegation-profiles.md`), creates no branch or worktree — isolation is
a precondition of *mutating* work, not a ritual applied to every pass.
```

- [ ] **Step 2: Add the Deliverable-disposition subsection to Phase 6 (§8)**

At the end of section `## 8. Phase 6 — Close out honestly`, after the existing final bullet (the "adjacent work noticed" one), append:

```markdown

### Deliverable disposition

Once Phase 5's verification state is known, stop at a single contextual
decision on how the deliverable should proceed. The decision offers only the
actions actually valid for this deliverable and state — not the full universe
of git/GitHub actions — derived from: the deliverable named in Phase 2, the
real implementation and verification state, existing PR/issue state, the
explicit mutation authority already granted (Section 2), and repository
instructions. Mark the recommended action when there is a clear one; ask a
follow-up only when the chosen action genuinely needs one (draft vs. ready
PR; close with or without a comment).

**No answer means:** leave the deliverable in its current state; perform no
push, PR creation, issue mutation, merge, close, release, or publication; and
report that disposition remains undecided. This is the two-authority
invariant at its decision point — the specific external grant is *requested*
here, never assumed.

Prefer a concise explanatory comment when closing an issue; permit no-comment
closure only when the user explicitly chooses it, or there is genuinely no
useful explanation to preserve.
```

- [ ] **Step 3: Add workspace provenance to the state vocabulary (§9)**

At the end of section `## 9. State vocabulary`, after the deliverable-states list, append:

```markdown

**Workspace provenance** (recorded for every authorized repository-mutating
pass): the worktree path, branch, base ref, and base SHA the pass ran in —
carried into closeout evidence per `docs/delegated-implementation-packets.md`
§10. It is what makes "the base was `origin/main`" checkable rather than
narrated.
```

- [ ] **Step 4: Update the provider mapping table (§10)**

In the `## 10. Provider mapping` table, replace the Phase 4 and Phase 6 rows to name the new mechanisms. Phase 4 row — append to the Claude cell `; isolates the pass via bin/objective-worktree.sh` and to the Codex/human cell `; creates the worktree with git worktree add from the fetched origin/main SHA`. Phase 6 row — append to the Claude cell `; the deliverable-disposition decision is one AskUserQuestion` and to the Codex/human cell `; the disposition decision is a literal prompt to the human`.

(Edit the two existing table rows in place; do not add new rows. Keep the pipe-column count identical to the other rows.)

- [ ] **Step 5: Run `make check`**

Run: `make check`
Expected: all pass — in particular `links` (all cross-doc refs are inline-code or repo-relative and resolve) and `Claude frontmatter`.

- [ ] **Step 6: Commit**

```bash
git add docs/workflows/issue-work-loop.md
git commit -m "docs: add workspace-isolation and deliverable-disposition gates to the issue work loop contract"
```

---

### Task 3: Extend the Claude adapter skill (Phase 4 + Phase 6 bullets)

**Files:**
- Modify: `skills/issue-work-loop/SKILL.md` (phase 4 bullet, phase 6 bullet)

**Interfaces:**
- Consumes: the helper verdict-token contract (Task 1) and the contract's two new subsections (Task 2).
- Produces: the Claude-native invocation named in the pressure tests (Task 5).

- [ ] **Step 1: Append the isolation instruction to the Phase 4 bullet**

In `## The six phases`, at the end of item `4.` (the Bound & execute bullet, ending with the `fork-pr-flow` sentence), append this text inside the same bullet:

```markdown
   Before the first repository mutation of an authorized pass, isolate the
   work: run `bin/objective-worktree.sh <branch>` — it fetches `origin`,
   resolves `origin/main` (or a `--base` ref) to a SHA, and creates the
   objective branch plus a dedicated worktree at that exact SHA. Do all
   mutation inside that worktree, leaving the primary checkout untouched.
   Read the emitted `READY: <path> <branch> <base-ref> <base-sha>` line and
   record those four provenance fields for close-out; on a `BLOCKED:` or
   `ERROR:` token, stop and report — never improvise the base or claim it was
   fresh. A read-only or plan-only pass (Phase-2 deliverable `analysis`, or a
   Review/Research profile) creates no worktree.
```

- [ ] **Step 2: Append the disposition instruction to the Phase 6 bullet**

At the end of item `6.` (Close out honestly), append this text inside the same bullet:

```markdown
   After verification, stop at the deliverable-disposition decision: present
   one `AskUserQuestion` whose options are only the actions valid for this
   deliverable and state — derived from the Phase-2 deliverable, the real
   verification state, existing PR/issue state, and the explicit authority
   granted — with the recommended action marked and a follow-up only when the
   choice genuinely needs one (draft vs. ready PR; close with or without a
   comment). No answer = leave the deliverable as-is, perform no external
   mutation, and report disposition undecided. Prefer an explanatory comment
   on issue closure; allow no-comment closure only on an explicit choice.
```

- [ ] **Step 3: Add a red-flag line (optional but recommended)**

In `## Boundaries / red flags`, add a bullet:

```markdown
- Do not skip the Phase-4 worktree isolation for a mutating pass, and do not
  claim the base was `origin/main` without the helper's emitted base SHA — a
  narrated base is not a verified one.
```

- [ ] **Step 4: Run `make check`**

Run: `make check`
Expected: all pass — the skill's frontmatter is unchanged, only body prose was added; no `docs/skill-portability-audit.md` row change is needed (the skill's existing row already covers it; its maturity/status is not altered by adding phase detail).

- [ ] **Step 5: Commit**

```bash
git add skills/issue-work-loop/SKILL.md
git commit -m "docs: teach the issue-work-loop skill the isolation + disposition gates"
```

---

### Task 4: Add workspace provenance to delegated-implementation-packets

**Files:**
- Modify: `docs/delegated-implementation-packets.md` (§2 Preflight prose, §10 Closeout evidence prose, the reusable template)

**Interfaces:**
- Consumes: the provenance fields defined in Task 1 (path, branch, base ref, base SHA) and referenced by Task 2's §9.
- Produces: nothing downstream — this is the closeout-evidence surface the gates require.

- [ ] **Step 1: Extend the §2 Preflight description**

In `## The ten sections`, item `2. **Preflight**`, add to its sentence (after "the PR base is correct") the clause:

```markdown
; and, for an authorized repository-mutating packet, that the work runs in a dedicated worktree whose branch is based on a freshly-resolved `origin/main` (or the mandated base) SHA, not a stale local `main`
```

- [ ] **Step 2: Extend the §10 Closeout evidence description**

In item `10. **Closeout evidence**`, add to its list of what the worker returns (after "the final diff or repository state"):

```markdown
, the workspace provenance (the worktree path, branch, base ref, and base SHA the work ran in),
```

- [ ] **Step 3: Extend the reusable template's Preflight section**

In the `### Preflight` block of the `## Reusable template`, add a line:

```markdown
- For a mutating packet: work runs in a dedicated worktree; branch based on a fresh `origin/main` (or `<base>`) SHA `<sha>`, not stale local `main`.
```

- [ ] **Step 4: Extend the reusable template's Closeout evidence section**

In the `### Closeout evidence` block, add a line:

```markdown
- Workspace provenance: worktree `<path>`, branch `<branch>`, base ref `<ref>`, base SHA `<sha>`.
```

- [ ] **Step 5: Run `make check`**

Run: `make check`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add docs/delegated-implementation-packets.md
git commit -m "docs: expose worktree provenance in packet preflight + closeout evidence"
```

---

### Task 5: Pressure tests — record all 12, run the judgment reps

**Files:**
- Create: `skills/issue-work-loop/PRESSURE-TESTS.md`

**Interfaces:**
- Consumes: the shell fixture from Task 1 (covers PT 1, 2, 4, 12) and the skill behavior from Tasks 2–4 (covers PT 3, 5–11).

- [ ] **Step 1: Write the pressure-test record**

Create `skills/issue-work-loop/PRESSURE-TESTS.md`, following the structure of `skills/scoped-sequential-prs/PRESSURE-TESTS.md`. Record all 12 scenarios, each with: what it verifies, how it is verified (shell fixture vs. subagent rep), and its result. For the four mechanics scenarios, cite `bin/test-objective-worktree.sh` cases 1, 2, 3/4, 8 respectively. For the eight judgment scenarios, describe the fixture-repo setup and the transcript-grep grading.

```markdown
# issue-work-loop — pressure tests

Two families: **mechanics** (the isolation helper's git logic — deterministic
shell fixtures in `bin/test-objective-worktree.sh`) and **judgment** (the
skill's Phase-4 exemption and Phase-6 disposition shaping — fresh-subagent
reps in throwaway fixtures, graded on the filesystem and a transcript grep
for the real tool calls, never the agent's self-report).

| # | Scenario | Family | Verified by | Result |
|---|---|---|---|---|
| 1 | Mutating issue → worktree from fresh `origin/main` SHA even when local main is stale | mechanics | `bin/test-objective-worktree.sh` case 1 | <fill on run> |
| 2 | Dirty primary checkout untouched | mechanics | case 2 | <fill on run> |
| 3 | Read-only investigation creates no branch/worktree | judgment | subagent rep | <fill on run> |
| 4 | Existing incompatible branch / occupied worktree fails closed | mechanics | cases 3, 4 | <fill on run> |
| 5 | Completed local patch offers local/commit/PR choices, not issue-review choices | judgment | subagent rep | <fill on run> |
| 6 | Completed issue impl, green checks, no PR → offers issue-comment + PR options | judgment | subagent rep | <fill on run> |
| 7 | Existing PR → decision offers update/link that PR, not a duplicate | judgment | subagent rep | <fill on run> |
| 8 | Failed verification does not offer issue closure as a normal completion action | judgment | subagent rep | <fill on run> |
| 9 | No interactive response → no external mutation | judgment | subagent rep | <fill on run> |
| 10 | Issue closure prefers an explanatory comment; honors explicit no-comment | judgment | subagent rep | <fill on run> |
| 11 | Implementation permission alone never enables push/PR/comment/close/merge/release | judgment | subagent rep | <fill on run> |
| 12 | Worktree branch, path, base ref, base SHA appear in closeout evidence | mechanics | case 8 | <fill on run> |
```

- [ ] **Step 2: Run the mechanics family**

Run: `bin/test-objective-worktree.sh`
Expected: `9 passed, 0 failed`. Fill results for PT 1, 2, 4, 12 in the table.

- [ ] **Step 3: Run the judgment family (subagent reps)**

For each judgment scenario (3, 5–11), dispatch a fresh general-purpose subagent into a throwaway fixture repo copy (its own copy per rep — shared dirs collide), give it the fixture state (e.g. "green checks, no PR, issue #N open, implementation authority only") and the issue-work-loop skill, and instruct it through Phase 6. Grade on the transcript: grep `tasks/<id>.output` for the real `AskUserQuestion` tool-use and inspect its options — confirm the offered set matches the scenario's expectation (e.g. PT8: no "close issue" option present; PT9: no `gh`/`git push` tool-use when no answer is given; PT11: no external-mutation tool-use under implementation-only authority). Record pass/fail per rep, scoring the transcript + filesystem, not the self-report. Aim for ~5 reps per scenario per the repo's pressure-test method.

Note any scenario that cannot be faithfully driven by a subagent (e.g. PT9/PT10 hinge on the live `AskUserQuestion` round-trip a subagent mis-routes) and record the caveat + the injection method used, per the repo's precedent for pressure-testing `AskUserQuestion`-gated behavior.

- [ ] **Step 4: Fill results and commit**

Fill every `<fill on run>` cell with the real outcome. If any judgment scenario reveals the skill prose is ambiguous, fix `skills/issue-work-loop/SKILL.md` (re-run `make check`) before recording GREEN.

```bash
git add skills/issue-work-loop/PRESSURE-TESTS.md skills/issue-work-loop/SKILL.md
git commit -m "test: pressure tests for the isolation + disposition gates"
```

- [ ] **Step 5: Classify the plan doc in the inventory**

Add a `not_a_capability` row for this plan (mirroring the spec's row already at the end of the ledger):

```json
    {
      "path": "docs/superpowers/plans/2026-07-15-objective-isolation-disposition.md",
      "reason": "a point-in-time implementation plan for the objective-isolation + deliverable-disposition gates, paired with its design spec; planning artifact, not itself a capability."
    }
```

Run: `make check` → `capability inventory OK`. Then:

```bash
git add docs/superpowers/plans/2026-07-15-objective-isolation-disposition.md capabilities.json
git commit -m "docs: implementation plan for objective isolation & disposition gates"
```

(If executing via subagent-driven-development, this plan doc is committed at the start of execution instead — do it wherever it first needs to be tracked; the inventory row is required either way.)

---

## Self-Review

**Spec coverage** (checked against `…-objective-isolation-disposition-design.md`):
- §4 objective-isolation gate → Task 2 Step 1 (contract) + Task 3 Step 1 (skill) + Task 1 (helper). ✓
- §4.2 helper interface + honesty (emitted base SHA) → Task 1 Steps 4, and asserted in Task 1 cases 1 + 8 (PT1, PT12). ✓
- §4.1 fail-closed conditions → Task 1 cases 3–6 + helper `BLOCKED/ERROR` branches. ✓
- §4.1 read-only exemption → Task 2 Step 1 + Task 3 Step 1 + PT3 (Task 5). ✓
- §5 deliverable-disposition gate → Task 2 Step 2 (contract) + Task 3 Step 2 (skill) + PT 5–11 (Task 5). ✓
- §5 no-answer semantics → Task 2 Step 2 + Task 3 Step 2 + PT9. ✓
- §5 closure-comment preference → Task 2 Step 2 + Task 3 Step 2 + PT10. ✓
- §6 closeout provenance → Task 2 Step 3 (§9) + Task 4 (packets §2/§10/template) + PT12. ✓
- §7 file plan → Tasks 1–5 touch exactly the listed files; nothing in the "not touched" set is modified. ✓
- §8 all 12 pressure tests → Task 5 table + Task 1 fixture. ✓
- Inventory obligations (helper `script` row, spec + plan `not_a_capability` rows, `version_introduced 0.6.0`) → Task 1 Step 9, spec already committed, Task 5 Step 5. ✓

**Placeholder scan:** the only `<fill on run>` markers are in the PRESSURE-TESTS table and are intentional — they are filled by Task 5 Steps 2–4 when the tests actually run (a results record cannot be pre-filled honestly). No code/prose step is left as TODO.

**Type consistency:** the verdict-token grammar `READY: <path> <branch> <base-ref> <base-sha>` and the four `BLOCKED:` tokens are identical across the helper source (Task 1 Step 4), the test assertions (Task 1 Step 2), the capabilities description (Task 1 Step 9), the contract §10 note (Task 2 Step 4), and the skill bullet (Task 3 Step 1). Exit codes `0/10/1/64` are consistent throughout.
