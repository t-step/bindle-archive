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

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
