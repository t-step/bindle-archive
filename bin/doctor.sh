#!/usr/bin/env bash
#
# doctor.sh — read-only diagnostics for a Bindle installation. Reports the
# health of every item install.sh would manage, without writing anything
# anywhere: no mkdir, no touch, no file creation — not even in /tmp. Every
# operation below is a stat/readlink/read.
#
# For each expected (src, dest) pair — the same items install.sh's
# install_claude/install_codex would link — the destination is classified as:
#   current           symlink already points at the current source
#   missing           nothing installed at dest yet
#   stale             owned symlink pointing at a different, still-existing
#                     item inside this repo
#   broken            owned symlink whose target no longer exists
#   earlier-checkout  symlink outside this repo whose target is missing but
#                     whose path looks like an earlier Bindle checkout
#                     (detection only, never a claim of ownership — run
#                     bin/install.sh --adopt to preview + confirm relinking,
#                     or see docs/ownership-boundaries.md)
#   conflict          anything else foreign: a real file/dir, or a symlink
#                     owned by something else
#
# Each managed directory (skills/, agents/, commands/ under the Claude home)
# is also swept for broken owned symlinks that are no longer among the
# expected items (deleted/renamed items); foreign entries in the sweep are
# ignored. The notes-home resolution (docs/notes-home.md) and common dev-tool
# availability are reported too.
#
# Usage:
#   bin/doctor.sh                     # diagnose ~/.claude
#   bin/doctor.sh --home DIR          # diagnose a different Claude home
#   bin/doctor.sh --codex-home DIR    # also diagnose a Codex AGENTS.md target
#   bin/doctor.sh --agents-skills-home DIR   # also diagnose Codex Agent Skills
#   bin/doctor.sh --bin-dir DIR       # diagnose bindle executable target
#
# Exit codes:
#   0  no findings (everything current, or nothing to report)
#   1  one or more findings (missing/stale/broken/conflict/earlier-checkout)
#   2  usage error (bad flag, missing required argument)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=bin/lib/manifest.sh
# shellcheck disable=SC1091 # only resolvable with -x or a full-repo shellcheck pass (make check does the latter); pre-commit lints changed files only
source "$REPO_ROOT/bin/lib/manifest.sh"
CLAUDE_HOME="${HOME}/.claude"
CODEX_HOME=""
HAVE_CODEX=false
AGENTS_SKILLS_HOME=""
HAVE_AGENTS_SKILLS_HOME=false
BINDLE_BIN_DIR="${HOME}/.local/bin"
path_findings=0

while [ $# -gt 0 ]; do
  case "$1" in
    --home)
      CLAUDE_HOME="${2:-}"
      shift 2
      ;;
    --codex-home)
      CODEX_HOME="${2:-}"
      HAVE_CODEX=true
      shift 2
      ;;
    --agents-skills-home)
      AGENTS_SKILLS_HOME="${2:-}"
      HAVE_AGENTS_SKILLS_HOME=true
      shift 2
      ;;
    --bin-dir)
      BINDLE_BIN_DIR="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: bin/doctor.sh [--home DIR] [--codex-home DIR] [--agents-skills-home DIR] [--bin-dir DIR]" >&2
      exit 2
      ;;
  esac
done

current_count=0 missing_count=0 stale_count=0 broken_count=0 conflict_count=0 earlier_count=0
CODEX_ITEMS=0
AGENTS_SKILLS_ITEMS=0
expected_dests=""

