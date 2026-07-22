#!/usr/bin/env bash
#
# test-release-publish.sh — exercise bin/release-publish.sh against a
# throwaway git fixture with a stubbed gh CLI. Never touches the network or
# the real repo/remote.
#
# shellcheck disable=SC2015 # `cond && ok || bad` is the intended assertion idiom (bad only runs on failure); ok/bad never fail
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/release-publish.sh"

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

# build_fixture <work-dir> — a minimal git repo with a CHANGELOG carrying a
# [0.6.0] section, for extraction assertions. Also lays down three tags for
# the VERSION/manifest gate (#327):
#   v0.6.0  VERSION and manifest agree at 0.6.0 (the happy path every other
#           assertion in this file already exercises)
#   v0.7.0  the v0.9.0 real-world shape: manifest bumped to 0.7.0, VERSION
#           left at 0.6.0 -- the mismatch the gate must refuse to publish
#   v9.9.9  VERSION and manifest agree at 9.9.9, no CHANGELOG section --
#           exercises the pre-existing fallback-notes path, unrelated to the
#           gate
build_fixture() {
  local work="$1"
  git init -q "$work"
  git -C "$work" config user.email t@e.st
  git -C "$work" config user.name t
  git -C "$work" checkout -q -b main
  cat >"$work/CHANGELOG.md" <<'MD'
# Changelog

## [0.6.0] - 2026-07-16

### Fixed

- A fix worth publishing.

## [0.5.0] - 2026-06-01

### Added

- Older stuff.
MD
  printf '0.6.0\n' >"$work/VERSION"
  printf '{\n  ".": "0.6.0"\n}\n' >"$work/.release-please-manifest.json"
  git -C "$work" add -A
  git -C "$work" commit -q -m init
  git -C "$work" tag v0.6.0

  printf '{\n  ".": "0.7.0"\n}\n' >"$work/.release-please-manifest.json"
  git -C "$work" add -A
  git -C "$work" commit -q -m "manifest bumped, VERSION sync never ran"
  git -C "$work" tag v0.7.0

  printf '9.9.9\n' >"$work/VERSION"
  printf '{\n  ".": "9.9.9"\n}\n' >"$work/.release-please-manifest.json"
  git -C "$work" add -A
  git -C "$work" commit -q -m "9.9.9 matching pair"
  git -C "$work" tag v9.9.9
}

# gh_stub <dir> <pr-list-json> <label-list-lines> — a fake `gh` on PATH that
# answers `pr list`/`label list` from canned responses, accepts
# `label create`/`pr edit`/`release create`, logs every invocation, and
# refuses anything unexpected.
gh_stub() {
  local dir="$1" pr_json="$2" label_lines="$3"
  mkdir -p "$dir"
  printf '%s' "$pr_json" >"$dir/pr-list-response.json"
  printf '%s' "$label_lines" >"$dir/label-list-response.txt"
  log="$dir/gh.log"
  cat >"$dir/gh" <<EOF
#!/usr/bin/env bash
echo "\$*" >>"$log"
case "\$1 \$2" in
  "pr list")
    cat "$dir/pr-list-response.json"
    ;;
  "label list")
    cat "$dir/label-list-response.txt"
    ;;
  "label create"|"pr edit"|"release create")
    exit 0
    ;;
  *)
    echo "unexpected gh invocation: \$*" >&2
    exit 1
    ;;
esac
EOF
  chmod +x "$dir/gh"
}

WORK="$TMP/work"
build_fixture "$WORK"

# --- verb / arg parsing: no gh/fixture needed --------------------------------
out="$(cd "$WORK" && "$SCRIPT" bogus v0.6.0 2>&1)"
code=$?
[ "$code" -eq 2 ] && ok "unknown verb -> exit 2" || bad "unknown verb ($code): $out"

out="$(cd "$WORK" && "$SCRIPT" apply v0.6.0 2>&1)"
code=$?
[ "$code" -eq 3 ] && ok "apply without token -> exit 3" || bad "apply-no-token ($code): $out"

out="$(cd "$WORK" && "$SCRIPT" dry-run 2>&1)"
code=$?
[ "$code" -eq 64 ] && ok "missing tag -> exit 64" || bad "missing tag ($code): $out"

