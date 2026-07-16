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
  printf '0.1.0\n' >"$r/version.txt"
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
# No release-please-config.json → an Unreleased section is required, and its
# absence is a problem.
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
echo "retired release fallbacks are absent from live surfaces:"
out="$(
  python3 - "$REPO_ROOT" <<'PY'
import os
import re
import subprocess
import sys

root = os.path.realpath(sys.argv[1])
historical = (
    "docs/design/",
    "docs/plans/",
    "docs/superpowers/specs/",
    "docs/superpowers/plans/",
)
patterns = (
    re.compile(r"(?<![A-Za-z0-9_])VER" + r"SION(?![A-Za-z0-9_])"),
    re.compile(r"RELEASE-MANIFEST" + r"\.json"),
    re.compile(r"bin/release" + r"\.sh"),
    re.compile(r"\bmake[ \t]+release\b"),
    re.compile(r"extra-files[^\n]*VER" + r"SION"),
)


def allowed_history(path):
    return path == "CHANGELOG.md" or path.startswith(historical)


def allowed_negative_test(path, line):
    if path == "bin/test-release-publication.sh":
        return (
            '"RELEASE-MANIFEST' + '.json"' in line
            or "Historical prose mentions gh release create and RELEASE-MANIFEST" + ".json." in line
        )
    if path == "bin/test-release-strategy.sh":
        return 'os.path.join(root, "VER' + 'SION")' in line
    if path == "skills/release-captain/PRESSURE-TESTS.md":
        fragments = (
            "with a `VER" + "SION`",
            "bumped VER" + "SION",
            "bumped `VER" + "SION`",
            "new tag / VER" + "SION bump",
            "`VER" + "SION`, edits",
            "bumps VER" + "SION",
            "edit VER" + "SION/CHANGELOG",
        )
        return any(fragment in line for fragment in fragments)
    return False


tracked = subprocess.check_output(
    ["git", "-C", root, "ls-files", "-z"], text=True
).split("\0")
failures = []
for path in tracked:
    if not path or allowed_history(path):
        continue
    if path == "VER" + "SION":
        failures.append(f"{path}: root retired version path exists")
        continue
    full = os.path.join(root, path)
    try:
        with open(full, encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, UnicodeDecodeError):
        continue
    for number, line in enumerate(lines, 1):
        if any(pattern.search(line) for pattern in patterns):
            if allowed_negative_test(path, line):
                continue
            failures.append(f"{path}:{number}:{line.rstrip()}")

print("\n".join(failures))
raise SystemExit(bool(failures))
PY
)"
status=$?
[ "$status" -eq 0 ] || printf '%s\n' "$out"

check "live files contain no retired release fallback" test "$status" -eq 0
check "fallback scan reports no forbidden paths" test -z "$out"

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
