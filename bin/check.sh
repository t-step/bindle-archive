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
#   5.  version      — VERSION is semver; CHANGELOG has an Unreleased section
#                      unless Release Please owns it (release-please-config.json)
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

# Lines in the installed instruction assets (skills/commands/agents) that mention
# a Bindle-root script (`bin/*.sh`) descriptively rather than as a run
# instruction, so the "Bindle-root path refs" check (section 8) should not flag
# them. Match is a plain substring of the offending line. Keep this narrow and
# comment every entry with why — an undocumented allow is a bug waiting to hide.
PATH_REF_ALLOW=(
  # domi-consumer names the detector once, descriptively ("Where the tools
  # live. Both `bin/domi-status.sh` ..."), before giving the qualified
  # `<bindle>/bin/domi-status.sh` run form a few lines down.
  "Where the tools live"
  # promote-insight names the scanner as the *destination* for a privacy rule
  # ("a `bin/check-private-info.sh` pattern or a denylist term"), not a run.
  "**privacy rule**"
)

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
# DELIBERATE ASYMMETRY (#279): this flags trailing whitespace on every line,
# while pre-commit's `trailing-whitespace` hook runs with
# --markdown-linebreak-ext=md and permits it at the end of a Markdown line
# (intentional hard breaks). So `make check` is STRICTER than the commit hook
# and CI on .md. Left as-is rather than aligned: local-stricter hides no defect
# from a contributor who runs the gates in order, and the stricter rule is the
# one worth keeping visible. Do not "fix" the difference by loosening this.
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
# Release Please owns the changelog when configured (it generates versioned
# sections from Conventional Commits and keeps no hand-maintained Unreleased
# section). Only require Unreleased for the legacy bin/release.sh flow, i.e.
# when release-please-config.json is absent.
if [ ! -f release-please-config.json ] &&
  [ -f CHANGELOG.md ] &&
  ! grep -q '^## \[Unreleased\]' CHANGELOG.md; then
  problem "CHANGELOG.md missing '## [Unreleased]' section"
fi

# --- 5b. product boundary (staleness) ---------------------------------------
# docs/product-boundary.md is the scope gate every "deliberately out of scope"
# call rests on. It lapsed once (#283) by carrying a version range in its title
# that expired with no event to announce it — ~200 issues accumulated against a
# document that had quietly stopped applying. The `Affirmed through:` line
# replaces that silent expiry with a mechanical one: the document must name a
# minor at least as new as VERSION's, so cutting a minor forces an explicit
# re-affirm-or-amend. Patch releases are exempt — a boundary document has
# nothing to say about a patch.
#
# Affirmed AHEAD of VERSION passes: VERSION lags merged work (#265), and
# affirming the boundary before the cut is the desired order, not a defect.
#
# Deliberately NOT behind --content-only: a cheap text comparison with no
# external tool dependency, so it must reach the pre-commit hook and CI, not
# only a local `make check` (the #279 lesson).
echo "product boundary:"
boundary_doc="docs/product-boundary.md"
if [ ! -f "$boundary_doc" ]; then
  # Absent = nothing to affirm. NOT a failure here: check.sh is copied into
  # throwaway fixture repos by several test suites, and requiring this file
  # would couple every one of those fixture builders to it — the "maintain two
  # lists" defect. Deletion in the real repo is already loud: three
  # capabilities.json entries list this file under related_docs, so
  # bin/check-inventory.py (section 6b) fails if it disappears.
  echo "  - no $boundary_doc; skipping (inventory owns its existence)"
elif ! grep -q '^Affirmed through:' "$boundary_doc"; then
  problem "$boundary_doc has no 'Affirmed through:' line (see its Revisit triggers)"
