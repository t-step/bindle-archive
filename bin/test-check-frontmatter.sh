#!/usr/bin/env bash
#
# test-check-frontmatter.sh — exercise bin/check.sh's frontmatter parsing
# against throwaway fixture repos. check.sh derives its repo root from its own
# location and shells out to `git ls-files`, so each test builds a tiny fake
# git repo (with a copy of check.sh + check-private-info.sh) and runs check.sh
# from inside it. Nothing touches this repo.
#
# Usage: bin/test-check-frontmatter.sh
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
echo "a body-level name: cannot influence validation:"
REPO="$TMP/repo-body-name"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo"
cat >"$REPO/skills/demo/SKILL.md" <<'EOF'
---
description: demo skill
---

Some prose.

Example:
```
name: totally-different-thing
```
EOF
git_commit "$REPO" "skill with a body name: line, no frontmatter name:"
out="$(cd "$REPO" && bin/check.sh --content-only 2>&1)"

check "still reports the real problem (missing name:)" contains "frontmatter missing 'name:'" "$out"
check "does not fabricate a mismatch from body text" not_contains "totally-different-thing" "$out"

# ===========================================================================
echo "unterminated frontmatter fails clearly:"
REPO="$TMP/repo-unterminated"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo"
cat >"$REPO/skills/demo/SKILL.md" <<'EOF'
---
name: demo
description: demo skill

No closing delimiter above — this whole rest of the file is (incorrectly, pre-fix) part of "frontmatter".
EOF
git_commit "$REPO" "skill with unterminated frontmatter"
out="$(cd "$REPO" && bin/check.sh --content-only 2>&1)"
status=$?

check "reports a clear unterminated-frontmatter problem" contains "never closed" "$out"
check "overall check fails" test "$status" -ne 0

# ===========================================================================
echo "duplicate frontmatter keys are rejected:"
REPO="$TMP/repo-dup-key"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo"
cat >"$REPO/skills/demo/SKILL.md" <<'EOF'
---
name: demo
name: demo-again
description: demo skill
---

Body.
EOF
git_commit "$REPO" "skill with a duplicated name: key"
out="$(cd "$REPO" && bin/check.sh --content-only 2>&1)"
status=$?

check "reports a duplicate-key problem" contains "duplicate" "$out"
check "overall check fails" test "$status" -ne 0

# ===========================================================================
echo "valid frontmatter still passes (regression floor):"
REPO="$TMP/repo-valid"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo" "$REPO/agents" "$REPO/commands"
cat >"$REPO/skills/demo/SKILL.md" <<'EOF'
---
name: demo
description: demo skill
---

Body.
EOF
cat >"$REPO/agents/demo.md" <<'EOF'
---
name: demo
description: demo agent
---

Body.
EOF
cat >"$REPO/commands/demo.md" <<'EOF'
---
description: demo command
---

Body.
EOF
git_commit "$REPO" "valid skill, agent, command"
out="$(cd "$REPO" && bin/check.sh --content-only 2>&1)"
status=$?

check "valid frontmatter passes cleanly" test "$status" -eq 0
check "reports all three items checked" contains "3 item(s) have valid frontmatter" "$out"

# ===========================================================================
echo "a genuine name/folder mismatch is still caught:"
REPO="$TMP/repo-mismatch"
build_repo "$REPO"
mkdir -p "$REPO/skills/demo"
cat >"$REPO/skills/demo/SKILL.md" <<'EOF'
---
name: wrong-name
description: demo skill
---

Body.
EOF
git_commit "$REPO" "skill whose frontmatter name doesn't match its folder"
out="$(cd "$REPO" && bin/check.sh --content-only 2>&1)"
status=$?

check "reports the real mismatch" contains "must match its folder" "$out"
check "overall check fails" test "$status" -ne 0

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
