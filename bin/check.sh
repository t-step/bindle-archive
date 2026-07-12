#!/usr/bin/env bash
#
# check.sh — repo hygiene checks for Bindle. Runs locally (directly or via
# the pre-commit hook) and in CI. Exits nonzero if any check fails.
#
# Checks (shellcheck/shfmt are skipped with a notice if not installed locally;
# CI installs and enforces them):
#   1.  shellcheck   — lint every tracked *.sh, wherever it lives (discovered
#                      via `git ls-files`, minus the documented SH_EXCLUDE
#                      list below — not hardcoded to bin/)
#   1b. shfmt        — consistent shell formatting, same discovered file set
#   2.  Claude frontmatter — every Claude skill/agent has name+description
#                      (command needs description); a skill's name matches its
#                      folder and an agent's matches its filename
#   3.  formatting   — no trailing whitespace, every tracked text file ends in
#                      a newline
#   4.  links        — repo-relative markdown links resolve
#   5.  version      — VERSION is semver and CHANGELOG has an Unreleased section
#   6.  skill scripts— python selftests, discovered by convention: any tracked
#                      skills/<name>/scripts/selftest.py runs automatically
#   7.  private info — bin/check-private-info.sh self-test + full tracked scan
#
# Usage:
#   bin/check.sh                  # full aggregate (make check / CI)
#   bin/check.sh --content-only   # only the Bindle content checks
#                                 # (2,4,5) — the pre-commit framework owns
#                                 # shellcheck/shfmt/formatting at commit time
#
set -uo pipefail # intentionally NOT -e: run every check, then aggregate

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# Tracked *.sh paths (as `git ls-files` prints them) deliberately left out of
# the lint/format discovery below. Keep this narrow, and comment every entry
# with why it's here — an undocumented exclusion is a bug waiting to hide.
SH_EXCLUDE=()

fail=0
problem() {
  printf '  ✗ %s\n' "$1"
  fail=1
}
ok() { printf '  ✓ %s\n' "$1"; }

# --content-only skips shellcheck/shfmt/formatting — the pre-commit framework
# owns those at commit time. The checks unique to Bindle always run, so this
# script stays the full standalone aggregate (make check / CI) with no args.
content_only=false
[ "${1:-}" = "--content-only" ] && content_only=true

if ! $content_only; then
  # Discover every tracked *.sh, wherever it lives, minus SH_EXCLUDE. A plain
  # `while read` loop (not mapfile) keeps this bash-3.2-compatible (macOS
  # default /bin/bash), and `IFS= read -r` handles spaces/unusual chars in a
  # path safely as long as the path itself has no literal newline.
  sh_files=()
  while IFS= read -r f; do
    excluded=false
    if [ "${#SH_EXCLUDE[@]}" -gt 0 ]; then
      for x in "${SH_EXCLUDE[@]}"; do
        [ "$f" = "$x" ] && excluded=true && break
      done
    fi
    $excluded || sh_files+=("$f")
  done < <(git ls-files '*.sh')

  # --- 1. shellcheck -------------------------------------------------------
  echo "shellcheck:"
  if [ "${#sh_files[@]}" -eq 0 ]; then
    echo "  - no tracked shell scripts found"
  elif command -v shellcheck >/dev/null 2>&1; then
    printf '  scanning %d script(s):\n' "${#sh_files[@]}"
    printf '    %s\n' "${sh_files[@]}"
    if shellcheck "${sh_files[@]}"; then
      ok "shell scripts clean"
    else
      problem "shellcheck reported issues"
    fi
  else
    echo "  - shellcheck not installed; skipping (CI enforces this)"
  fi

  # --- 1b. shfmt (formatting) ----------------------------------------------
  echo "shfmt:"
  if [ "${#sh_files[@]}" -eq 0 ]; then
    echo "  - no tracked shell scripts found"
  elif command -v shfmt >/dev/null 2>&1; then
    if shfmt -i 2 -ci -d "${sh_files[@]}" >/dev/null 2>&1; then
      ok "shell formatting consistent"
    else
      problem "shell formatting differs (fix: shfmt -i 2 -ci -w over the scripts listed above)"
    fi
  else
    echo "  - shfmt not installed; skipping (CI enforces this)"
  fi
fi

# --- 2. Claude frontmatter -------------------------------------------------
echo "Claude frontmatter:"
# extract_fm FILE — parse the leading '---'-delimited block ONCE into the
# global fm_block, so every later check (required keys, name lookup) reads
# that same parsed block instead of re-scanning the whole file — a body line
# that happens to start with e.g. "name:" (an example, a quoted config
# snippet) can never leak into validation. Returns/sets:
#   0  ok:            fm_block holds the block's lines (delimiters excluded)
#   1  no frontmatter: first line isn't '---'
#   2  unterminated:  no closing '---' before EOF
#   3  duplicate key: fm_dup_keys holds the offending key name(s)
# Duplicate top-level keys are rejected outright (documented rule) rather than
# silently taking the first or last — an ambiguous file should fail clearly,
# not guess.
extract_fm() {
  local file="$1"
  fm_block=""
  fm_dup_keys=""
  if [ "$(head -1 "$file")" != "---" ]; then
    return 1
  fi
  local close_line
  close_line="$(awk 'NR>1 && /^---[[:space:]]*$/ {print NR; exit}' "$file")"
  if [ -z "$close_line" ]; then
    return 2
  fi
  fm_block="$(sed -n "2,$((close_line - 1))p" "$file")"
  fm_dup_keys="$(grep -oE '^[A-Za-z0-9_-]+:' <<<"$fm_block" | sort | uniq -d | tr '\n' ' ')"
  fm_dup_keys="${fm_dup_keys% }"
  if [ -n "$fm_dup_keys" ]; then
    return 3
  fi
  return 0
}