# classify SRC DEST — sets STATE, DETAIL, ACTION for the (src, dest) pair.
# Read-only: only ever stats/readlinks SRC and DEST, never writes either.
# shellcheck disable=SC2329 # reachable only via check_item, itself invoked
# indirectly through the manifest callbacks below (see each_manifest_item)
classify() {
  local src="$1" dest="$2"
  STATE="" DETAIL="" ACTION=""
  if [ -L "$dest" ]; then
    local cur
    cur="$(readlink "$dest")"
    case "$cur" in
      "$REPO_ROOT"/*)
        if [ "$cur" = "$src" ]; then
          STATE="current"
        elif [ -e "$dest" ]; then
          STATE="stale"
          DETAIL="linked to $cur (not the current source $src)"
          ACTION="run: bin/install.sh (relinks owned items)"
        else
          STATE="broken"
          DETAIL="symlink target no longer exists ($cur)"
          ACTION="run: bin/install.sh --prune (or reinstall after restoring the item)"
        fi
        ;;
      *)
        local suffix old_prefix
        suffix="${src#"$REPO_ROOT"}"
        if [ -e "$dest" ]; then
          STATE="conflict"
          DETAIL="symlink to $cur (owned elsewhere)"
          ACTION='see docs/ownership-boundaries.md ("Recovery when conflicts happen")'
        else
          case "$cur" in
            *"$suffix")
              old_prefix="${cur%"$suffix"}"
              STATE="earlier-checkout"
              DETAIL="symlink to $cur (target missing) — possibly an earlier Bindle checkout at $old_prefix"
              ACTION='run: bin/install.sh --adopt (preview + confirm), or see docs/ownership-boundaries.md'
              ;;
            *)
              STATE="conflict"
              DETAIL="broken symlink to $cur (owned elsewhere)"
              ACTION='see docs/ownership-boundaries.md ("Recovery when conflicts happen")'
              ;;
          esac
        fi
        ;;
    esac
  elif [ -e "$dest" ]; then
    STATE="conflict"
    DETAIL="real file/dir at $dest (not a Bindle-owned symlink)"
    ACTION='see docs/ownership-boundaries.md ("Recovery when conflicts happen")'
  else
    STATE="missing"
    DETAIL="nothing installed at $dest"
    ACTION="run: bin/install.sh"
  fi
}

# check_item NAME SRC DEST — classify and print one line (plus an action line
# for findings), tally counters, and remember DEST so the directory sweep
# below doesn't double-report it.
# shellcheck disable=SC2329 # invoked indirectly via the manifest callbacks below
check_item() {
  local name="$1" src="$2" dest="$3"
  expected_dests="${expected_dests}
${dest}"
  classify "$src" "$dest"
  if [ "$STATE" = "current" ]; then
    printf '  \xe2\x9c\x93 %s — current\n' "$name"
    current_count=$((current_count + 1))
    return 0
  fi
  printf '  \xe2\x9c\x97 %s — %s: %s\n' "$name" "$STATE" "$DETAIL"
  printf '      \xe2\x86\x92 %s\n' "$ACTION"
  case "$STATE" in
    missing) missing_count=$((missing_count + 1)) ;;
    stale) stale_count=$((stale_count + 1)) ;;
    broken) broken_count=$((broken_count + 1)) ;;
    conflict) conflict_count=$((conflict_count + 1)) ;;
    earlier-checkout) earlier_count=$((earlier_count + 1)) ;;
  esac
}

# is_expected_dest DEST — true if DEST was already checked via check_item.
is_expected_dest() {
  case "${expected_dests}
" in
    *"
${1}
"*) return 0 ;;
    *) return 1 ;;
  esac
}

# sweep_dir DIR CATEGORY — report broken owned symlinks in DIR that are not
# among the expected items (i.e. the source item was deleted or renamed).
# Foreign entries (not pointing into this repo) are none of Bindle's
# business and are ignored.
sweep_dir() {
  local d="$1" category="$2" link cur name
  [ -d "$d" ] || return 0
  for link in "$d"/*; do
    [ -e "$link" ] || [ -L "$link" ] || continue
    [ -L "$link" ] || continue
    cur="$(readlink "$link")"
    case "$cur" in
      "$REPO_ROOT"/*) : ;;
      *) continue ;;
    esac
    [ -e "$link" ] && continue
    is_expected_dest "$link" && continue
    name="${category}/$(basename "$link")"
    printf '  \xe2\x9c\x97 %s — broken: symlink target no longer exists (%s)\n' "$name" "$cur"
    printf '      \xe2\x86\x92 run: bin/install.sh --prune (or reinstall after restoring the item)\n'
    broken_count=$((broken_count + 1))
  done
}

# _doctor_item PROVIDER CATEGORY NAME SRC DEST_REL — manifest callback that
# diagnoses one item for the given home. Label = the repo-relative source path,
# matching the labels doctor.sh printed before (skills/<n>, agents/<n>.md, ...).
# Skips rows whose source no longer exists in this checkout — same as the old
# filesystem-glob loops, which never enumerated a deleted item; that leaves any
# now-orphaned dest symlink for sweep_dir to report as broken instead.
# shellcheck disable=SC2329 # invoked indirectly, by name, via each_manifest_item
_doctor_claude_cb() {
  [ "$1" = claude ] || return 0
  [ -e "$4" ] || return 0
  check_item "${4#"$REPO_ROOT"/}" "$4" "$CLAUDE_HOME/$5"
}
# shellcheck disable=SC2329 # invoked indirectly, by name, via each_manifest_item
_doctor_codex_cb() {
  [ "$1" = codex ] || return 0
  [ "$2" = global-guidance ] || return 0
  [ -e "$4" ] || return 0
  CODEX_ITEMS=$((CODEX_ITEMS + 1))
  check_item "${4#"$REPO_ROOT"/}" "$4" "$CODEX_HOME/$5"
}
# shellcheck disable=SC2329 # invoked indirectly, by name, via each_manifest_item
_doctor_codex_skills_cb() {
  [ "$1" = codex ] || return 0
  [ "$2" = skill ] || return 0
  [ -e "$4" ] || return 0
  AGENTS_SKILLS_ITEMS=$((AGENTS_SKILLS_ITEMS + 1))
  check_item "${4#"$REPO_ROOT"/}" "$4" "$AGENTS_SKILLS_HOME/$5"
}
# shellcheck disable=SC2329 # invoked indirectly, by name, via each_manifest_item
_doctor_local_executable_cb() {
  [ "$1" = local ] || return 0
  [ "$2" = executable ] || return 0
  [ -e "$4" ] || return 0
  check_item "${4#"$REPO_ROOT"/}" "$4" "$BINDLE_BIN_DIR/$5"
}

claude_section() {
  echo
  echo "claude home ($CLAUDE_HOME):"
  each_manifest_item "$REPO_ROOT" _doctor_claude_cb
  sweep_dir "$CLAUDE_HOME/skills" "skills"
  sweep_dir "$CLAUDE_HOME/agents" "agents"
  sweep_dir "$CLAUDE_HOME/commands" "commands"
}

codex_section() {
  echo
  echo "codex home ($CODEX_HOME):"
  CODEX_ITEMS=0
  each_manifest_item "$REPO_ROOT" _doctor_codex_cb
  [ "$CODEX_ITEMS" -gt 0 ] || echo "  - no global/AGENTS.md in this repo"
}

codex_skills_section() {
  echo
  echo "codex agent-skills home ($AGENTS_SKILLS_HOME):"
  AGENTS_SKILLS_ITEMS=0
  each_manifest_item "$REPO_ROOT" _doctor_codex_skills_cb
  [ "$AGENTS_SKILLS_ITEMS" -gt 0 ] || echo "  - no Codex-eligible skills in this repo"
  sweep_dir "$AGENTS_SKILLS_HOME" "skills"
}

path_contains_dir() {
  case ":$PATH:" in
    *":$1:"*) return 0 ;;
    *) return 1 ;;
  esac
}

path_remediation() {
  local shell_name shell_rc export_cmd
  shell_name="$(basename "${SHELL:-sh}")"
  case "$shell_name" in
    zsh) shell_rc="$HOME/.zshrc" ;;
    bash) shell_rc="$HOME/.bashrc" ;;
    fish) shell_rc="$HOME/.config/fish/config.fish" ;;
    *) shell_rc="your shell startup file" ;;
  esac
  printf '  \xe2\x9c\x97 PATH — missing: %s is not on PATH\n' "$BINDLE_BIN_DIR"
  if [ "$shell_name" = fish ]; then
    printf '      \xe2\x86\x92 Add %s to PATH: fish_add_path %s\n' "$BINDLE_BIN_DIR" "$BINDLE_BIN_DIR"
  else
    export_cmd="export PATH=\"$BINDLE_BIN_DIR:\$PATH\""
    printf '      \xe2\x86\x92 Add %s to PATH: add '\''%s'\'' to %s\n' "$BINDLE_BIN_DIR" "$export_cmd" "$shell_rc"
  fi
  path_findings=1
}

executable_section() {
  echo
  echo "bindle executable ($BINDLE_BIN_DIR):"
  each_manifest_item "$REPO_ROOT" _doctor_local_executable_cb
  if ! path_contains_dir "$BINDLE_BIN_DIR"; then
    path_remediation
  fi
}

notes_section() {
  echo
  echo "notes home:"
  local notes_dir source_desc env_var_name is_default proj_count p

  if [ -n "${BINDLE_NOTES_DIR:-}" ]; then
    notes_dir="$BINDLE_NOTES_DIR"
    source_desc="BINDLE_NOTES_DIR"
    env_var_name="BINDLE_NOTES_DIR"
    is_default=false
  elif [ -n "${CLAUDE_KIT_NOTES_DIR:-}" ]; then
    notes_dir="$CLAUDE_KIT_NOTES_DIR"
    source_desc="CLAUDE_KIT_NOTES_DIR (deprecated)"
    env_var_name="CLAUDE_KIT_NOTES_DIR"
    is_default=false
  else
    notes_dir="${HOME}/.bindle"
    source_desc="default"
    env_var_name=""
    is_default=true
  fi

  echo "  - resolved: $notes_dir (via $source_desc)"
  if [ "$env_var_name" = "CLAUDE_KIT_NOTES_DIR" ]; then
    echo "  - CLAUDE_KIT_NOTES_DIR is deprecated; prefer BINDLE_NOTES_DIR"
  fi

  if [ -d "$notes_dir" ]; then
    proj_count=0
    if [ -d "$notes_dir/projects" ]; then
      for p in "$notes_dir/projects"/*/; do
        [ -d "$p" ] || continue
        proj_count=$((proj_count + 1))
      done
    fi
    echo "  - exists; ${proj_count} project(s) under projects/"
  elif $is_default; then
    echo "  - not created yet (created on first session note)"
  else
    printf '  \xe2\x9c\x97 notes-home — missing: %s does not exist\n' "$notes_dir"
    printf '      \xe2\x86\x92 create the directory, or unset %s if that override is unintended\n' "$env_var_name"
    missing_count=$((missing_count + 1))
  fi

  if [ -d "${HOME}/.claude-kit" ]; then
    echo "  - legacy ~/.claude-kit data present (not migrated automatically)"
  fi
}

