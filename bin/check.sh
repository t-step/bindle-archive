#!/usr/bin/env bash
#
# check.sh — repo hygiene checks for claude-kit. Runs locally (directly or via
# the pre-commit hook) and in CI. Exits nonzero if any check fails.
#
# Checks (shellcheck/shfmt are skipped with a notice if not installed locally;
# CI installs and enforces them):
#   1.  shellcheck   — lint the shell scripts
#   1b. shfmt        — consistent shell formatting
#   2.  frontmatter  — every skill/agent has name+description (command needs
#                      description); a skill's name matches its folder and an
#                      agent's matches its filename
#   3.  formatting   — no trailing whitespace, every tracked text file ends in
#                      a newline
#   4.  links        — repo-relative markdown links resolve
#   5.  version      — VERSION is semver and CHANGELOG has an Unreleased section
#
# Usage:
#   bin/check.sh                  # full aggregate (make check / CI)
#   bin/check.sh --content-only   # only the claude-kit-specific checks
#                                 # (2,4,5) — the pre-commit framework owns
#                                 # shellcheck/shfmt/formatting at commit time
#
set -uo pipefail # intentionally NOT -e: run every check, then aggregate

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

fail=0
problem() {
  printf '  ✗ %s\n' "$1"
  fail=1
}
ok() { printf '  ✓ %s\n' "$1"; }

# --content-only skips shellcheck/shfmt/formatting — the pre-commit framework
# owns those at commit time. The checks unique to claude-kit always run, so this
# script stays the full standalone aggregate (make check / CI) with no args.
content_only=false
[ "${1:-}" = "--content-only" ] && content_only=true

if ! $content_only; then
  # --- 1. shellcheck -------------------------------------------------------
  echo "shellcheck:"
  if command -v shellcheck >/dev/null 2>&1; then
    if shellcheck bin/*.sh; then
      ok "shell scripts clean"
    else
      problem "shellcheck reported issues"
    fi
  else
    echo "  - shellcheck not installed; skipping (CI enforces this)"
  fi

  # --- 1b. shfmt (formatting) ----------------------------------------------
  echo "shfmt:"
  if command -v shfmt >/dev/null 2>&1; then
    if shfmt -i 2 -ci -d bin/*.sh >/dev/null 2>&1; then
      ok "shell formatting consistent"
    else
      problem "shell formatting differs (fix: shfmt -i 2 -ci -w bin/*.sh)"
    fi
  else
    echo "  - shfmt not installed; skipping (CI enforces this)"
  fi
fi

# --- 2. frontmatter --------------------------------------------------------
echo "frontmatter:"
# check_fm FILE KEY... — require a leading --- block containing each KEY.
check_fm() {
  local file="$1"
  shift
  if [ "$(head -1 "$file")" != "---" ]; then
    problem "$file: missing frontmatter block"
    return
  fi
  local fm key
  fm="$(awk 'NR==1 {next} /^---[[:space:]]*$/ {exit} {print}' "$file")"
  for key in "$@"; do
    if ! grep -qE "^${key}:" <<<"$fm"; then
      problem "$file: frontmatter missing '${key}:'"
    fi
  done
}

# fm_name FILE — print the frontmatter 'name:' value (empty if none).
fm_name() { sed -n -E 's/^name:[[:space:]]*//p' "$1" | head -1; }

