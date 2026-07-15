# session-end land-on-main Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/session-end`, as its final step, leave the repo on `main`
fast-forwarded to `origin/main` — but only when lossless — via a tested
`bin/session-end-land.sh` helper.

**Architecture:** A read-only-by-default bash helper inspects git state and
either performs a safe switch-to-main + `--ff-only` merge or prints a blocking
reason (mutating nothing). The `/session-end` command runs it as its last step
and renders the verdict. All safety logic lives in the helper so it can be
tested deterministically in fixture repos.

**Tech Stack:** bash (`#!/usr/bin/env bash`, `set -uo pipefail`), git,
pre-commit, GNU Make. Markdown for command/skill/changelog edits. Inventory
reconciled by `bin/check-inventory.py` (`capabilities.json`).

## Global Constraints

- `make check` must be green before every commit; never `--no-verify`, never
  commit to `main` (a `no-commit-to-branch` hook enforces this). Work lands on
  branch `feature/session-end-land-on-main`, PR to `main`.
- A new `bin/*.sh` helper must be classified in `capabilities.json` (a
  `not_a_capability` ledger row) or `make check` fails. `bin/test-*.sh` is
  auto-excluded (regex at `bin/check-inventory.py:346`) — no row needed for the
  test.
- In command/skill *prose* (inline code), reference Bindle-root scripts as
  `<bindle>/bin/session-end-land.sh` — a bare `bin/session-end-land.sh` in
  prose fails the Bindle-root-path-refs check in `bin/check.sh`.
- A new `bin/test-*.sh` must be wired in TWO places: the `test:` target in
  `Makefile` and a `local` hook in `.pre-commit-config.yaml`.
- New shell must pass `shellcheck` and `shfmt` (both run by `make check`).

---

### Task 1: The tested landing helper

**Files:**
- Create: `bin/session-end-land.sh`
- Create: `bin/test-session-end-land.sh`
- Modify: `Makefile` (add to `test:` target)
- Modify: `.pre-commit-config.yaml` (add a `local` hook)
- Modify: `capabilities.json` (one `not_a_capability` row for the helper)

**Interfaces:**
- Produces: `bin/session-end-land.sh [--check] [--no-fetch]`. First stdout line
  is a verdict token: `SAFE` | `BLOCKED: dirty-tree` | `BLOCKED: branch-unmerged`
  | `BLOCKED: main-diverged` | `BLOCKED: detached-head` | `ERROR: <reason>`.
  Exit codes: `0` SAFE (landed, or would-land under `--check`), `10` BLOCKED,
  `1` ERROR, `64` usage error. On SAFE without `--check` it switches to `main`
  and runs `git merge --ff-only origin/main`, then prints `git branch -d <b>`
  suggestions for merged local branches (never deletes). Task 2 consumes this.

- [ ] **Step 1: Write the failing test**

Create `bin/test-session-end-land.sh` with exactly this content:

