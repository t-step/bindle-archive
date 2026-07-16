# release-please-sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `VERSION` and `RELEASE-MANIFEST.json` in sync with the Release
Please release PR automatically, with no manual step (issue #137).

**Architecture:** A new local script, `bin/release-please-sync.sh`, runs as
the step immediately after `bin/release-strategy.sh apply`. It finds the
open Release Please release PR (by its `autorelease: pending` label), reads
the version RP already computed from that branch's
`.release-please-manifest.json`, and — in an isolated `git worktree` — writes
`VERSION`, regenerates `RELEASE-MANIFEST.json` via the existing
`bin/release-manifest.py`, commits, and pushes onto the *same* PR branch. It
never creates a new PR, never touches `main`, never tags, merges, or
publishes.

**Tech Stack:** bash (`set -euo pipefail`), `gh` CLI, `git worktree`,
`python3` (stdlib only, reusing `bin/release-manifest.py`).

## Global Constraints

- Never commit to `main` — work stays on branch `fix/137-release-please-sync`
  (already checked out); `make check` must pass before every commit.
- `bin/release-please-sync.sh` never touches `main`, never tags, merges,
  publishes, or deploys — its only mutation is a commit + push onto the
  already-open Release Please PR branch.
- No dependency on GitHub Actions — everything here runs locally (GH Actions
  is currently billing-blocked in this repo; see the design spec).
- No rename of `VERSION` → `version.txt`; no changes to the ~9 existing
  `VERSION` readers (`bin/check.sh`, `bin/check-inventory.py`,
  `bin/doctor.sh`, `bin/install.sh`, `bin/new.sh`, `bin/release-evidence.py`,
  `bin/release.sh`, `bin/release-strategies/local-release-please.sh`).
- New `bin/*.sh` scripts and new `docs/**/*.md` files must be classified in
  `capabilities.json` (a `capabilities` row or a `not_a_capability` ledger
  entry) or `make check` fails.
- Design reference: `docs/superpowers/specs/2026-07-15-release-please-sync-design.md`.

---

### Task 1: Ignore `.worktrees/`

**Files:**
- Modify: `.gitignore`

**Interfaces:** None — standalone config change.

- [ ] **Step 1: Add the ignore rule**

Open `.gitignore` and append this block at the end of the file:

```gitignore

# Scratch git worktrees created by release tooling (bin/release-please-sync.sh)
# and ad hoc local work — never committed.
.worktrees/
```

- [ ] **Step 2: Verify it's picked up**

Run: `git status --short`
Expected: the existing `?? .worktrees/` line disappears from the output
(there is already an untracked `.worktrees/` directory left over from prior
work in this repo — confirm it no longer shows as untracked).

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .worktrees/ (used by release-please-sync)"
```

---

### Task 2: Drop the dead `VERSION` extra-files entry

**Files:**
- Modify: `release-please-config.json`

**Interfaces:** None — standalone config change. `bin/test-release-strategy.sh`
already asserts `release-type == "simple"` and
`include-component-in-tag is False` against this file, and does **not**
assert anything about `extra-files` — removing the key does not break that
test (verify in Step 2 below).

- [ ] **Step 1: Remove the no-op entry**

`release-please-config.json` currently reads:

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "include-component-in-tag": false,
  "packages": {
    ".": {
      "release-type": "simple",
      "changelog-path": "CHANGELOG.md",
      "extra-files": ["VERSION"]
    }
  }
}
```

Change it to:

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "include-component-in-tag": false,
  "packages": {
    ".": {
      "release-type": "simple",
      "changelog-path": "CHANGELOG.md"
    }
  }
}
```

(`extra-files: ["VERSION"]` never worked — Release Please's generic file
updater only rewrites lines carrying an `x-release-please-version`
annotation, and `VERSION` is a bare semver string with none. `bin/release-please-sync.sh`,
built in Task 3, replaces it.)

- [ ] **Step 2: Confirm the existing strategy test still passes**

Run: `bin/test-release-strategy.sh`
Expected: last line reads `... passed, 0 failed` (the config-shape assertion
near the end of that file does not reference `extra-files` and keeps passing).

- [ ] **Step 3: Commit**

```bash
git add release-please-config.json
git commit -m "fix: drop the no-op VERSION extra-files entry from release-please-config.json"
```

---

### Task 3: `bin/release-please-sync.sh` + its test suite

**Files:**
- Create: `bin/release-please-sync.sh`
- Create: `bin/test-release-please-sync.sh`

**Interfaces:**
- Produces: an executable `bin/release-please-sync.sh` with two verbs —
  `dry-run` (read-only) and `apply --approval-token <token>` (mutates: pushes
  a commit onto the open Release Please PR branch). Exit codes: `0` success/
  no-op, `2` unknown verb, `3` apply without a token, `4` `gh` not on `PATH`,
  `10` zero matching PRs, `11` more than one matching PR, nonzero (from
  `bin/check.sh`/`bin/test-install.sh`/`bin/release-manifest.py`) on a failed
  pre-push invariant check.

#### RED

- [ ] **Step 1: Write the test file**

Create `bin/test-release-please-sync.sh`:

```bash
#!/usr/bin/env bash
#
# test-release-please-sync.sh — exercise bin/release-please-sync.sh against a
# throwaway git fixture with a local bare "origin" and a stubbed gh CLI.
# Never touches the network or the real repo's git state.
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/release-please-sync.sh"

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