# check_fm FILE KEY... — extract_fm FILE, then require each KEY present in the
# parsed block. Skips further checks for that file on parse failure (caller
# checks $? / uses fm_block/fm_name_from_block itself when it needs the name).
check_fm() {
  local file="$1"
  shift
  extract_fm "$file"
  case $? in
    1)
      problem "$file: missing frontmatter block"
      return 1
      ;;
    2)
      problem "$file: frontmatter block never closed with a trailing '---'"
      return 1
      ;;
    3)
      problem "$file: frontmatter has duplicate key(s): $fm_dup_keys"
      return 1
      ;;
  esac
  local key
  for key in "$@"; do
    if ! grep -qE "^${key}:" <<<"$fm_block"; then
      problem "$file: frontmatter missing '${key}:'"
    fi
  done
  return 0
}

# fm_name_from_block — print the already-parsed fm_block's 'name:' value
# (empty if absent). Never re-reads the file, so body content is never in
# scope.
fm_name_from_block() { sed -n -E 's/^name:[[:space:]]*//p' <<<"$fm_block" | head -1; }

fm_checked=0
for dir in skills/*/; do
  name="$(basename "$dir")"
  case "$name" in _* | .*) continue ;; esac
  [ -f "${dir}SKILL.md" ] || continue
  fm_checked=$((fm_checked + 1))
  check_fm "${dir}SKILL.md" name description || continue
  got="$(fm_name_from_block)"
  if [ -n "$got" ] && [ "$got" != "$name" ]; then
    problem "${dir}SKILL.md: name '$got' must match its folder '$name'"
  fi
done
for f in agents/*.md; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  case "$base" in _* | .*) continue ;; esac
  fm_checked=$((fm_checked + 1))
  check_fm "$f" name description || continue
  got="$(fm_name_from_block)"
  expected="${base%.md}"
  if [ -n "$got" ] && [ "$got" != "$expected" ]; then
    problem "$f: name '$got' must match its filename '$expected'"
  fi
done
for f in commands/*.md; do
  [ -e "$f" ] || continue
  case "$(basename "$f")" in _* | .*) continue ;; esac
  fm_checked=$((fm_checked + 1))
  check_fm "$f" description || continue
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
# Convention, not configuration: any tracked skills/<name>/scripts/selftest.py
# runs automatically — adding a new scripted skill needs no edit here.
echo "skill-scripts:"
selftests=()
while IFS= read -r f; do
  selftests+=("$f")
done < <(git ls-files 'skills/*/scripts/selftest.py')

if [ "${#selftests[@]}" -eq 0 ]; then
  echo "  - no skill selftests found"
elif command -v python3 >/dev/null 2>&1; then
  for st in "${selftests[@]}"; do
    skill="$(basename "$(dirname "$(dirname "$st")")")"
    echo "  running: $st"
    if python3 "$st" >/dev/null 2>&1; then
      ok "$skill selftests pass"
    else
      problem "$skill selftests failed (run: python3 $st)"
    fi
  done
else
  echo "  - python3 not installed; skipping script selftests"
fi
if [ -f bin/slugify.sh ]; then
  if bin/slugify.sh --self-test >/dev/null 2>&1; then
    ok "slugify self-test passes (session-continuity slug rule)"
  else
    problem "slugify self-test failed (run: bin/slugify.sh --self-test)"
  fi
fi

# --- 6b. capability inventory ----------------------------------------------
# Reconcile capabilities.json against the actual repo. Runs only where the
# validator ships (the real repo); skipped in minimal fixture repos that copy
# check.sh but not check-inventory.py. Skipped with a notice if python3 is
# absent — CI enforces it.
echo "capability inventory:"
if [ ! -f bin/check-inventory.py ]; then
  echo "  - bin/check-inventory.py not present; skipping"
elif ! command -v python3 >/dev/null 2>&1; then
  echo "  - python3 not installed; skipping (CI enforces this)"
elif [ ! -f capabilities.json ]; then
  problem "capabilities.json missing (bin/check-inventory.py is present but the inventory is not)"
else
  if inv_out="$(python3 bin/check-inventory.py --root . 2>&1)"; then
    ok "$inv_out"
  else
    printf '%s\n' "$inv_out" | sed 's/^/  /'
    problem "capability inventory check failed (run: python3 bin/check-inventory.py)"
  fi
fi

# --- 7. private info ---------------------------------------------------------
# Personal-info guard (relay emails, home paths, transcripts, denylist terms).
# Skipped in --content-only: the dedicated pre-commit hook runs it on staged
# files at commit time; here it sweeps every tracked file.
if ! $content_only; then
  echo "private info:"
  if bin/check-private-info.sh --self-test >/dev/null 2>&1 &&
    bin/check-private-info.sh >/dev/null 2>&1; then
    ok "self-test passes; no private info in tracked files"
  else
    problem "private-info scan failed (run bin/check-private-info.sh)"
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