fm_checked=0
for dir in skills/*/; do
  name="$(basename "$dir")"
  case "$name" in _* | .*) continue ;; esac
  [ -f "${dir}SKILL.md" ] || continue
  check_fm "${dir}SKILL.md" name description
  got="$(fm_name "${dir}SKILL.md")"
  if [ -n "$got" ] && [ "$got" != "$name" ]; then
    problem "${dir}SKILL.md: name '$got' must match its folder '$name'"
  fi
  fm_checked=$((fm_checked + 1))
done
for f in agents/*.md; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  case "$base" in _* | .*) continue ;; esac
  check_fm "$f" name description
  got="$(fm_name "$f")"
  expected="${base%.md}"
  if [ -n "$got" ] && [ "$got" != "$expected" ]; then
    problem "$f: name '$got' must match its filename '$expected'"
  fi
  fm_checked=$((fm_checked + 1))
done
for f in commands/*.md; do
  [ -e "$f" ] || continue
  case "$(basename "$f")" in _* | .*) continue ;; esac
  check_fm "$f" description
  fm_checked=$((fm_checked + 1))
done
[ "$fail" -eq 0 ] && ok "${fm_checked} item(s) have valid frontmatter"

# --- 3. formatting ---------------------------------------------------------
if ! $content_only; then
  echo "formatting:"
  fmt_problems=0
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    case "$f" in *.png | *.jpg | *.jpeg | *.gif | *.ico) continue ;; esac
    if grep -nE '[[:space:]]+$' "$f" >/dev/null 2>&1; then
      problem "$f: trailing whitespace"
      fmt_problems=$((fmt_problems + 1))
    fi
    if [ -s "$f" ] && [ -n "$(tail -c1 "$f")" ]; then
      problem "$f: no final newline"
      fmt_problems=$((fmt_problems + 1))
    fi
  done < <(git ls-files)
  [ "$fmt_problems" -eq 0 ] && ok "no trailing whitespace, all files end in newline"
fi

# --- 4. links --------------------------------------------------------------
# Catch markdown that points at a repo file/path that no longer exists. We only
# resolve repo-relative targets: [text](path), @path mentions, and ](#...) is
# skipped (in-page anchors). External URLs and frontmatter are left alone — we
# never touch the wording Claude reads, only verify referenced files exist.
echo "links:"
link_problems=0
while IFS= read -r mdfile; do
  [ -f "$mdfile" ] || continue
  base="$(dirname "$mdfile")"
  # Pull markdown link targets: the (...) part of [text](target).
  while IFS= read -r target; do
    case "$target" in
      '' | \#* | http://* | https://* | mailto:*) continue ;; # anchors / external
    esac
    target="${target%%#*}" # strip #anchor
    target="${target%% *}" # strip " \"title\""
    [ -n "$target" ] || continue
    case "$target" in
      /*) [ -e "$REPO_ROOT$target" ] || [ -e "$target" ] ||
        {
          problem "$mdfile: link to missing '$target'"
          link_problems=$((link_problems + 1))
        } ;;
      *) [ -e "$base/$target" ] ||
        {
          problem "$mdfile: link to missing '$target'"
          link_problems=$((link_problems + 1))
        } ;;
    esac
  done < <(grep -oE '\]\([^)]+\)' "$mdfile" 2>/dev/null | sed -E 's/^\]\(//; s/\)$//')
done < <(git ls-files '*.md')
[ "$link_problems" -eq 0 ] && ok "all repo-relative markdown links resolve"

# --- 5. version ------------------------------------------------------------
echo "version:"
if [ ! -f VERSION ]; then
  problem "VERSION file missing"
elif ! [[ "$(cat VERSION)" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  problem "VERSION ('$(cat VERSION)') is not semver MAJOR.MINOR.PATCH"
else
  ok "VERSION is valid semver ($(cat VERSION))"
fi
if [ -f CHANGELOG.md ] && ! grep -q '^## \[Unreleased\]' CHANGELOG.md; then
  problem "CHANGELOG.md missing '## [Unreleased]' section"
fi

# --- 6. skill scripts (python selftests) -----------------------------------
echo "skill-scripts:"
lca_selftest="skills/license-compliance-auditor/scripts/selftest.py"
if [ -f "$lca_selftest" ]; then
  if command -v python3 >/dev/null 2>&1; then
    if python3 "$lca_selftest" >/dev/null 2>&1; then
      ok "license-compliance-auditor selftests pass"
    else
      problem "license-compliance-auditor selftests failed (run: python3 $lca_selftest)"
    fi
  else
    echo "  - python3 not installed; skipping script selftests"
  fi
fi

# --- result ----------------------------------------------------------------
echo
if [ "$fail" -eq 0 ]; then
  echo "All checks passed."
else
  echo "Hygiene checks FAILED."
fi
exit "$fail"