# build_fixture <work-dir> <check-exit-code> — a minimal Bindle-shaped repo
# pushed to a local bare "$work.bare", with a release-please PR branch that
# has bumped .release-please-manifest.json + CHANGELOG.md but left VERSION
# behind (the exact bug this script fixes).
build_fixture() {
  local work="$1" check_exit="$2"
  local bare="$work.bare"
  git init -q --bare "$bare"

  git init -q "$work"
  git -C "$work" config user.email t@e.st
  git -C "$work" config user.name t
  git -C "$work" checkout -q -b main
  git -C "$work" remote add origin "$bare"

  mkdir -p "$work/bin"
  cp "$REPO_ROOT/bin/release-manifest.py" "$work/bin/release-manifest.py"
  cat >"$work/bin/check.sh" <<SH
#!/usr/bin/env bash
exit $check_exit
SH
  chmod +x "$work/bin/check.sh"
  cat >"$work/bin/test-install.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  chmod +x "$work/bin/test-install.sh"

  cat >"$work/capabilities.json" <<'JSON'
{
  "capabilities": [
    {"name": "demo", "type": "skill", "path": "skills/demo",
     "description": "Demo.", "provider": {"claude": "installed", "codex": "untested"},
     "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"}
  ],
  "not_a_capability": []
}
JSON
  cat >"$work/install-manifest.tsv" <<'TSV'
# GENERATED from capabilities.json — do not edit; run 'make manifest'
claude	skill	demo	skills/demo	skills/demo
TSV
  cat >"$work/CHANGELOG.md" <<'MD'
# Changelog

## [0.1.0] - 2026-01-01

### Added

- Initial release.
MD
  printf '0.1.0\n' >"$work/VERSION"
  printf '{\n  ".": "0.1.0"\n}\n' >"$work/.release-please-manifest.json"

  git -C "$work" add -A
  git -C "$work" commit -q -m init
  git -C "$work" push -q origin main

  git -C "$work" checkout -q -b "release-please--branches--main"
  cat >"$work/CHANGELOG.md" <<'MD'
# Changelog

## [0.2.0] - 2026-02-01

### Added

- A new thing.

## [0.1.0] - 2026-01-01

### Added

- Initial release.
MD
  printf '{\n  ".": "0.2.0"\n}\n' >"$work/.release-please-manifest.json"
  git -C "$work" add -A
  git -C "$work" commit -q -m "chore(main): release 0.2.0"
  git -C "$work" push -q origin "release-please--branches--main"
  git -C "$work" checkout -q main
}

# gh_stub <dir> <pr-list-json> — a fake `gh` on PATH that answers `pr list`
# with the given JSON and refuses anything else.
gh_stub() {
  local dir="$1" json="$2"
  mkdir -p "$dir"
  printf '%s' "$json" >"$dir/pr-list-response.json"
  cat >"$dir/gh" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "pr" ] && [ "\$2" = "list" ]; then
  cat "$dir/pr-list-response.json"
  exit 0
fi
echo "unexpected gh invocation: \$*" >&2
exit 1
EOF
  chmod +x "$dir/gh"
}

# --- verb / token parsing: no fixture needed ---------------------------------
out="$("$SCRIPT" bogus 2>&1)"
code=$?
[ "$code" -eq 2 ] && ok "unknown verb -> exit 2" || bad "unknown verb ($code): $out"

