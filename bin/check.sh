#!/usr/bin/env bash
#
# check.sh — repo hygiene checks for claude-kit. Runs locally (directly or via
# the pre-commit hook) and in CI. Exits nonzero if any check fails.
#
# Checks:
#   1. shellcheck — lint the shell scripts (skipped with a notice if not
#      installed locally; CI installs and enforces it)
#   2. frontmatter — every skill/agent has name+description, every command has
#      description (the filename is the command name)
#   3. formatting — no trailing whitespace, every tracked text file ends in a
#      newline
#
# Usage: bin/check.sh
#
set -uo pipefail   # intentionally NOT -e: run every check, then aggregate

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

fail=0
problem() { printf '  ✗ %s\n' "$1"; fail=1; }
ok()      { printf '  ✓ %s\n' "$1"; }

# --- 1. shellcheck ---------------------------------------------------------
echo "shellcheck:"
if command -v shellcheck >/dev/null 2>&1; then
  # Every tracked shell script: bin/*.sh plus the (extensionless) git hooks.
  shell_files=(bin/*.sh .githooks/*)
  if shellcheck "${shell_files[@]}"; then
    ok "shell scripts clean"
  else
    problem "shellcheck reported issues"
  fi
else
  echo "  - shellcheck not installed; skipping (CI enforces this)"
fi

# --- 2. frontmatter --------------------------------------------------------
echo "frontmatter:"
# check_fm FILE KEY... — require a leading --- block containing each KEY.
check_fm() {
  local file="$1"; shift
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

fm_checked=0
for dir in skills/*/; do
  name="$(basename "$dir")"
  case "$name" in _*|.*) continue ;; esac
  [ -f "${dir}SKILL.md" ] || continue
  check_fm "${dir}SKILL.md" name description
  fm_checked=$((fm_checked+1))
done
for f in agents/*.md; do
  [ -e "$f" ] || continue
  case "$(basename "$f")" in _*|.*) continue ;; esac
  check_fm "$f" name description
  fm_checked=$((fm_checked+1))
done
for f in commands/*.md; do
  [ -e "$f" ] || continue
  case "$(basename "$f")" in _*|.*) continue ;; esac
  check_fm "$f" description
  fm_checked=$((fm_checked+1))
done
[ "$fail" -eq 0 ] && ok "${fm_checked} item(s) have valid frontmatter"

# --- 3. formatting ---------------------------------------------------------
echo "formatting:"
fmt_problems=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  case "$f" in *.png|*.jpg|*.jpeg|*.gif|*.ico) continue ;; esac
  if grep -nE '[[:space:]]+$' "$f" >/dev/null 2>&1; then
    problem "$f: trailing whitespace"
    fmt_problems=$((fmt_problems+1))
  fi
  if [ -s "$f" ] && [ -n "$(tail -c1 "$f")" ]; then
    problem "$f: no final newline"
    fmt_problems=$((fmt_problems+1))
  fi
done < <(git ls-files)
[ "$fmt_problems" -eq 0 ] && ok "no trailing whitespace, all files end in newline"

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
      ''|\#*|http://*|https://*|mailto:*) continue ;;   # anchors / external
    esac
    target="${target%%#*}"                              # strip #anchor
    target="${target%% *}"                              # strip " \"title\""
    [ -n "$target" ] || continue
    case "$target" in
      /*) [ -e "$REPO_ROOT$target" ] || [ -e "$target" ] || \
            { problem "$mdfile: link to missing '$target'"; link_problems=$((link_problems+1)); } ;;
      *)  [ -e "$base/$target" ] || \
            { problem "$mdfile: link to missing '$target'"; link_problems=$((link_problems+1)); } ;;
    esac
  done < <(grep -oE '\]\([^)]+\)' "$mdfile" 2>/dev/null | sed -E 's/^\]\(//; s/\)$//')
done < <(git ls-files '*.md')
[ "$link_problems" -eq 0 ] && ok "all repo-relative markdown links resolve"

# --- result ----------------------------------------------------------------
echo
if [ "$fail" -eq 0 ]; then
  echo "All checks passed."
else
  echo "Hygiene checks FAILED."
fi
exit "$fail"