else
  affirmed="$(sed -n 's/^Affirmed through:[[:space:]]*//p' "$boundary_doc" | head -1 | tr -d '[:space:]')"
  if ! [[ "$affirmed" =~ ^v[0-9]+\.[0-9]+$ ]]; then
    problem "$boundary_doc: 'Affirmed through: $affirmed' is not vMAJOR.MINOR"
  elif [ -f VERSION ] && [[ "$(cat VERSION)" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    a_rest="${affirmed#v}"
    a_maj="${a_rest%%.*}"
    a_min="${a_rest#*.}"
    v_maj="$(cut -d. -f1 <VERSION)"
    v_min="$(cut -d. -f2 <VERSION)"
    if [ "$a_maj" -lt "$v_maj" ] ||
      { [ "$a_maj" -eq "$v_maj" ] && [ "$a_min" -lt "$v_min" ]; }; then
      problem "$boundary_doc affirmed through $affirmed, but VERSION is $(cat VERSION) — re-read the boundary, then update 'Affirmed through:' or amend the document"
    else
      ok "boundary current for VERSION $(cat VERSION) (affirmed $affirmed)"
    fi
  fi
  # A missing/malformed VERSION is already reported by section 5; don't
  # double-report it here.
fi

# --- 5c. Codex provider-doc drift -------------------------------------------
# capabilities.json is the source of truth for which skills Codex installs;
# hand-written prose is not, and drifted from it (#290/#291): README.md's
# GENERATED block said Codex installs skills two lines above a hand-written
# paragraph still saying it installs `global/AGENTS.md` and nothing else.
# bin/check-inventory.py can't catch that — it only governs text inside
# `<!-- GENERATED:... -->` markers, and the stale line sat outside them.
#
# So: while any skill carries provider.codex "installed", every user-facing
# install doc that exists must name `--agents-skills-home`, and no live doc may
# carry a current-state AGENTS.md-only claim. Narrow by construction — a fixed
# doc list and two literal claim patterns, not a prose linter.
#
# Deliberately NOT behind --content-only: pure text + one json read, no
# external tool beyond python3, so it must reach the pre-commit hook and CI,
# not only a local `make check` (the #279 lesson).
#
# Skips on a missing capabilities.json for the section-5b reason: check.sh is
# copied into throwaway fixture repos by several suites, and requiring the
# manifest would couple every fixture builder to it.

# Docs a reader consults to learn how a Codex install works. Each is checked
# only if present.
CODEX_INSTALL_DOCS=(
  README.md
  CONTRIBUTING.md
  AGENTS.md
  global/AGENTS.md
  docs/using-bindle-with-codex.md
  docs/provider-interop.md
  docs/ownership-boundaries.md
  docs/sharing-skills.md
)

# Paths that describe what WAS true. A changelog entry and a dated design or
# plan record are supposed to preserve the old claim verbatim; rewording them
# would falsify the record.
CODEX_DRIFT_SKIP_PATHS=(
  CHANGELOG.md
  'docs/design/'
  'docs/plans/'
  'docs/superpowers/plans/'
)

# Lines that mention the old behavior correctly — by negating it — and so are
# not stale claims. Match is a plain substring. Keep narrow and comment every
# entry with why, same discipline as PATH_REF_ALLOW.
CODEX_DRIFT_ALLOW=(
  # using-bindle-with-codex tells the reader the two-target install is the only
  # one: "Omitting the second one exits 2 ... so there is no AGENTS.md-only
  # install to run first." The phrase is the correction, not the drift.
  "no AGENTS.md-only install"
)

echo "codex provider docs:"
codex_installed=0
if [ -f capabilities.json ]; then
  codex_installed="$(python3 -c '
import json, sys
try:
    caps = json.load(open("capabilities.json")).get("capabilities", [])
except Exception:
    print(0); sys.exit()
print(sum(1 for c in caps
          if c.get("type") == "skill"
          and c.get("provider", {}).get("codex") == "installed"))
' 2>/dev/null || echo 0)"
fi

if [ ! -f capabilities.json ]; then
  echo "  - no capabilities.json; skipping (inventory owns its existence)"
elif [ "$codex_installed" -eq 0 ]; then
  echo "  - no Codex-installed skills; skipping"
else
  codex_doc_problems=0
  for doc in "${CODEX_INSTALL_DOCS[@]}"; do
    [ -f "$doc" ] || continue
    if ! grep -qF -- '--agents-skills-home' "$doc"; then
      problem "$doc: no mention of --agents-skills-home, but $codex_installed skill(s) are Codex-installed"
      codex_doc_problems=$((codex_doc_problems + 1))
    fi
  done

  while IFS= read -r mdfile; do
    [ -f "$mdfile" ] || continue
    # Length-guard both array expansions: under `set -u`, bash 3.2 (macOS)
    # treats "${arr[@]}" on an empty array as unbound and aborts the run.
    skip=0
    if [ "${#CODEX_DRIFT_SKIP_PATHS[@]}" -gt 0 ]; then
      for p in "${CODEX_DRIFT_SKIP_PATHS[@]}"; do
        case "$mdfile" in "$p"* | "./$p"*) skip=1 && break ;; esac
      done
    fi
    [ "$skip" -eq 1 ] && continue
    lineno=0
    while IFS= read -r line; do
      lineno=$((lineno + 1))
      allowed=0
      if [ "${#CODEX_DRIFT_ALLOW[@]}" -gt 0 ]; then
        for a in "${CODEX_DRIFT_ALLOW[@]}"; do
          case "$line" in *"$a"*) allowed=1 && break ;; esac
        done
      fi
      [ "$allowed" -eq 1 ] && continue
      # Two literal claim shapes, both meaning "Codex gets AGENTS.md and
      # nothing else": the prose form and the compound-adjective form.
      if grep -qiE 'installs? only [^.]{0,20}AGENTS\.md|AGENTS\.md-only' <<<"$line"; then
        problem "$mdfile:$lineno: stale Codex claim — skills are Codex-installed now; reword or move it to a historical record"
        codex_doc_problems=$((codex_doc_problems + 1))
      fi
    done <"$mdfile"
  done < <(git ls-files '*.md')

  [ "$codex_doc_problems" -eq 0 ] &&
    ok "codex provider docs consistent with capabilities.json ($codex_installed installed skill(s))"