out="$(cd "$WORK" && "$SCRIPT" dry-run 0.6.0 2>&1)"
code=$?
[ "$code" -eq 5 ] && ok "bad tag format (no leading v) -> exit 5" || bad "bad tag ($code): $out"

# --- gh missing: hard stop before any extraction/lookup ----------------------
NOGH="$TMP/no-gh-path"
mkdir -p "$NOGH"
ln -sf "$(command -v git)" "$NOGH/git"
ln -sf "$(command -v python3)" "$NOGH/python3"
ln -sf "$(command -v awk)" "$NOGH/awk"
ln -sf "$(command -v bash)" "$NOGH/bash"
ln -sf "$(command -v mktemp)" "$NOGH/mktemp"
ln -sf "$(command -v sed)" "$NOGH/sed"
out="$(cd "$WORK" && PATH="$NOGH" "$SCRIPT" dry-run v0.6.0 2>&1)"
code=$?
[ "$code" -eq 4 ] && ok "gh missing -> exit 4" || bad "gh missing ($code): $out"

# --- two matching merged PRs: refuse to guess ---------------------------------
GH2="$TMP/gh2"
gh_stub "$GH2" '[{"number":1,"headRefName":"a","mergedAt":"2026-07-01T00:00:00Z"},{"number":2,"headRefName":"b","mergedAt":"2026-07-02T00:00:00Z"}]' \
  $'autorelease: pending\n'
out="$(cd "$WORK" && PATH="$GH2:$PATH" "$SCRIPT" dry-run v0.6.0 2>&1)"
code=$?
[ "$code" -eq 11 ] && ok "two merged pending-labeled PRs -> exit 11" || bad "two PRs ($code): $out"

# --- dry-run: extracts the right changelog section, reports relabel plan, mutates nothing ---
GH1="$TMP/gh1"
gh_stub "$GH1" '[{"number":151,"headRefName":"release-please--branches--main","mergedAt":"2026-07-16T00:00:00Z"}]' \
  $'autorelease: pending\n'
out="$(cd "$WORK" && PATH="$GH1:$PATH" "$SCRIPT" dry-run v0.6.0 2>&1)"
code=$?
{
  [ "$code" -eq 0 ] &&
    printf '%s' "$out" | grep -q 'A fix worth publishing' &&
    ! printf '%s' "$out" | grep -q 'Older stuff' &&
    printf '%s' "$out" | grep -q 'would create label' &&
    printf '%s' "$out" | grep -q 'would relabel PR #151' &&
    ! grep -Eq 'release create|label create|pr edit' "$GH1/gh.log"
} &&
  ok "dry-run extracts [0.6.0] section, plans relabel, mutates nothing" ||
  bad "dry-run ($code): $out; gh.log=$(cat "$GH1/gh.log" 2>/dev/null)"

# --- apply: publishes, creates the label (absent), relabels the merged PR ---
: >"$GH1/gh.log"
out="$(cd "$WORK" && PATH="$GH1:$PATH" "$SCRIPT" apply v0.6.0 --approval-token eph-1 2>&1)"
code=$?
{
  [ "$code" -eq 0 ] &&
    grep -q 'release create v0.6.0 --title v0.6.0 --notes-file' "$GH1/gh.log" &&
    grep -q 'label create autorelease: tagged' "$GH1/gh.log" &&
    grep -q 'pr edit 151 --add-label autorelease: tagged --remove-label autorelease: pending' "$GH1/gh.log"
} &&
  ok "apply publishes, creates missing label, relabels the merged PR" ||
  bad "apply ($code): $out; gh.log=$(cat "$GH1/gh.log")"

# --- apply: label already exists -> no label create call ---------------------
GH3="$TMP/gh3"
gh_stub "$GH3" '[{"number":151,"headRefName":"release-please--branches--main","mergedAt":"2026-07-16T00:00:00Z"}]' \
  $'autorelease: pending\nautorelease: tagged\n'
