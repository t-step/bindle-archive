#!/usr/bin/env bash
#
# test-check.sh — exercise bin/check.sh's script/self-test *discovery* against
# throwaway fixture repos. check.sh derives its repo root from its own
# location and shells out to `git ls-files`, so each test builds a tiny fake
# git repo (with a copy of check.sh + check-private-info.sh) and runs check.sh
# from inside it. Nothing touches this repo.
#
# Usage: bin/test-check.sh
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so the fixture-repo git
# calls below would hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK_SRC="$REPO_ROOT/bin/check.sh"
PRIVATE_INFO_SRC="$REPO_ROOT/bin/check-private-info.sh"

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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git_commit() { # git_commit DIR MESSAGE
  (cd "$1" && git add -A && git -c user.email=test@example.com -c user.name=test commit -q -m "$2")
}

# build_repo DIR — a minimal fake Bindle repo check.sh can run cleanly against.
build_repo() {
  local r="$1"
  mkdir -p "$r/bin"
  cp "$CHECK_SRC" "$r/bin/check.sh"
  cp "$PRIVATE_INFO_SRC" "$r/bin/check-private-info.sh"
  chmod +x "$r/bin/check.sh" "$r/bin/check-private-info.sh"
  printf '0.1.0\n' >"$r/VERSION"
  printf '# Changelog\n\n## [Unreleased]\n\n- nothing yet\n' >"$r/CHANGELOG.md"
  # The boundary document is required (see check.sh section 5b); its minor must
  # keep pace with VERSION's. Fixtures start affirmed at their own VERSION.
  mkdir -p "$r/docs"
  printf '# Product boundary\n\nAffirmed through: v0.1\n' >"$r/docs/product-boundary.md"
  (cd "$r" && git init -q && git symbolic-ref HEAD refs/heads/main)
  git_commit "$r" "init"
}

# ===========================================================================
echo "shell script discovery outside bin/:"
REPO="$TMP/repo-sh"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo/scripts"
cat >"$REPO/skills/demo/scripts/tool.sh" <<'EOF'
#!/usr/bin/env bash
cd $1
echo $1
EOF
git_commit "$REPO" "add script outside bin/"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "discovers a tracked script outside bin/" contains "skills/demo/scripts/tool.sh" "$out"
check "shellcheck actually lints it (reports the unquoted-arg issue)" contains "shellcheck reported issues" "$out"

# ===========================================================================
echo "skill self-test discovery:"
REPO="$TMP/repo-selftest"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo/scripts"
cat >"$REPO/skills/demo/scripts/selftest.py" <<'EOF'
print("demo selftest ok")
EOF
git_commit "$REPO" "add a conventional skill selftest"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "runs a newly added skill selftest without editing check.sh" contains "skills/demo/scripts/selftest.py" "$out"
check "reports the passing skill by name" contains "demo selftests pass" "$out"

echo "failing skill self-test is reported:"
REPO="$TMP/repo-selftest-fail"
build_repo "$REPO"
mkdir -p "$REPO/skills/broken/scripts"
cat >"$REPO/skills/broken/scripts/selftest.py" <<'EOF'
import sys
sys.exit(1)
EOF
git_commit "$REPO" "add a failing skill selftest"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "reports the failing skill by name" contains "broken selftests failed" "$out"

# ===========================================================================
echo "explicit shell exclusion:"
REPO="$TMP/repo-exclude"
build_repo "$REPO"
mkdir -p "$REPO/fixtures"
cat >"$REPO/fixtures/broken.sh" <<'EOF'
#!/usr/bin/env bash
cd $1
echo $1
EOF
# SH_EXCLUDE ships empty; patch this copy to exclude the fixture, same as a
# maintainer would when adding a documented exclusion.
sed -i.bak 's/^SH_EXCLUDE=()$/SH_EXCLUDE=(fixtures\/broken.sh)/' "$REPO/bin/check.sh"
rm -f "$REPO/bin/check.sh.bak"
git_commit "$REPO" "add excluded fixture + exclusion"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "excluded script is not shellchecked" not_contains "fixtures/broken.sh" "$out"
check "everything else still passes cleanly" contains "shell scripts clean" "$out"

# ===========================================================================
echo "paths with spaces are handled safely:"
REPO="$TMP/repo-spaces"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo space/scripts"
cat >"$REPO/skills/demo space/scripts/my tool.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "hi"
EOF
git_commit "$REPO" "add a script with spaces in its path"
out="$(cd "$REPO" && bin/check.sh 2>&1)"
status=$?

check "does not error out on a spaced path" test "$status" -eq 0
check "discovers the spaced-path script" contains "skills/demo space/scripts/my tool.sh" "$out"

# ===========================================================================
echo "Bindle-root path refs — flags a bare run-ref:"
REPO="$TMP/repo-pathref"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo"
cat >"$REPO/skills/demo/SKILL.md" <<'EOF'
---
name: demo
description: demo skill
---
Run `bin/check-private-info.sh` on the summary before committing.
EOF
git_commit "$REPO" "add skill with a bare Bindle-root run-ref"
out="$(cd "$REPO" && bin/check.sh 2>&1)"
status=$?

check "flags the file with the bare run-ref" contains "skills/demo/SKILL.md" "$out"
check "explains the fix (qualify with <bindle>/)" contains "qualify with <bindle>/" "$out"
check "check.sh exits non-zero on a bare run-ref" test "$status" -ne 0