fi

# --- 5d. CodeGraph guidance drift ------------------------------------------
# global/CLAUDE.md and global/AGENTS.md both install into provider-specific
# global instruction surfaces. The CodeGraph rule drifted twice (#314), once
# toward the exact opposite behavior ("CodeGraph before grep"). The AGENTS.md
# delimiters are useful install/update seams, but they also make clobbering the
# fixed prose easy, so gate the shared behavioral assertions:
#   - CodeGraph only pays off around a 6+ file orientation threshold;
#   - for narrow follow-up, grep + Read is cheaper;
#   - the Codex block must never say CodeGraph before grep.
#
# Deliberately NOT behind --content-only: pure text checks, so it must reach
# the commit hook and CI, not only local make check.
echo "CodeGraph guidance:"
if [ ! -f global/CLAUDE.md ] || [ ! -f global/AGENTS.md ]; then
  echo "  - provider guidance file(s) absent; skipping"
else
  codegraph_problems=0
  claude_codegraph="$(grep -i 'CodeGraph' global/CLAUDE.md || true)"
  agents_codegraph="$(
    awk '
      /<!-- CODEGRAPH_START -->/ { found_start = 1; in_block = 1; next }
      /<!-- CODEGRAPH_END -->/ { if (in_block) { found_end = 1; in_block = 0; next } }
      in_block { print }
      END { if (!found_start || !found_end) exit 2 }
    ' global/AGENTS.md
  )"
  agents_status=$?

  if [ "$agents_status" -ne 0 ]; then
    problem "global/AGENTS.md: missing CODEGRAPH_START/CODEGRAPH_END block"
    codegraph_problems=$((codegraph_problems + 1))
  fi

  check_codegraph_text() { # check_codegraph_text LABEL TEXT
    local label="$1"
    local text="$2"
    if ! grep -qiE '6\+[^[:alnum:]]*file|6\+ files|6\+-file' <<<"$text"; then
      problem "$label: CodeGraph guidance must state the 6+ file threshold"
      codegraph_problems=$((codegraph_problems + 1))
    fi
    if ! grep -qiE 'grep[[:space:]]*\+?[[:space:]]*Read|grep.*Read' <<<"$text"; then
      problem "$label: CodeGraph guidance must prefer grep + Read for narrow follow-up"
      codegraph_problems=$((codegraph_problems + 1))
    fi
    if grep -qiE 'codegraph[^.]{0,80}before[^.]{0,40}grep|before[^.]{0,40}grep[^.]{0,80}codegraph' <<<"$text"; then
      problem "$label: CodeGraph guidance says CodeGraph before grep"
      codegraph_problems=$((codegraph_problems + 1))
    fi
  }

  check_codegraph_text "global/CLAUDE.md" "$claude_codegraph"
  if [ "$agents_status" -eq 0 ]; then
    check_codegraph_text "global/AGENTS.md" "$agents_codegraph"
  fi
  [ "$codegraph_problems" -eq 0 ] &&
    ok "CodeGraph guidance consistent across global/CLAUDE.md and global/AGENTS.md"
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
  if inv_out="$(python3 bin/check-inventory.py --root . --check-manifest --check-docs 2>&1)"; then
    ok "$inv_out"
  else
    printf '%s\n' "$inv_out" | sed 's/^/  /'
    problem "capability inventory check failed (run: python3 bin/check-inventory.py)"
  fi