out="$(cd "$WORK" && PATH="$GH3:$PATH" "$SCRIPT" apply v0.6.0 --approval-token eph-2 2>&1)"
code=$?
{
  [ "$code" -eq 0 ] &&
    grep -q 'release create' "$GH3/gh.log" &&
    ! grep -q 'label create' "$GH3/gh.log" &&
    grep -q 'pr edit 151' "$GH3/gh.log"
} &&
  ok "apply skips label create when the label already exists" ||
  bad "apply-label-exists ($code): gh.log=$(cat "$GH3/gh.log")"

# --- apply: zero matching merged PRs -> publish succeeds, relabel is a no-op ---
GH0="$TMP/gh0"
gh_stub "$GH0" '[]' $'autorelease: tagged\n'
out="$(cd "$WORK" && PATH="$GH0:$PATH" "$SCRIPT" apply v0.6.0 --approval-token eph-3 2>&1)"
code=$?
{
  [ "$code" -eq 0 ] &&
    grep -q 'release create' "$GH0/gh.log" &&
    ! grep -q 'pr edit' "$GH0/gh.log" &&
    printf '%s' "$out" | grep -qi 'nothing to relabel'
} &&
  ok "apply with zero matching PRs publishes and no-ops the relabel" ||
  bad "apply-zero-prs ($code): $out; gh.log=$(cat "$GH0/gh.log")"

# --- dry-run: no matching changelog section falls back to "Release <tag>" ---
GH4="$TMP/gh4"
gh_stub "$GH4" '[]' $'autorelease: tagged\n'
out="$(cd "$WORK" && PATH="$GH4:$PATH" "$SCRIPT" dry-run v9.9.9 2>&1)"
code=$?
{ [ "$code" -eq 0 ] && printf '%s' "$out" | grep -q 'Release v9.9.9'; } &&
  ok "dry-run falls back to 'Release <tag>' when no changelog section matches" ||
  bad "fallback notes ($code): $out"

# --- VERSION/manifest gate (#327): a trap `gh` that fails loudly if ever
# invoked, proving the gate refuses BEFORE any gh call (not just before a
# mutating one) --------------------------------------------------------------
GHTRAP="$TMP/gh-trap"
mkdir -p "$GHTRAP"
ln -sf "$(command -v git)" "$GHTRAP/git"
ln -sf "$(command -v python3)" "$GHTRAP/python3"
ln -sf "$(command -v awk)" "$GHTRAP/awk"
ln -sf "$(command -v bash)" "$GHTRAP/bash"
ln -sf "$(command -v mktemp)" "$GHTRAP/mktemp"
ln -sf "$(command -v sed)" "$GHTRAP/sed"
ln -sf "$(command -v rm)" "$GHTRAP/rm"
cat >"$GHTRAP/gh" <<'EOF'
#!/usr/bin/env bash
echo "UNEXPECTED gh invocation: $*" >&2
exit 9
EOF
chmod +x "$GHTRAP/gh"

out="$(cd "$WORK" && PATH="$GHTRAP" "$SCRIPT" dry-run v0.7.0 2>&1)"
code=$?
{
  [ "$code" -eq 12 ] &&
    printf '%s' "$out" | grep -q '0.6.0' &&
    printf '%s' "$out" | grep -q '0.7.0' &&
    ! printf '%s' "$out" | grep -qi 'UNEXPECTED gh'
} &&
  ok "dry-run refuses a tag whose VERSION disagrees with the manifest (v0.9.0 shape) -> exit 12" ||
  bad "dry-run version/manifest mismatch ($code): $out"

out="$(cd "$WORK" && PATH="$GHTRAP" "$SCRIPT" apply v0.7.0 --approval-token eph-4 2>&1)"
code=$?
{ [ "$code" -eq 12 ] && ! printf '%s' "$out" | grep -qi 'UNEXPECTED gh'; } &&
  ok "apply refuses the same mismatch -> exit 12, never touches gh" ||
  bad "apply version/manifest mismatch ($code): $out"

out="$(cd "$WORK" && PATH="$GHTRAP" "$SCRIPT" dry-run v5.5.5 2>&1)"
code=$?
{ [ "$code" -eq 13 ] && printf '%s' "$out" | grep -qi 'not found'; } &&
  ok "dry-run refuses a tag that does not exist locally -> exit 13" ||
  bad "missing tag ref ($code): $out"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