```bash
#!/usr/bin/env bash
#
# test-session-end-land.sh — exercise bin/session-end-land.sh against throwaway
# git fixtures, each with a bare `origin` remote so origin/main comparisons work
# offline. Never touches the network or a real repo.
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAND="$REPO_ROOT/bin/session-end-land.sh"

pass=0 fail=0
ok() {
  printf '  \342\234\223 %s\n' "$1"
  pass=$((pass + 1))
}
bad() {
  printf '  \342\234\227 %s\n' "$1"
  fail=$((fail + 1))
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cfg() { # cfg <repo> — deterministic identity
  git -C "$1" config user.email t@e.st
  git -C "$1" config user.name t
}

# new_fixture <tag> — bare origin seeded with a `main` containing one commit;
# clone it and echo the clone's path (has `origin` remote + origin/main).
new_fixture() {
  local tag="$1" up="$TMP/up.$1" seed="$TMP/seed.$1" repo="$TMP/repo.$1"
  git init -q --bare "$up"
  git init -q "$seed"
  cfg "$seed"
  git -C "$seed" checkout -q -b main
  : >"$seed/base"
  git -C "$seed" add base
  git -C "$seed" commit -qm base
  git -C "$seed" remote add origin "$up"
  git -C "$seed" push -q origin main
  git clone -q "$up" "$repo"
  cfg "$repo"
  echo "$repo"
}

# run <repo> [args...] — sets $code and $out from the helper
run() {
  local repo="$1"
  shift
  out="$(cd "$repo" && "$LAND" "$@" 2>&1)"
  code=$?
}

# --- SAFE: on a merged feature branch -> lands on main, reports deletable ---
R="$(new_fixture merged)"
git -C "$R" switch -q -c feature
echo x >"$R/x"
git -C "$R" add x
git -C "$R" commit -qm "feat: x"
git -C "$R" switch -q main
git -C "$R" merge -q --ff-only feature
git -C "$R" push -q origin main
git -C "$R" switch -q feature # end the "session" on the merged branch
run "$R"
[ "$code" -eq 0 ] && head -1 <<<"$out" | grep -qx "SAFE" \
  && ok "merged branch -> SAFE exit 0" || bad "merged branch verdict ($code): $out"
[ "$(git -C "$R" branch --show-current)" = "main" ] \
  && ok "merged branch -> landed on main" || bad "merged branch not on main"
grep -q "git branch -d feature" <<<"$out" \
  && ok "merged branch reported safe-to-delete" || bad "no delete suggestion: $out"
git -C "$R" rev-parse --verify -q feature >/dev/null \
  && ok "merged branch not actually deleted" || bad "branch was deleted"

# --- SAFE: local main behind origin/main -> fast-forwards ---
R="$(new_fixture behind)"
# advance origin/main via a second clone, leaving R's main behind
git clone -q "$TMP/up.behind" "$TMP/other.behind"
cfg "$TMP/other.behind"
echo y >"$TMP/other.behind/y"
git -C "$TMP/other.behind" add y
git -C "$TMP/other.behind" commit -qm "feat: y"
git -C "$TMP/other.behind" push -q origin main
run "$R" # helper fetches, then ff
[ "$code" -eq 0 ] && head -1 <<<"$out" | grep -qx "SAFE" \
  && ok "behind main -> SAFE exit 0" || bad "behind verdict ($code): $out"
git -C "$R" merge-base --is-ancestor origin/main main \
  && ok "behind main -> fast-forwarded" || bad "behind main not ff'd"

# --- SAFE: already on clean up-to-date main -> no-op ---
R="$(new_fixture clean)"
run "$R"
[ "$code" -eq 0 ] && head -1 <<<"$out" | grep -qx "SAFE" \
  && ok "clean main -> SAFE no-op" || bad "clean main verdict ($code): $out"

# --- BLOCKED: dirty tree -> no mutation ---
R="$(new_fixture dirty)"
echo mut >>"$R/base" # modify a tracked file
run "$R"
[ "$code" -eq 10 ] && head -1 <<<"$out" | grep -qx "BLOCKED: dirty-tree" \
  && ok "dirty tree -> BLOCKED exit 10" || bad "dirty verdict ($code): $out"
git -C "$R" diff --quiet || dirty_kept=1
[ "${dirty_kept:-0}" = 1 ] && ok "dirty tree -> changes untouched" || bad "dirty change lost"

# --- BLOCKED: unmerged branch -> no mutation, stays on branch ---
R="$(new_fixture unmerged)"
git -C "$R" switch -q -c feature
echo z >"$R/z"
git -C "$R" add z
git -C "$R" commit -qm "feat: z" # never merged to origin/main
run "$R"
[ "$code" -eq 10 ] && head -1 <<<"$out" | grep -qx "BLOCKED: branch-unmerged" \
  && ok "unmerged -> BLOCKED exit 10" || bad "unmerged verdict ($code): $out"
[ "$(git -C "$R" branch --show-current)" = "feature" ] \
  && ok "unmerged -> stayed on feature" || bad "unmerged switched away"

# --- BLOCKED: local main diverged (local-only commit) -> no mutation ---
R="$(new_fixture diverged)"
echo d >"$R/d"
git -C "$R" add d
git -C "$R" commit -qm "local: d" # on main, not pushed
run "$R"
[ "$code" -eq 10 ] && head -1 <<<"$out" | grep -qx "BLOCKED: main-diverged" \
  && ok "diverged -> BLOCKED exit 10" || bad "diverged verdict ($code): $out"

# --- --check on a SAFE case -> verdict only, no mutation ---
R="$(new_fixture check)"
git clone -q "$TMP/up.check" "$TMP/other.check"
cfg "$TMP/other.check"
echo c >"$TMP/other.check/c"
git -C "$TMP/other.check" add c
git -C "$TMP/other.check" commit -qm "feat: c"
git -C "$TMP/other.check" push -q origin main
before="$(git -C "$R" rev-parse HEAD)"
run "$R" --check
[ "$code" -eq 0 ] && head -1 <<<"$out" | grep -qx "SAFE" \
  && ok "--check -> SAFE exit 0" || bad "--check verdict ($code): $out"
[ "$(git -C "$R" rev-parse HEAD)" = "$before" ] \
  && ok "--check -> HEAD unchanged" || bad "--check mutated HEAD"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
```

