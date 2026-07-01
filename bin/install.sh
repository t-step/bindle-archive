#!/usr/bin/env bash
#
# install.sh — install this toolkit into the user-level Claude Code config
# (~/.claude) so your skills, subagents, slash commands, and global CLAUDE.md
# are available in EVERY project, regardless of what that project provides.
#
# How: each item in this repo is symlinked into the matching ~/.claude/ dir.
# Edit a file here -> the change is live everywhere immediately.
#
#   skills/<name>/SKILL.md  ->  ~/.claude/skills/<name>
#   agents/<name>.md        ->  ~/.claude/agents/<name>.md
#   commands/<name>.md      ->  ~/.claude/commands/<name>.md
#   global/CLAUDE.md        ->  ~/.claude/CLAUDE.md   (global personal instructions)
#
# The repo-root CLAUDE.md is this repo's OWN project memory and is NOT installed.
#
# GOOD CITIZEN GUARANTEE: this script only ever creates, updates, or removes
# symlinks that point INTO this repo. Anything else in ~/.claude — a real file,
# or a link owned by another source (a plugin, or a project's DomI-style setup) —
# is left completely untouched. Safe to run alongside any project's own config.
#
# Usage:
#   bin/install.sh                 # install/update all links
#   bin/install.sh --prune         # also remove links for items deleted from this repo
#   bin/install.sh --home DIR      # install into DIR instead of ~/.claude (for testing)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${HOME}/.claude"
PRUNE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --prune)
      PRUNE=true
      shift
      ;;
    --home)
      HOME_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$HOME_DIR"
HOME_DIR="$(cd "$HOME_DIR" && pwd)"

linked=0 current=0 conflicts=0 pruned=0

# link_item SRC DEST — symlink SRC->DEST, but never clobber foreign files/links.
link_item() {
  local src="$1" dest="$2" name
  name="$(basename "$dest")"
  if [ -L "$dest" ]; then
    local cur
    cur="$(readlink "$dest")"
    case "$cur" in
      "$REPO_ROOT"/*)
        if [ "$cur" = "$src" ]; then
          current=$((current + 1))
        else
          rm "$dest"
          ln -s "$src" "$dest"
          echo "  relinked  $name"
          linked=$((linked + 1))
        fi
        ;;
      *)
        echo "  CONFLICT  $name -> $cur (owned elsewhere, left untouched)" >&2
        conflicts=$((conflicts + 1))
        ;;
    esac
  elif [ -e "$dest" ]; then
    echo "  CONFLICT  $name exists as a real file/dir (left untouched)" >&2
    conflicts=$((conflicts + 1))
  else
    ln -s "$src" "$dest"
    echo "  linked    $name"
    linked=$((linked + 1))
  fi
}

# points_into_repo PATH — true if PATH is a symlink resolving inside this repo.
points_into_repo() {
  [ -L "$1" ] || return 1
  case "$(readlink "$1")" in "$REPO_ROOT"/*) return 0 ;; *) return 1 ;; esac
}

# prune_dir DIR — remove broken symlinks in DIR that point into this repo.
prune_dir() {
  local d="$1"
  [ -d "$d" ] || return 0
  local link
  for link in "$d"/*; do
    [ -L "$link" ] || continue
    if points_into_repo "$link" && [ ! -e "$link" ]; then
      echo "  pruned    $(basename "$link")"
      rm "$link"
      pruned=$((pruned + 1))
    fi
  done
}

# --- skills (each is a directory containing SKILL.md) ---
echo "skills:"
mkdir -p "$HOME_DIR/skills"
for dir in "$REPO_ROOT"/skills/*/; do
  name="$(basename "$dir")"
  case "$name" in _* | .*) continue ;; esac
  [ -f "${dir}SKILL.md" ] || continue
  link_item "${REPO_ROOT}/skills/${name}" "${HOME_DIR}/skills/${name}"
done
$PRUNE && prune_dir "$HOME_DIR/skills"

# --- subagents (single .md files) ---
echo "agents:"
mkdir -p "$HOME_DIR/agents"
for f in "$REPO_ROOT"/agents/*.md; do
  [ -e "$f" ] || continue
  name="$(basename "$f")"
  case "$name" in _* | .*) continue ;; esac
  link_item "$f" "${HOME_DIR}/agents/${name}"
done
$PRUNE && prune_dir "$HOME_DIR/agents"

# --- slash commands (single .md files) ---
echo "commands:"
mkdir -p "$HOME_DIR/commands"
for f in "$REPO_ROOT"/commands/*.md; do
  [ -e "$f" ] || continue
  name="$(basename "$f")"
  case "$name" in _* | .*) continue ;; esac
  link_item "$f" "${HOME_DIR}/commands/${name}"
done
$PRUNE && prune_dir "$HOME_DIR/commands"

# --- global CLAUDE.md (personal instructions for every project) ---
# Source is global/CLAUDE.md; the repo-root CLAUDE.md is this repo's own project
# memory and is deliberately never installed (so it can't leak into other projects).
if [ -f "$REPO_ROOT/global/CLAUDE.md" ]; then
  echo "global instructions:"
  link_item "$REPO_ROOT/global/CLAUDE.md" "$HOME_DIR/CLAUDE.md"
fi

echo
echo "Done: ${linked} linked, ${current} already current, ${conflicts} conflicts, ${pruned} pruned."
if [ -f "$REPO_ROOT/VERSION" ]; then
  echo "claude-kit v$(cat "$REPO_ROOT/VERSION") installed into: $HOME_DIR"
else
  echo "Installed into: $HOME_DIR"
fi
[ "$conflicts" -eq 0 ] || echo "Conflicts left untouched — nothing owned by another source was modified."