# ===========================================================================
echo "Bindle-root path refs — clean when qualified, allowlisted, or in frontmatter:"
REPO="$TMP/repo-pathref-ok"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo" "$REPO/skills/desc" "$REPO/commands"
# already <bindle>/-qualified — must be clean
cat >"$REPO/skills/demo/SKILL.md" <<'EOF'
---
name: demo
description: demo skill
---
Run `<bindle>/bin/check-private-info.sh` on the summary before committing.
EOF
# a frontmatter permission glob — must NOT trip (frontmatter is skipped)
cat >"$REPO/commands/notes.md" <<'EOF'
---
description: notes command
allowed-tools: Bash(bin/notes-home.sh status:*)
---
Body text with no runnable Bindle-root refs.
EOF
# a descriptive mention covered by the shipped allowlist ("Where the tools live")
cat >"$REPO/skills/desc/SKILL.md" <<'EOF'
---
name: desc
description: desc skill
---
**Where the tools live.** Both `bin/domi-status.sh` and the docs are at the Bindle root.
EOF
git_commit "$REPO" "qualified + frontmatter-glob + allowlisted refs"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "does not flag a <bindle>/-qualified ref" not_contains "skills/demo/SKILL.md" "$out"
check "does not flag a frontmatter permission glob" not_contains "commands/notes.md" "$out"
check "does not flag an allowlisted descriptive line" not_contains "skills/desc/SKILL.md" "$out"
check "reports the section clean" contains "Bindle-root tool refs are" "$out"

# ===========================================================================
echo "CHANGELOG Unreleased requirement (legacy flow only):"
# No release-please-config.json → the legacy bin/release.sh flow → an
# Unreleased section is required, and its absence is a problem.
REPO="$TMP/repo-nounrel-legacy"
build_repo "$REPO"
printf '# Changelog\n\n## [1.0.0] - 2020-01-01\n\n- shipped\n' >"$REPO/CHANGELOG.md"
git_commit "$REPO" "drop Unreleased, no Release Please"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "flags a missing Unreleased section without Release Please" contains "missing '## [Unreleased]' section" "$out"

# release-please-config.json present → Release Please owns the changelog → an
# Unreleased section is NOT required, and its absence must not be flagged.
REPO="$TMP/repo-nounrel-rp"
build_repo "$REPO"
printf '# Changelog\n\n## [1.0.0] - 2020-01-01\n\n- shipped\n' >"$REPO/CHANGELOG.md"
printf '{"packages":{".":{"release-type":"simple"}}}\n' >"$REPO/release-please-config.json"
git_commit "$REPO" "drop Unreleased, Release Please configured"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "does not require Unreleased when Release Please is configured" not_contains "missing '## [Unreleased]' section" "$out"

# ===========================================================================
echo "product-boundary staleness gate:"
# The boundary document names the minor it was last affirmed against. It goes
# stale silently otherwise — the #283 failure, where a v0.3–v0.4 document sat
# unrevised across ~200 issues with no event to announce its expiry.

# Affirmed minor == VERSION's minor → current, nothing flagged.
REPO="$TMP/repo-boundary-current"
build_repo "$REPO"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "accepts a boundary affirmed through VERSION's minor" not_contains "affirmed through" "$out"

# A patch bump must NOT demand re-affirmation — a boundary document has nothing
# to say about a patch release.
REPO="$TMP/repo-boundary-patch"
build_repo "$REPO"
printf '0.1.7\n' >"$REPO/VERSION"
git_commit "$REPO" "patch bump"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "does not demand re-affirmation on a patch bump" not_contains "affirmed through" "$out"

# Affirmed minor behind VERSION's minor → the document has lapsed.
REPO="$TMP/repo-boundary-stale"
build_repo "$REPO"
printf '0.2.0\n' >"$REPO/VERSION"
git_commit "$REPO" "minor bump without re-affirming the boundary"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "flags a boundary affirmed behind VERSION's minor" contains "affirmed through v0.1, but VERSION is 0.2.0" "$out"

# A major bump is a minor bump too, as far as staleness goes.
REPO="$TMP/repo-boundary-major"
build_repo "$REPO"
printf '1.0.0\n' >"$REPO/VERSION"
git_commit "$REPO" "major bump without re-affirming the boundary"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "flags a boundary left behind by a major bump" contains "affirmed through v0.1, but VERSION is 1.0.0" "$out"

# Present but unaffirmed → the line is the whole mechanism, so its absence is a
# failure, not a skip.
REPO="$TMP/repo-boundary-noline"
build_repo "$REPO"
printf '# Product boundary\n\nNo affirmation line here.\n' >"$REPO/docs/product-boundary.md"
git_commit "$REPO" "drop the affirmation line"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "flags a boundary document with no 'Affirmed through:' line" contains "no 'Affirmed through:' line" "$out"

# Malformed affirmation → don't silently treat an unparseable value as current.
REPO="$TMP/repo-boundary-malformed"
build_repo "$REPO"
printf '# Product boundary\n\nAffirmed through: soon\n' >"$REPO/docs/product-boundary.md"
git_commit "$REPO" "malformed affirmation"
out="$(cd "$REPO" && bin/check.sh 2>&1)"

check "flags a malformed 'Affirmed through:' value" contains "not vMAJOR.MINOR" "$out"

# Missing document → skip, don't fail. check.sh is copied into fixture repos by
# several suites; requiring this file would couple every fixture builder to it.
# Deletion in the real repo is caught by bin/check-inventory.py instead, which
# resolves the capabilities.json related_docs entries that name this file.
REPO="$TMP/repo-boundary-missing"
build_repo "$REPO"
rm "$REPO/docs/product-boundary.md"
git_commit "$REPO" "delete the boundary document"
out="$(cd "$REPO" && bin/check.sh --content-only 2>&1)"
status=$?

check "skips cleanly when docs/product-boundary.md is absent" contains "skipping (inventory owns its existence)" "$out"
check "does not fail the run when the boundary document is absent" test "$status" -eq 0

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