tools_section() {
  echo
  echo "tools:"
  if command -v git >/dev/null 2>&1; then
    printf '  \xe2\x9c\x93 git — found\n'
  else
    printf '  \xe2\x9c\x97 git — missing: required for repo operations\n'
    printf '      \xe2\x86\x92 install git\n'
    missing_count=$((missing_count + 1))
  fi

  local tool
  for tool in shellcheck shfmt pre-commit; do
    if command -v "$tool" >/dev/null 2>&1; then
      printf '  \xe2\x9c\x93 %s — found\n' "$tool"
    else
      echo "  - $tool not found (needed for make check)"
    fi
  done
  if command -v python3 >/dev/null 2>&1; then
    printf '  \xe2\x9c\x93 python3 — found\n'
  else
    echo "  - python3 not found (needed for skill self-tests)"
  fi
  if command -v gh >/dev/null 2>&1; then
    printf '  \xe2\x9c\x93 gh — found\n'
  else
    echo "  - gh not found (needed for issue workflow)"
  fi
}

# --- header ------------------------------------------------------------
if [ -f "$REPO_ROOT/VERSION" ]; then
  echo "Bindle v$(cat "$REPO_ROOT/VERSION")"
else
  echo "Bindle (VERSION file missing)"
fi
echo "repo root: $REPO_ROOT"

claude_section
if $HAVE_CODEX; then
  codex_section
fi
if $HAVE_AGENTS_SKILLS_HOME; then
  codex_skills_section
fi
executable_section
notes_section
tools_section

# --- summary -------------------------------------------------------------
echo
printf 'summary: %d current, %d missing, %d stale, %d broken, %d conflict, %d earlier-checkout\n' \
  "$current_count" "$missing_count" "$stale_count" "$broken_count" "$conflict_count" "$earlier_count"

total_findings=$((missing_count + stale_count + broken_count + conflict_count + earlier_count + path_findings))
if [ "$total_findings" -eq 0 ]; then
  exit 0
else
  exit 1
fi
