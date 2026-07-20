#!/usr/bin/env bash
#
# test-release-please-sync.sh — exercise bin/release-please-sync.sh against a
# throwaway git fixture with a local bare "origin" and a stubbed gh CLI.
# Never touches the network or the real repo's git state.
#
# shellcheck disable=SC2015 # `cond && ok || bad` is the intended assertion idiom (bad only runs on failure); ok/bad never fail
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
ln -sf "$(command -v bash)" "$NOGH/bash"
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

# --- apply, clean: VERSION lands on the head branch --------------------------
out="$(cd "$WORK1" && PATH="$GH1:$PATH" "$SCRIPT" apply --approval-token eph-1 2>&1)"
code=$?
head_version="$(git -C "$WORK1.bare" show "release-please--branches--main:VERSION" 2>/dev/null || true)"
{
  [ "$code" -eq 0 ] &&
    [ "$head_version" = "0.2.0" ]
} &&
  ok "apply syncs VERSION onto the PR branch" ||
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

# --- check: the v0.7.0 failure mode (#265) ----------------------------------
# WORK3 is the exact shape the v0.7.0 cut was left in: the release PR branch
# carries the bumped manifest while VERSION still holds the old value, because
# the chained sync ran before the PR was visible and reported "nothing to sync".
# `check` is the deterministic gate that refuses to call that a good release PR.
WORK3="$TMP/work3"
build_fixture "$WORK3" 0
GH4="$TMP/gh4"
gh_stub "$GH4" '[{"number":70,"headRefName":"release-please--branches--main","baseRefName":"main"}]'

bare3_before="$(git -C "$WORK3.bare" show-ref)"
out="$(cd "$WORK3" && PATH="$GH4:$PATH" "$SCRIPT" check 2>&1)"
code=$?
bare3_after="$(git -C "$WORK3.bare" show-ref)"
{
  [ "$code" -eq 12 ] &&
    printf '%s' "$out" | grep -q '0.1.0' &&
    printf '%s' "$out" | grep -q '0.2.0' &&
    [ "$bare3_before" = "$bare3_after" ]
} &&
  ok "check fails (12) on a release PR whose VERSION disagrees with the manifest" ||
  bad "check-disagree ($code): $out"

printf '%s' "$out" | grep -q 'release-please-sync.sh apply' &&
  ok "check names the recovery (re-run apply)" ||
  bad "check-recovery-hint: $out"

# check takes no approval token — it is read-only, so requiring one would
# discourage running it. It must NOT be refused for lack of a token.
[ "$code" -ne 3 ] && ok "check needs no approval token" || bad "check demanded a token"

# --- check: passes once VERSION and the manifest agree ----------------------
(cd "$WORK3" && PATH="$GH4:$PATH" "$SCRIPT" apply --approval-token eph-4 >/dev/null 2>&1)
out="$(cd "$WORK3" && PATH="$GH4:$PATH" "$SCRIPT" check 2>&1)"
code=$?
{ [ "$code" -eq 0 ] && printf '%s' "$out" | grep -qi 'in sync'; } &&
  ok "check passes once VERSION and the manifest agree" ||
  bad "check-in-sync ($code): $out"

# The race itself: no PR labeled 'autorelease: pending' yet. An unrun check is
# never a passing one — this is the exit that must stop the release flow.
out="$(cd "$WORK3" && PATH="$GH0:$PATH" "$SCRIPT" check 2>&1)"
code=$?
[ "$code" -eq 10 ] && ok "check with no release PR -> exit 10, not success" || bad "check-no-pr ($code): $out"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