out="$("$SCRIPT" apply 2>&1)"
code=$?
[ "$code" -eq 3 ] && ok "apply without token -> exit 3" || bad "apply-no-token ($code): $out"

# --- gh missing: hard stop before any git/PR activity ------------------------
WORK1="$TMP/work1"
build_fixture "$WORK1" 0

NOGH="$TMP/no-gh-path"
mkdir -p "$NOGH"
ln -sf "$(command -v git)" "$NOGH/git"
ln -sf "$(command -v python3)" "$NOGH/python3"
out="$(cd "$WORK1" && PATH="$NOGH" "$SCRIPT" dry-run 2>&1)"
code=$?
[ "$code" -eq 4 ] && ok "gh missing -> exit 4" || bad "gh missing ($code): $out"

GH1="$TMP/gh1"
gh_stub "$GH1" '[{"number":42,"headRefName":"release-please--branches--main","baseRefName":"main"}]'

# --- zero matching PRs --------------------------------------------------------
GH0="$TMP/gh0"
gh_stub "$GH0" '[]'
out="$(cd "$WORK1" && PATH="$GH0:$PATH" "$SCRIPT" dry-run 2>&1)"
code=$?
[ "$code" -eq 10 ] && ok "zero PRs -> exit 10" || bad "zero PRs ($code): $out"

# --- two matching PRs ----------------------------------------------------------
GH2="$TMP/gh2"
gh_stub "$GH2" '[{"number":1,"headRefName":"a","baseRefName":"main"},{"number":2,"headRefName":"b","baseRefName":"main"}]'
out="$(cd "$WORK1" && PATH="$GH2:$PATH" "$SCRIPT" dry-run 2>&1)"
code=$?
[ "$code" -eq 11 ] && ok "two PRs -> exit 11" || bad "two PRs ($code): $out"

# --- dry-run: reports the diff, mutates nothing -------------------------------
bare1_before="$(git -C "$WORK1.bare" show-ref)"
out="$(cd "$WORK1" && PATH="$GH1:$PATH" "$SCRIPT" dry-run 2>&1)"
code=$?
bare1_after="$(git -C "$WORK1.bare" show-ref)"
{
  [ "$code" -eq 0 ] &&
    printf '%s' "$out" | grep -q '0.1.0 -> 0.2.0' &&
    [ "$bare1_before" = "$bare1_after" ]
} &&
  ok "dry-run reports the diff and mutates nothing" ||
  bad "dry-run ($code): $out"

# --- apply without token, even with a real PR available ----------------------
out="$(cd "$WORK1" && PATH="$GH1:$PATH" "$SCRIPT" apply 2>&1)"
code=$?
[ "$code" -eq 3 ] && ok "apply without token (real fixture) -> exit 3" || bad "apply-no-token ($code): $out"

# --- apply, clean: VERSION + RELEASE-MANIFEST.json land on the head branch ---
out="$(cd "$WORK1" && PATH="$GH1:$PATH" "$SCRIPT" apply --approval-token eph-1 2>&1)"
code=$?
head_version="$(git -C "$WORK1.bare" show "release-please--branches--main:VERSION" 2>/dev/null || true)"
{
  [ "$code" -eq 0 ] &&
    [ "$head_version" = "0.2.0" ] &&
    git -C "$WORK1.bare" show "release-please--branches--main:RELEASE-MANIFEST.json" 2>/dev/null |
      grep -q '"version": "0.2.0"'
} &&
  ok "apply syncs VERSION + RELEASE-MANIFEST.json onto the PR branch" ||
  bad "apply ($code): $out; VERSION on branch = $head_version"

[ ! -d "$WORK1/.worktrees/release-please-sync" ] &&
  ok "worktree removed after apply" || bad "worktree left behind"

# --- idempotent: running apply again is a no-op, no new commit ---------------
before_sha="$(git -C "$WORK1.bare" rev-parse "release-please--branches--main")"
out="$(cd "$WORK1" && PATH="$GH1:$PATH" "$SCRIPT" apply --approval-token eph-2 2>&1)"
code=$?
after_sha="$(git -C "$WORK1.bare" rev-parse "release-please--branches--main")"
{
  [ "$code" -eq 0 ] &&
    printf '%s' "$out" | grep -qi 'already in sync' &&
    [ "$before_sha" = "$after_sha" ]
} &&
  ok "re-running apply is idempotent (no new commit)" ||
  bad "idempotent apply ($code): $out"

