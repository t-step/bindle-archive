#!/usr/bin/env bash
#
# facts-index.sh — print one line per durable fact in the current project's
# notes home, as <slug><TAB><type><TAB><description>, sorted by slug.
#
# The index, never a body: this reads only the leading '---'-delimited
# frontmatter block of each facts/<slug>.md, so its cost is bounded by fact
# COUNT, not fact size. Selecting which bodies to then read is the model's job
# (docs/superpowers/specs/2026-07-26-facts-loader-phase2a-design.md,
# constraint 3) — Bindle ships no ranker.
#
# Usage:
#   bin/facts-index.sh [--cwd DIR] [--home DIR]
#
#   --cwd DIR   directory to orient from (default: $PWD)
#   --home DIR  Claude home override, for notes-home resolution parity with
#               bin/session-context.sh (tests only; does not affect real installs)
#
# Read-only toward the notes home: never writes, never bumps `modified`, never
# repairs frontmatter (#423 owns validation). Degrades silently — no notes
# home, no facts/ dir, or an empty one prints nothing and exits 0. A MALFORMED
# fact is listed with an empty type/description rather than skipped: an
# invisible fact is worse than an ugly line.
#
# Exit codes: 0 always, except 2 for a usage error (bad flag/missing argument).
#
set -uo pipefail

CWD="$PWD"

while [ $# -gt 0 ]; do
  case "$1" in
    --cwd)
      [ $# -ge 2 ] || {
        echo "facts-index.sh: --cwd needs a directory argument" >&2
        exit 2
      }
      CWD="$2"
      shift 2
      ;;
    --home)
      [ $# -ge 2 ] || {
        echo "facts-index.sh: --home needs a directory argument" >&2
        exit 2
      }
      CLAUDE_HOME_OVERRIDE="$2"
      shift 2
      ;;
    *)
      echo "facts-index.sh: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# --- notes-home resolution (mirrors bin/session-context.sh's chain) ----------
#
# The persisted settings.json read is what makes this work for a CODEX session,
# which never inherits Claude Code's env block. bin/notes-home.sh's chain stops
# at the environment; this one does not. The deprecated ~/.claude-kit READ
# fallback in bin/check-private-info.sh is deliberately absent: facts/ is a
# Phase 1 (2026-07) construct, so no fact can predate the rename.

resolve_notes_home() {
  if [ -n "${BINDLE_NOTES_DIR:-}" ]; then
    NOTES_DIR="$BINDLE_NOTES_DIR"
  elif [ -n "${CLAUDE_KIT_NOTES_DIR:-}" ]; then
    NOTES_DIR="$CLAUDE_KIT_NOTES_DIR"
  else
    local claude_home="${CLAUDE_HOME_OVERRIDE:-${HOME}/.claude}"
    local persisted=""
    if [ -f "$claude_home/settings.json" ]; then
      persisted="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("env", {}).get("BINDLE_NOTES_DIR", ""))
except Exception:
    print("")' "$claude_home/settings.json" 2>/dev/null)"
    fi
    if [ -n "$persisted" ]; then
      NOTES_DIR="$persisted"
    else
      NOTES_DIR="${HOME}/.bindle"
    fi
  fi
}

# --- project identity (same rule as bin/session-context.sh) -----------------

REPO_ROOT="$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$REPO_ROOT" ]; then
  PROJECT_DIR="$REPO_ROOT"
else
  PROJECT_DIR="$CWD"
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(basename "$PROJECT_DIR" | "$SCRIPT_DIR/slugify.sh" 2>/dev/null || basename "$PROJECT_DIR")"

# --- frontmatter parsing ----------------------------------------------------

# fm_block FILE — print the leading '---'-delimited block (delimiters
# excluded), or nothing when the file has no terminated block. Parsing ONCE
# into this block is what stops a body line that happens to start with
# "description:" from leaking into a field (bin/check.sh's extract_fm makes the
# same argument for Claude frontmatter).
fm_block() {
  local file="$1" close
  [ "$(head -1 "$file" 2>/dev/null)" = "---" ] || return 0
  close="$(awk 'NR>1 && /^---[[:space:]]*$/ {print NR; exit}' "$file")"
  [ -n "$close" ] || return 0
  sed -n "2,$((close - 1))p" "$file"
}

# clean_field TEXT — one safe TSV field: strip a matched pair of surrounding
# quotes, turn any embedded tab into a space (a tab in a description must not
# forge a fourth column), and trim the edges.
clean_field() {
  local v="$1"
  case "$v" in
    \"*\") v="${v#\"}" && v="${v%\"}" ;;
    \'*\') v="${v#\'}" && v="${v%\'}" ;;
  esac
  printf '%s' "$v" | tr '\t' ' ' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# fm_top BLOCK KEY — value of a top-level frontmatter key (first occurrence).
fm_top() {
  sed -n -E "s/^$2:[[:space:]]*//p" <<<"$1" | head -1
}

# fm_meta BLOCK KEY — value of an INDENTED key under `metadata:`. The schema
# nests type/modified there (session-continuity SKILL.md, "Fact files"), so a
# top-level match would silently miss them.
fm_meta() {
  awk -v key="$2" '
    /^metadata:[[:space:]]*$/ { inmeta = 1; next }
    /^[^[:space:]]/ { inmeta = 0 }
    inmeta && $0 ~ "^[[:space:]]+" key ":" {
      sub("^[[:space:]]+" key ":[[:space:]]*", "")
      print
      exit
    }
  ' <<<"$1"
}

# --- enumeration ------------------------------------------------------------

resolve_notes_home
FACTS_DIR="$NOTES_DIR/projects/$PROJECT/facts"
[ -d "$FACTS_DIR" ] || exit 0

emit_fact() {
  local file="$1" block slug type desc
  block="$(fm_block "$file")"
  slug="$(clean_field "$(fm_top "$block" name)")"
  [ -n "$slug" ] || slug="$(basename "$file" .md)"
  type="$(clean_field "$(fm_meta "$block" type)")"
  desc="$(clean_field "$(fm_top "$block" description)")"
  printf '%s\t%s\t%s\n' "$slug" "$type" "$desc"
}

{
  for f in "$FACTS_DIR"/*.md; do
    [ -f "$f" ] || continue
    [ "$(basename "$f")" = "MEMORY.md" ] && continue
    emit_fact "$f"
  done
} | LC_ALL=C sort
exit 0