Make it executable:

```bash
chmod +x bin/test-session-end-land.sh
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bin/test-session-end-land.sh`
Expected: FAIL — the helper does not exist yet, so `run` invokes a missing
`bin/session-end-land.sh`; the summary line reports failures and the script
exits non-zero.

- [ ] **Step 3: Write the helper**

Create `bin/session-end-land.sh` with exactly this content:

```bash
#!/usr/bin/env bash
#
# session-end-land.sh — leave the repo on clean, synced main, but only when
# lossless. Read-only inspection plus a fast-forward-only landing; never
# strands work. Run as the final step of /session-end.
#
# SAFE requires: a clean working tree (no tracked changes), the current branch
# already merged into origin/main (or already on main), and a local main that
# has not diverged from origin/main. When SAFE it switches to main and runs
# `git merge --ff-only origin/main`, then reports any fully-merged local
# branches as safe-to-delete (it never deletes them). Otherwise it mutates
# nothing and prints the blocking reason.
#
# Usage: bin/session-end-land.sh [--check] [--no-fetch]
#   --check     inspect and print the verdict only; never mutate.
#   --no-fetch  skip the best-effort `git fetch origin` (caller already fetched).
#
# Output: first stdout line is a machine-readable verdict token —
#   SAFE                     landed (or, with --check, would land)
#   BLOCKED: dirty-tree      uncommitted/staged tracked changes
#   BLOCKED: branch-unmerged current branch has commits not in origin/main
#   BLOCKED: main-diverged   local main has commits not in origin/main
#   BLOCKED: detached-head   HEAD is detached; no branch to reason about
#   ERROR: <reason>          not a git repo, no origin, or no origin/main
# followed by human-readable detail and any proposed commands.
#
# Exit codes:
#   0   SAFE (landed, or would-land under --check)
#   10  BLOCKED (a normal, expected outcome — not an error)
#   1   ERROR (environment problem)
#   64  usage error
#
set -uo pipefail

CHECK=0
FETCH=1
while [ $# -gt 0 ]; do
  case "$1" in
    -h | --help)
      awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
      exit 0
      ;;
    --check) CHECK=1 ;;
    --no-fetch) FETCH=0 ;;
    *)
      echo "session-end-land.sh: unknown argument '$1'" >&2
      exit 64
      ;;
  esac
  shift
done

MAIN="main"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: not a git repository"
  exit 1
fi
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: no 'origin' remote"
  exit 1
fi

if [ "$FETCH" -eq 1 ]; then
  git fetch origin --quiet 2>/dev/null \
    || echo "warning: git fetch origin failed; comparing against stale origin/$MAIN" >&2
fi

if ! git rev-parse --verify --quiet "origin/$MAIN" >/dev/null; then
  echo "ERROR: origin/$MAIN not found"
  exit 1
fi

cur="$(git branch --show-current)"
if [ -z "$cur" ]; then
  echo "BLOCKED: detached-head"
  echo "  HEAD is detached — check out a branch before ending the session."
  exit 10
fi

# dirty = any staged/unstaged change to a TRACKED file (untracked ?? ignored)
dirty="$(git status --porcelain --untracked-files=no)"
if [ -n "$dirty" ]; then
  echo "BLOCKED: dirty-tree"
  echo "  Uncommitted changes to tracked files — commit or stash first:"
  sed 's/^/    /' <<<"$dirty"
  exit 10
fi

# local main diverged from origin/main? (only if a local main exists)
if git rev-parse --verify --quiet "$MAIN" >/dev/null; then
  ahead_main="$(git rev-list --count "origin/$MAIN..$MAIN")"
  if [ "$ahead_main" -gt 0 ]; then
    echo "BLOCKED: main-diverged"
    echo "  Local $MAIN has $ahead_main commit(s) not on origin/$MAIN — resolve before landing."
    exit 10
  fi
fi

# current branch merged into origin/main? (trivially true when already on main)
if [ "$cur" != "$MAIN" ]; then
  if ! git merge-base --is-ancestor HEAD "origin/$MAIN"; then
    ahead="$(git rev-list --count "origin/$MAIN..HEAD")"
    echo "BLOCKED: branch-unmerged"
    echo "  Branch '$cur' has $ahead commit(s) not in origin/$MAIN."
    echo "  Merge its PR (or push and open one) before landing on $MAIN."
    exit 10
  fi
fi

# --- SAFE ---
if [ "$CHECK" -eq 1 ]; then
  echo "SAFE"
  if [ "$cur" != "$MAIN" ]; then
    echo "  Would switch $cur -> $MAIN and fast-forward to origin/$MAIN."
  else
    echo "  Would fast-forward $MAIN to origin/$MAIN (or already up to date)."
  fi
  exit 0
fi

if [ "$cur" != "$MAIN" ]; then
  git switch "$MAIN" --quiet
fi
git merge --ff-only "origin/$MAIN" --quiet

echo "SAFE"
echo "  On $MAIN, up to date with origin/$MAIN."
deletable="$(git branch --merged "origin/$MAIN" --format '%(refname:short)' | grep -vx "$MAIN" || true)"
if [ -n "$deletable" ]; then
  echo "  Merged local branch(es) safe to delete (not deleted):"
  while IFS= read -r b; do
    [ -n "$b" ] && echo "    git branch -d $b"
  done <<<"$deletable"
fi
exit 0
```