# --- apply with a failing bin/check.sh: aborts, no commit, no push -----------
WORK2="$TMP/work2"
build_fixture "$WORK2" 1
GH3="$TMP/gh3"
gh_stub "$GH3" '[{"number":7,"headRefName":"release-please--branches--main","baseRefName":"main"}]'
before_sha2="$(git -C "$WORK2.bare" rev-parse "release-please--branches--main")"
out="$(cd "$WORK2" && PATH="$GH3:$PATH" "$SCRIPT" apply --approval-token eph-3 2>&1)"
code=$?
after_sha2="$(git -C "$WORK2.bare" rev-parse "release-please--branches--main")"
{ [ "$code" -ne 0 ] && [ "$before_sha2" = "$after_sha2" ]; } &&
  ok "apply aborts on a failing bin/check.sh, no push" ||
  bad "check-fail abort ($code): $out"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
```

- [ ] **Step 2: Make it executable and run it to confirm RED**

```bash
chmod +x bin/test-release-please-sync.sh
bin/test-release-please-sync.sh
```

Expected: every case fails (`bin/release-please-sync.sh: No such file or
directory` or similar), ending in `0 passed, 9 failed` (or a shell error
before that line is even reached — either is a valid RED, since the script
doesn't exist yet). Do not proceed until you've confirmed a real failure.

#### GREEN

- [ ] **Step 3: Write the implementation**

Create `bin/release-please-sync.sh`:

```bash
#!/usr/bin/env bash
#
# release-please-sync.sh — syncs VERSION + RELEASE-MANIFEST.json onto the
# open Release Please release-PR branch (issue #137).
#
# release-please-config.json used to list VERSION under extra-files, but
# Release Please's generic file updater only rewrites lines carrying an
# x-release-please-version annotation comment — Bindle's bare VERSION has
# none, so that entry was a silent no-op (removed; see release-please-config.json).
# This script closes the gap: it reads the version Release Please already
# computed (from the release PR branch's .release-please-manifest.json) and
# writes it into VERSION, then regenerates RELEASE-MANIFEST.json
# (bin/release-manifest.py) — both in one follow-up commit pushed onto the
# SAME PR branch. It never creates a new PR, never touches main, never tags,
# merges, or publishes.
#
# Run from inside the target repo's working tree — same convention as
# bin/release-strategy.sh and bin/release-strategies/local-release-please.sh
# (no chdir to a fixed location; operates on the caller's cwd via `git -C`).
#
# Usage:
#   bin/release-please-sync.sh dry-run
#   bin/release-please-sync.sh apply --approval-token <ephemeral>
#
set -euo pipefail

die() {
  echo "release-please-sync: $1" >&2
  exit "${2:-1}"
}

verb="${1:-}"
shift || true

case "$verb" in
  dry-run) ;;
  apply)
    token=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --approval-token)
          token="${2:-}"
          shift 2
          ;;
        --approval-token=*)
          token="${1#*=}"
          shift
          ;;
        *) shift ;;
      esac
    done
    [ -n "$token" ] || die "apply refused — no approval token" 3
    ;;
  *)
    die "unknown verb '${verb:-<none>}' (want: dry-run|apply)" 2
    ;;
esac

command -v gh >/dev/null 2>&1 || die "gh CLI not found on PATH" 4

repo_root="$(git rev-parse --show-toplevel)"

# --- find the release PR ----------------------------------------------------
prs_json="$(gh pr list --state open --label "autorelease: pending" \
  --json number,headRefName,baseRefName)"
pr_count="$(printf '%s' "$prs_json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
[ "$pr_count" -ne 0 ] || die "no open PR labeled 'autorelease: pending' — nothing to sync" 10
[ "$pr_count" -eq 1 ] || die "found $pr_count PRs labeled 'autorelease: pending' — expected exactly 1, refusing to guess" 11

pr_field() { printf '%s' "$prs_json" | python3 -c "import json,sys; print(json.load(sys.stdin)[0][\"$1\"])"; }
pr_number="$(pr_field number)"
head_ref="$(pr_field headRefName)"
base_ref="$(pr_field baseRefName)"

git -C "$repo_root" fetch -q origin "$head_ref" "$base_ref"

manifest_version() { # manifest_version <ref>
  git -C "$repo_root" show "$1:.release-please-manifest.json" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["."])'
}