fi

# --- 6b2. finding-code coverage --------------------------------------------
# Every finding code a validator can emit must be classified in its surface's
# invariant-coverage.json or explicitly excluded with a reason. Without this,
# a new code is simply absent from the schema-vs-native reasoning and both
# suites stay green while one direction of its invariant goes unasserted.
# Same skip discipline as 6b: absent validator or python3 is a notice, not a
# failure, so a minimal fixture repo can still run check.sh.
echo "finding-code coverage:"
if [ ! -f bin/check-finding-codes.py ]; then
  echo "  - bin/check-finding-codes.py not present; skipping"
elif ! command -v python3 >/dev/null 2>&1; then
  echo "  - python3 not installed; skipping (CI enforces this)"
else
  if codes_out="$(python3 bin/check-finding-codes.py --root . 2>&1)"; then
    ok "$codes_out"
  else
    printf '%s\n' "$codes_out" | sed 's/^/  /'
    problem "finding-code coverage failed (run: python3 bin/check-finding-codes.py)"
  fi
fi

# --- 6c. Bindle-root path refs ---------------------------------------------
# The installed instruction assets (skills/commands/agents) run from the cwd of
# whatever project you're working in, NOT the Bindle checkout. A run instruction
# that names a Bindle-root script by a bare, repo-relative path (`bin/foo.sh`)
# misresolves there — worst case, a privacy scan the recipe blocks on is
# silently skipped (issue #113). Require such refs to be `<bindle>/`-qualified.
# Frontmatter is skipped (permission globs like `Bash(bin/x.sh:*)` aren't run
# instructions); PATH_REF_ALLOW covers documented descriptive mentions.
echo "Bindle-root path refs:"
pathref_problems=0
while IFS= read -r mdfile; do
  [ -f "$mdfile" ] || continue
  in_fm=0 lineno=0
  while IFS= read -r line; do
    lineno=$((lineno + 1))
    # Skip the leading YAML frontmatter block (--- ... ---).
    if [ "$lineno" -eq 1 ] && [ "$line" = "---" ]; then
      in_fm=1
      continue
    fi
    if [ "$in_fm" -eq 1 ]; then
      [ "$line" = "---" ] && in_fm=0
      continue
    fi
    # Documented descriptive mentions are not run instructions.
    allowed=0
    if [ "${#PATH_REF_ALLOW[@]}" -gt 0 ]; then
      for a in "${PATH_REF_ALLOW[@]}"; do
        case "$line" in *"$a"*) allowed=1 && break ;; esac
      done
    fi
    [ "$allowed" -eq 1 ] && continue
    # Inspect each inline-code span; flag a bin/*.sh not `<bindle>/`-qualified.
    # shellcheck disable=SC2016  # the backticks are a literal regex, not expansion
    spans="$(grep -oE '`[^`]+`' <<<"$line")"
    while IFS= read -r span; do
      [ -n "$span" ] || continue
      stripped="$(sed -E 's#<bindle>/bin/[a-zA-Z0-9_-]+\.sh##g' <<<"$span")"
      bad="$(grep -oE 'bin/[a-zA-Z0-9_-]+\.sh' <<<"$stripped" | head -1)"
      if [ -n "$bad" ]; then
        problem "$mdfile:$lineno: bare run-ref \`$bad\` — qualify with <bindle>/ or add to PATH_REF_ALLOW"
        pathref_problems=$((pathref_problems + 1))
      fi
    done <<<"$spans"
  done <"$mdfile"