Make it executable:

```bash
chmod +x bin/session-end-land.sh
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bin/test-session-end-land.sh`
Expected: PASS — final line `N passed, 0 failed`, exit 0.

- [ ] **Step 5: Wire the test into the Makefile**

In `Makefile`, add the new test to the `test:` target's command list (append
after `bin/test-release-evidence.sh`):

```make
	bin/test-session-end-land.sh
```

- [ ] **Step 6: Wire the test into pre-commit**

In `.pre-commit-config.yaml`, add a `local` hook alongside the other
`test-*.sh` hooks (mirror the `bindle-test-issue-dedup-scan` block exactly):

```yaml
      - id: bindle-test-session-end-land
        name: session-end-land.sh helper tests
        entry: bin/test-session-end-land.sh
        language: script
        pass_filenames: false
        always_run: true
```

- [ ] **Step 7: Add the inventory ledger row for the helper**

In `capabilities.json`, add a `not_a_capability` entry for the helper (the test
is auto-excluded). Append after the last existing ledger entry:

```json
    {
      "path": "bin/session-end-land.sh",
      "reason": "a git-state helper for /session-end that lands the repo on clean, synced main when lossless; operational tooling, not itself an installed capability."
    }
```

- [ ] **Step 8: Run the full gate**

Run: `make check`
Expected: all checks pass, including `capability inventory OK` (now one more
ledgered exclusion) and the new `session-end-land.sh helper tests` hook.

- [ ] **Step 9: Commit**

```bash
git add bin/session-end-land.sh bin/test-session-end-land.sh Makefile \
  .pre-commit-config.yaml capabilities.json
git commit -m "feat: session-end-land.sh — safe land-on-main helper"
```

---

### Task 2: Wire the helper into `/session-end` and reconcile the read-only rule