new_version="$(manifest_version "origin/$head_ref")"
old_version="$(manifest_version "origin/$base_ref")"
branch_version="$(git -C "$repo_root" show "origin/$head_ref:VERSION")"

if [ "$branch_version" = "$new_version" ]; then
  echo "release-please-sync: VERSION already in sync at $new_version (PR #$pr_number, $head_ref)"
  exit 0
fi

echo "release-please-sync: PR #$pr_number ($head_ref) — VERSION $branch_version -> $new_version"

if [ "$verb" = "dry-run" ]; then
  echo "release-please-sync: dry-run — would sync VERSION and regenerate RELEASE-MANIFEST.json on $head_ref"
  exit 0
fi

# --- apply: sync onto the PR branch in an isolated worktree -----------------
wt_dir="$repo_root/.worktrees/release-please-sync"
wt_branch="_release-please-sync"

git -C "$repo_root" worktree remove --force "$wt_dir" >/dev/null 2>&1 || true
git -C "$repo_root" worktree prune >/dev/null 2>&1 || true
rm -rf "$wt_dir"

cleanup() {
  git -C "$repo_root" worktree remove --force "$wt_dir" >/dev/null 2>&1 || true
  git -C "$repo_root" branch -D "$wt_branch" >/dev/null 2>&1 || true
}
trap cleanup EXIT

git -C "$repo_root" worktree add -q -B "$wt_branch" "$wt_dir" "origin/$head_ref"

(
  cd "$wt_dir"
  printf '%s\n' "$new_version" >VERSION
  bin/check.sh
  bin/test-install.sh
  python3 bin/release-manifest.py --version "$new_version" --previous "$old_version" --verify-determinism
  python3 bin/release-manifest.py --version "$new_version" --previous "$old_version" --emit
  git add VERSION RELEASE-MANIFEST.json
  git commit -q -m "chore: sync VERSION + RELEASE-MANIFEST.json to v${new_version}"
  git push -q origin "HEAD:$head_ref"
)

echo "release-please-sync: pushed VERSION + RELEASE-MANIFEST.json sync onto $head_ref (PR #$pr_number)"
```

- [ ] **Step 4: Make it executable**

```bash
chmod +x bin/release-please-sync.sh
```

- [ ] **Step 5: Run the test suite to confirm GREEN**

```bash
bin/test-release-please-sync.sh
```

Expected: last line reads `9 passed, 0 failed`. If any case fails, read its
`bad "..."` message (it includes the captured `$out`) and fix the script —
do not edit the test to match broken behavior.

- [ ] **Step 6: Run shellcheck/shfmt on the new files**

```bash
shellcheck bin/release-please-sync.sh bin/test-release-please-sync.sh
shfmt -i 2 -ci -d bin/release-please-sync.sh bin/test-release-please-sync.sh
```

Expected: no output from either command. If `shfmt` reports a diff, apply it:
`shfmt -i 2 -ci -w bin/release-please-sync.sh bin/test-release-please-sync.sh`
(bare `shfmt -w` uses different defaults and will still fail `make check`).

- [ ] **Step 7: Commit**

```bash
git add bin/release-please-sync.sh bin/test-release-please-sync.sh
git commit -m "feat(#137): release-please-sync — auto-sync VERSION + RELEASE-MANIFEST.json onto the RP release PR"
```

---

### Task 4: Wire into `make test`, pre-commit, and the capability inventory

**Files:**
- Modify: `Makefile`
- Modify: `.pre-commit-config.yaml`
- Modify: `capabilities.json`

**Interfaces:** None new — this task only registers Task 3's script with the
repo's existing test/hygiene machinery.

- [ ] **Step 1: Add the test target to `Makefile`**

`Makefile`'s `test:` target currently ends with:

```makefile
	bin/test-session-end-land.sh
	bin/test-release-strategy.sh
```

Change it to:

```makefile
	bin/test-session-end-land.sh
	bin/test-release-strategy.sh
	bin/test-release-please-sync.sh
```

- [ ] **Step 2: Add the pre-commit hook**

`.pre-commit-config.yaml` has this hook block (find it by searching for
`bindle-test-release-strategy`):

```yaml
      - id: bindle-test-release-strategy
        name: release-strategy seam tests
        entry: bin/test-release-strategy.sh
        language: script
        pass_filenames: false
        always_run: true