done < <(git ls-files 'skills/*/SKILL.md' 'commands/*.md' 'agents/*.md')
[ "$pathref_problems" -eq 0 ] && ok "all Bindle-root tool refs are <bindle>/-qualified"

# --- 7. private info ---------------------------------------------------------
# Personal-info guard (relay emails, home paths, transcripts, denylist terms).
# Skipped in --content-only: the dedicated pre-commit hook runs it on staged
# files at commit time; here it sweeps every tracked file.
#
# Who runs which half (#279) — the two halves reach different gates:
#   --self-test  also runs from bin/test-check-private-info.sh, which
#                `bindle-test-suites` discovers, so it reaches the commit hook
#                and CI. That suite and this call site invoke the SAME
#                entrypoint, so they cannot silently diverge; the suite adds a
#                coverage floor and mutation cases this call site can't express.
#   full sweep   stays here and in the `bindle-private-info` hook. Deliberately
#                NOT in the suite: a tree sweep per suite run would execute it
#                twice at commit time for no added coverage.
if ! $content_only; then
  echo "private info:"
  if bin/check-private-info.sh --self-test >/dev/null 2>&1 &&
    bin/check-private-info.sh >/dev/null 2>&1; then
    ok "self-test passes; no private info in tracked files"
  else
    problem "private-info scan failed (run bin/check-private-info.sh)"
  fi
fi

# --- scan scope (#347) ------------------------------------------------------
# Every section above enumerates its work with `git ls-files`, so an UNTRACKED
# file is outside all of them — and the verdict below then reads as a statement
# about the whole tree. PR #345 shipped three private-path hits through that
# gap: this run was green before `git add` and the pre-commit hook, which sees
# staged content, was red on the same three lines minutes later. The scan is
# correct; what was broken is that its result did not disclose its own scope.
# Ignored files are out of scope by intent and are not counted — a banner that
# fires in every repo with build output is a banner nobody reads.
#
# The exit code is deliberately unchanged: `make check` is run mid-edit, and a
# gate that fails whenever the tree is untidy gets bypassed rather than heeded.
# This runs under --content-only too (the #279 lesson): a disclosure only the
# local `make check` prints is one the commit hook and CI never make.
skipped="$(git ls-files --others --exclude-standard)"
partial=false
if [ -n "$skipped" ]; then
  partial=true
  skipped_n="$(grep -c . <<<"$skipped")"
  echo
  echo "scan scope:"
  echo "  PARTIAL: $skipped_n untracked file(s) were NOT scanned by any check —"
  head -n 10 <<<"$skipped" | while IFS= read -r p; do echo "    $p"; done
  [ "$skipped_n" -gt 10 ] && echo "    … and $((skipped_n - 10)) more"
  echo "    stage them (git add) and re-run before quoting this result."
fi

# --- stale reps (#339) ------------------------------------------------------
# A skill whose content changed since its newest hashed rep series is carrying
# evidence about text that no longer ships. Warn-only by the recorded #339
# decision (docs/superpowers/specs/2026-07-22-rep-content-identity-design.md):
# a hard gate would couple every routine SKILL.md edit to a fresh 5-rep
# campaign (#335 floor) and would be bypassed rather than heeded. Skills whose
# series are all `unrecorded` (grandfathered) exit 2, not 1, so this banner
# starts empty and only ever names genuine post-#339 drift.
if [ -x bin/skill-content-id.sh ]; then
  stale_reps="$(bin/skill-content-id.sh --check --all 2>/dev/null | grep ': STALE' || true)"
  if [ -n "$stale_reps" ]; then
    echo
    echo "stale reps:"
    echo "  WARN (warn-only, #339): skill content changed since the newest hashed rep series —"
    while IFS= read -r p; do echo "    $p"; done <<<"$stale_reps"
    echo "    run bin/skill-content-id.sh --check <skill> for the per-series report."
  fi
fi

# --- result ----------------------------------------------------------------
echo
if [ "$fail" -eq 0 ]; then
  if $partial; then
    echo "Checks passed — PARTIAL: $skipped_n untracked file(s) not scanned."
  else
    echo "All checks passed."
  fi
else
  echo "Hygiene checks FAILED."
fi
exit "$fail"