**Files:**
- Modify: `commands/session-end.md` (add the final landing step)
- Modify: `skills/session-continuity/SKILL.md` (Rule 1 carve-out)
- Modify: `CHANGELOG.md` (Unreleased entry)

**Interfaces:**
- Consumes: `bin/session-end-land.sh` verdict tokens and exit codes from Task 1.

- [ ] **Step 1: Add the landing step to the command**

In `commands/session-end.md`, insert a new numbered step immediately after
step 6 (the privacy pass) and before the final "Reply with the note's full
path…" paragraph. `allowed-tools` is left unchanged — the helper follows the
`<bindle>/bin/slugify.sh` precedent (Bindle tools run ad hoc, not pre-listed).
Insert:

```markdown
7. Land the repo on clean `main` — do this **last**, after the note is written
   and the privacy pass, so the note captured the branch context before HEAD
   moves. Run `<bindle>/bin/session-end-land.sh` (your Bindle checkout's copy;
   it operates on the current working repo). It is attempt-if-safe: it switches
   to `main` and fast-forwards it to `origin/main` only when lossless, and
   otherwise mutates nothing. Render its verdict into your reply and fold the
   outcome into the note's **decisions**:
   - **SAFE** → it landed; report the final state and pass along any
     `git branch -d <branch>` suggestions it printed for merged local branches
     — relay them, never run them yourself.
   - **BLOCKED: <reason>** → nothing changed; relay the blocker (dirty tree,
     unmerged branch, diverged `main`, or detached HEAD) and the remediation it
     proposed, so the operator can resolve it. Do not try to force the landing.
   - **ERROR** → not a git repo / no `origin`; report it and move on.
```

- [ ] **Step 2: Carve out the read-only rule**

In `skills/session-continuity/SKILL.md`, find Rule 1 under `## Rules`:

```markdown
1. **Read-only toward the project repo.** Starting or ending a session, or
   writing a handoff, must not modify the repo being worked on. The only
   exception: the user *explicitly* asks for content in the repo (a
   `/project-profile` export, or "put the session summary in the repo/PR"). An
   explicit request is honored — but only via the **Repo-bound content** recipe
   below, never by writing the raw note into the repo.
```

Replace it with (adds the built-in landing exception):

```markdown
1. **Read-only toward the project repo.** Starting or ending a session, or
   writing a handoff, must not modify the repo being worked on. One built-in
   exception applies to `/session-end` only: as its final step it may switch to
   `main` and fast-forward it to `origin/main` — a lossless navigation that
   creates, modifies, or deletes no tracked file and makes no commit, done only
   when safe and otherwise reported as a blocker (see the session-end command).
   The other exception is content: the user *explicitly* asks for it in the
   repo (a `/project-profile` export, or "put the session summary in the
   repo/PR"). An explicit request is honored — but only via the **Repo-bound
   content** recipe below, never by writing the raw note into the repo.
```

- [ ] **Step 3: Add a CHANGELOG entry**

In `CHANGELOG.md`, under the `## [Unreleased]` heading (create an `### Added`
subsection if the section conventions use one; match the file's existing
style), add:

```markdown
- `/session-end` now lands the repo on clean, synced `main` as its final step
  when lossless (new `bin/session-end-land.sh`), reporting a blocker instead of
  forcing when work would be stranded.
```

- [ ] **Step 4: Run the full gate**

Run: `make check`
Expected: all checks pass (frontmatter, links, Bindle-root path refs,
inventory, private-info).

- [ ] **Step 5: Commit**

```bash
git add commands/session-end.md skills/session-continuity/SKILL.md CHANGELOG.md
git commit -m "feat: /session-end lands on clean main as its final step"
```

---

## Notes for the implementer

- After both tasks, the branch is ready for a PR to `main`. Do **not** merge or
  push unless the operator asks (repo discipline; operator handles pushes).
- Manual end-to-end smoke (optional, on this repo): from a merged feature
  branch run `<bindle>/bin/session-end-land.sh --check` and confirm it prints
  `SAFE` and a "would switch" line without moving HEAD.
- The `--check` flag exists for that dry-run and for the test; the command
  itself calls the helper without `--check` so it actually lands.