```

Add a matching block immediately after it:

```yaml
      - id: bindle-test-release-strategy
        name: release-strategy seam tests
        entry: bin/test-release-strategy.sh
        language: script
        pass_filenames: false
        always_run: true
      - id: bindle-test-release-please-sync
        name: release-please-sync tests
        entry: bin/test-release-please-sync.sh
        language: script
        pass_filenames: false
        always_run: true
```

- [ ] **Step 3: Register the capability**

In `capabilities.json`, find the `local-release-please` row (search for
`"name": "local-release-please"`) — it ends with:

```json
      "mutation": [
        "network",
        "external"
      ],
      "version_introduced": "0.5.0"
    },
    {
      "name": "issue-work-loop",
```

Insert a new row between them so it reads:

```json
      "mutation": [
        "network",
        "external"
      ],
      "version_introduced": "0.5.0"
    },
    {
      "name": "release-please-sync",
      "type": "script",
      "path": "bin/release-please-sync.sh",
      "description": "Syncs VERSION and regenerates RELEASE-MANIFEST.json onto the open Release Please release-PR branch (issue #137): Release Please's extra-files mechanism cannot update Bindle's bare, unannotated VERSION file, so this closes that gap by reading the version Release Please already computed from the PR branch's .release-please-manifest.json and writing it into VERSION, then regenerating RELEASE-MANIFEST.json via bin/release-manifest.py, in one follow-up commit pushed onto the same PR branch. dry-run previews read-only; apply requires an ephemeral --approval-token (no token => hard stop). Never creates a new PR, never touches main, never tags, merges, or publishes.",
      "provider": {
        "claude": "manual",
        "codex": "manual"
      },
      "maturity": "tested",
      "mutation": [
        "network",
        "external"
      ],
      "version_introduced": "0.6.0"
    },
    {
      "name": "issue-work-loop",
```

(`version_introduced` is one minor bump ahead of the current `VERSION`
(`0.5.0`) — this repo's convention for a capability added mid-cycle, per
`bin/check-inventory.py`'s ceiling check, which accepts exactly one bump
ahead.)

- [ ] **Step 4: Validate the JSON and run the inventory check**

```bash
python3 -c "import json; json.load(open('capabilities.json'))" && echo "valid json"
python3 bin/check-inventory.py
```

Expected: `valid json` then `capability inventory OK (47 capabilities, 36
ledgered exclusions)`.

- [ ] **Step 5: Run the full local gate**

```bash
make check
make test
```

Expected: `make check` ends with `All checks passed.`; `make test` runs every
`bin/test-*.sh` including the two new ones, all green.

- [ ] **Step 6: Commit**

```bash
git add Makefile .pre-commit-config.yaml capabilities.json
git commit -m "chore(#137): wire release-please-sync into make test, pre-commit, and the capability inventory"
```

---

### Task 5: Update the release-captain contract (L1)

**Files:**
- Modify: `docs/workflows/release-captain.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Note the automatic cross-check in Step 1 (Orient)**

Find this sentence in `### Step 1 — Orient`:

```markdown
- Identify the latest valid release tag and the current version source of
  truth — for Bindle, the `VERSION` file cross-checked against
  `RELEASE-MANIFEST.json`; do not assume a version from a changelog heading
  alone.
```

Change it to:

```markdown
- Identify the latest valid release tag and the current version source of
  truth — for Bindle, the `VERSION` file cross-checked against
  `RELEASE-MANIFEST.json` (kept in sync automatically by
  `bin/release-please-sync.sh`, issue #137); do not assume a version from a
  changelog heading alone.
```

- [ ] **Step 2: Add the sync step to Step 6's handoff list**

Find this list in `### Step 6 — Optional Release Please handoff`:

```markdown
- pass only an *approved* recommendation into the mechanical step;
- support dry-run/preview where available;
- preserve Release Please's release PR as the **human promotion gate** — the
  PR is a proposal, its merge is a person's decision;
- run release-integrity verification (`package-release-integrity` / `#59`)
  before any publication;
- never treat the recommendation, passing CI, or a created release PR as
  authorization to merge or publish (Section 2).
```

Change it to:

```markdown
- pass only an *approved* recommendation into the mechanical step;
- support dry-run/preview where available;
- preserve Release Please's release PR as the **human promotion gate** — the
  PR is a proposal, its merge is a person's decision;
- sync `VERSION` and regenerate `RELEASE-MANIFEST.json` onto the release PR
  branch via `bin/release-please-sync.sh` (issue #137) — Release Please's own
  `extra-files` mechanism cannot update Bindle's bare, unannotated `VERSION`
  file, so this step closes that gap locally, before the PR is reviewed;
- run release-integrity verification (`package-release-integrity` / `#59`)
  before any publication;
- never treat the recommendation, passing CI, or a created release PR as
  authorization to merge or publish (Section 2).
```

- [ ] **Step 3: Note that `RELEASE-MANIFEST.json` is now auto-regenerated**

Find this bullet in `## 5. Fit with the rest of Bindle`:

```markdown
- **Above the mechanical layer.** This contract stops at a *recommendation*.
  The mechanical release-PR *artifact* work (version/changelog + the PR)
  belongs to Release Please, invoked only after human approval per step 6; tag,
  GitHub Release, package publication, and deployment are separate,
  human-authorized publication, never implied by a created release PR.
  `bin/release.sh` remains only as legacy/fallback publication tooling and
  does not regenerate Release-Please-owned artifacts.
```

Change the last sentence and add a new one after it:

```markdown
- **Above the mechanical layer.** This contract stops at a *recommendation*.
  The mechanical release-PR *artifact* work (version/changelog + the PR)
  belongs to Release Please, invoked only after human approval per step 6; tag,
  GitHub Release, package publication, and deployment are separate,
  human-authorized publication, never implied by a created release PR.
  `bin/release.sh` remains only as legacy/fallback publication tooling and
  does not regenerate Release-Please-owned artifacts. `RELEASE-MANIFEST.json`
  is not Release-Please-owned, but it is kept current automatically:
  `bin/release-please-sync.sh` regenerates it (and syncs `VERSION`) onto the
  release PR branch as part of Step 6, so it no longer depends on a
  `bin/release.sh` run (issue #137).
```

- [ ] **Step 4: Verify links/format still pass**

```bash
bin/check.sh
```

Expected: `All checks passed.` or (if run standalone rather than via `make
check`) no new `problem`/`FAIL` lines referencing `docs/workflows/release-captain.md`.

- [ ] **Step 5: Commit**

```bash
git add docs/workflows/release-captain.md
git commit -m "docs(#137): release-captain contract documents the release-please-sync step"
```

---

### Task 6: Update the release-captain skill (L3)

**Files:**
- Modify: `skills/release-captain/SKILL.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Extend the Apply section**

Find this section:

```markdown
### Apply

Mint an **ephemeral approval token** — fresh for this one invocation, never a
reusable secret and never persisted — and run:

```bash
<bindle>/bin/release-strategy.sh apply --approval-token <ephemeral-token>
```

`apply` may only create or update the release PR. It never merges, tags,
publishes, or deploys. The resulting release PR is a **proposal**; its merge is
a separate human decision.
```

Change it to:

```markdown
### Apply

Mint an **ephemeral approval token** — fresh for this one invocation, never a
reusable secret and never persisted — and run:

```bash
<bindle>/bin/release-strategy.sh apply --approval-token <ephemeral-token>
```

`apply` may only create or update the release PR. It never merges, tags,
publishes, or deploys. The resulting release PR is a **proposal**; its merge is
a separate human decision.

Immediately after, sync `VERSION` and `RELEASE-MANIFEST.json` onto that same
PR branch — mint a second, independent ephemeral token, since this performs
its own `git push` (an external mutation, per §2's rule that each such action
needs its own explicit grant):

```bash
<bindle>/bin/release-please-sync.sh apply --approval-token <ephemeral-token>
```

This closes the gap where Release Please's `extra-files` mechanism cannot
update Bindle's bare `VERSION` (issue #137): it never creates a new PR, never
touches `main`, and never tags or publishes — strictly a follow-up commit on
the already-open release PR branch. Safe to re-run: it no-ops if `VERSION`
already matches the PR's proposed version.
```

- [ ] **Step 2: Add a "Fit with the rest of Bindle" bullet**

Find this bullet at the end of the file:

```markdown
- **Above `<bindle>/bin/release.sh`.** That script remains legacy/fallback
  *publication* tooling only and does not regenerate Release-Please-owned
  artifacts (`VERSION`, `CHANGELOG.md`).
```

Add a new bullet immediately after it:

```markdown
- **Above `<bindle>/bin/release.sh`.** That script remains legacy/fallback
  *publication* tooling only and does not regenerate Release-Please-owned
  artifacts (`VERSION`, `CHANGELOG.md`).
- **`RELEASE-MANIFEST.json` stays current.**
  `<bindle>/bin/release-please-sync.sh` regenerates it (and syncs `VERSION`)
  onto the release PR branch as part of Apply — see above — so it no longer
  depends on a `bin/release.sh` run.
```

- [ ] **Step 3: Verify the skill's frontmatter/links still pass**

```bash
bin/check.sh
```

Expected: no new problems referencing `skills/release-captain/SKILL.md`.

- [ ] **Step 4: Commit**

```bash
git add skills/release-captain/SKILL.md
git commit -m "docs(#137): release-captain skill runs release-please-sync as part of Apply"
```

---

### Task 7: Update the release-manifest contract

**Files:**
- Modify: `docs/release-manifest.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Add a new section documenting the automatic path**

Find the `## Determinism` heading in `docs/release-manifest.md` and insert a
new section immediately before it:

```markdown
## Automatic generation under Release Please (issue #137)

`bin/release.sh` is legacy/fallback publication tooling — the primary release
path is now Release Please via `bin/release-strategy.sh`. Under that flow,
`bin/release-please-sync.sh apply` regenerates `RELEASE-MANIFEST.json` (and
syncs `VERSION`, which Release Please's own `extra-files` mechanism cannot
update for a bare, unannotated version file) onto the open release PR branch,
using the same generator (`bin/release-manifest.py`) and the same
determinism guarantee described below. See
`docs/workflows/release-captain.md` Step 6.

## Determinism
```

(Only the `## Automatic generation...` section is new — the existing
`## Determinism` heading and everything after it is unchanged; this step just
inserts new content above it.)

- [ ] **Step 2: Verify links still resolve**

```bash
bin/check.sh
```

Expected: no new problems referencing `docs/release-manifest.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/release-manifest.md
git commit -m "docs(#137): release-manifest contract documents the automatic Release Please path"
```

---

### Task 8: Final verification and PR

**Files:** None — verification and publication only.

- [ ] **Step 1: Run the full gate one more time from a clean state**

```bash
make check
make test
```

Expected: both green, no drift (this catches anything Tasks 1–7 individually
missed once all changes are combined).

- [ ] **Step 2: Review the full diff against `main`**

```bash
git status --short
git diff main --stat
```

Expected: only the files named in Tasks 1–7 (`.gitignore`,
`release-please-config.json`, `bin/release-please-sync.sh`,
`bin/test-release-please-sync.sh`, `Makefile`, `.pre-commit-config.yaml`,
`capabilities.json`, `docs/workflows/release-captain.md`,
`skills/release-captain/SKILL.md`, `docs/release-manifest.md`, plus the two
design/plan docs already committed earlier in this session) — nothing else.

- [ ] **Step 3: Push the branch and open the PR**

```bash
git push -u origin fix/137-release-please-sync
gh pr create --title "fix(#137): auto-sync VERSION + RELEASE-MANIFEST.json onto the Release Please PR" \
  --body "$(cat <<'EOF'
## What & why

Release Please's `extra-files` mechanism can't update Bindle's bare,
unannotated `VERSION` file (it only rewrites annotated lines), so every
release has left `VERSION` and `RELEASE-MANIFEST.json` stale, requiring a
manual fix. This adds `bin/release-please-sync.sh`, run as the step right
after `bin/release-strategy.sh apply`: it reads the version Release Please
already computed and syncs `VERSION` + regenerates `RELEASE-MANIFEST.json`
directly onto the open release PR branch — before human review, never
touching `main`, never tagging or publishing.

## Changes

- `bin/release-please-sync.sh` (new) + `bin/test-release-please-sync.sh` (9
  fixture cases, offline).
- Dropped the dead `VERSION` entry from `release-please-config.json`'s
  `extra-files` (it never worked).
- Wired into `make test`, pre-commit, and `capabilities.json`.
- `docs/workflows/release-captain.md`, `skills/release-captain/SKILL.md`,
  `docs/release-manifest.md` updated to document the new step.

## Testing

- `make check`
- `make test` (includes `bin/test-release-please-sync.sh`, 9/9 passing)

Fixes #137
EOF
)"
```

- [ ] **Step 4: Report the PR URL back to the user and stop**

Do not merge. Do not update the issue yet — that happens after the user
reviews and the PR is in a mergeable state, per the session's own closing
instructions (update issue #137, then end session).
