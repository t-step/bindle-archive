#!/usr/bin/env bash
#
# install.sh — install Bindle surfaces for supported providers.
#
# Claude Code remains the default for backward compatibility. Codex support is
# limited to an explicit AGENTS.md target directory; this script does not assume
# an undocumented Codex global install path.
#
# Claude:
#   skills/<name>/SKILL.md  ->  ~/.claude/skills/<name>
#   agents/<name>.md        ->  ~/.claude/agents/<name>.md
#   commands/<name>.md      ->  ~/.claude/commands/<name>.md
#   global/CLAUDE.md        ->  ~/.claude/CLAUDE.md
#
# Codex:
#   global/AGENTS.md        ->  <codex-home>/AGENTS.md
#
# Repo-root CLAUDE.md and AGENTS.md are this repo's OWN project memories and
# are NOT installed.
#
# GOOD CITIZEN GUARANTEE: this script only ever creates, updates, or removes
# symlinks that point INTO this repo. Anything else in an installed surface — a
# real file or a link owned by another source — is left completely untouched.
#
# Usage:
#   bin/install.sh                                      # Claude install
#   bin/install.sh --provider claude                    # Claude install
#   bin/install.sh --provider codex --codex-home DIR    # Codex AGENTS.md
#   bin/install.sh --provider all --codex-home DIR      # Claude + Codex
#   bin/install.sh --prune                              # prune broken owned links
#   bin/install.sh --home DIR                           # Claude home override
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_HOME="${HOME}/.claude"
CODEX_HOME=""
PROVIDER="claude"
PRUNE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --provider)
      PROVIDER="${2:-}"
      case "$PROVIDER" in
        claude | codex | all) ;;
        *)
          echo "Invalid provider: $PROVIDER (use: claude | codex | all)" >&2
          exit 2
          ;;
      esac
      shift 2
      ;;
    --prune)
      PRUNE=true
      shift
      ;;
    --home)
      CLAUDE_HOME="${2:-}"
      shift 2
      ;;
    --codex-home)
      CODEX_HOME="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

case "$PROVIDER" in
  codex | all)
    if [ -z "$CODEX_HOME" ]; then
      echo "Codex install requires an explicit target: --codex-home DIR" >&2
      echo "Example: bin/install.sh --provider codex --codex-home ~/.codex" >&2
      exit 2
    fi
    ;;
esac

case "$PROVIDER" in
  claude | all)
    mkdir -p "$CLAUDE_HOME"
    CLAUDE_HOME="$(cd "$CLAUDE_HOME" && pwd)"
    ;;
esac

case "$PROVIDER" in
  codex | all)
    mkdir -p "$CODEX_HOME"
    CODEX_HOME="$(cd "$CODEX_HOME" && pwd)"
    ;;
esac

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

# prune_path PATH — remove a broken symlink pointing into this repo.
prune_path() {
  local link="$1"
  [ -L "$link" ] || return 0
  if points_into_repo "$link" && [ ! -e "$link" ]; then
    echo "  pruned    $(basename "$link")"
    rm "$link"
    pruned=$((pruned + 1))
  fi
}

install_claude() {
  local dir f name

  # --- skills (each is a directory containing SKILL.md) ---
  echo "Claude skills:"
  mkdir -p "$CLAUDE_HOME/skills"
  for dir in "$REPO_ROOT"/skills/*/; do
    name="$(basename "$dir")"
    case "$name" in _* | .*) continue ;; esac
    [ -f "${dir}SKILL.md" ] || continue
    link_item "${REPO_ROOT}/skills/${name}" "${CLAUDE_HOME}/skills/${name}"
  done
  if $PRUNE; then
    prune_dir "$CLAUDE_HOME/skills"
  fi

  # --- subagents (single .md files) ---
  echo "Claude agents:"
  mkdir -p "$CLAUDE_HOME/agents"
  for f in "$REPO_ROOT"/agents/*.md; do
    [ -e "$f" ] || continue
    name="$(basename "$f")"
    case "$name" in _* | .*) continue ;; esac
    link_item "$f" "${CLAUDE_HOME}/agents/${name}"
  done
  if $PRUNE; then
    prune_dir "$CLAUDE_HOME/agents"
  fi

  # --- slash commands (single .md files) ---
  echo "Claude commands:"
  mkdir -p "$CLAUDE_HOME/commands"
  for f in "$REPO_ROOT"/commands/*.md; do
    [ -e "$f" ] || continue
    name="$(basename "$f")"
    case "$name" in _* | .*) continue ;; esac
    link_item "$f" "${CLAUDE_HOME}/commands/${name}"
  done
  if $PRUNE; then
    prune_dir "$CLAUDE_HOME/commands"
  fi

  # --- global CLAUDE.md (personal instructions for every project) ---
  # Source is global/CLAUDE.md; the repo-root CLAUDE.md is this repo's own
  # project memory and is deliberately never installed.
  if [ -f "$REPO_ROOT/global/CLAUDE.md" ]; then
    echo "Claude global instructions:"
    link_item "$REPO_ROOT/global/CLAUDE.md" "$CLAUDE_HOME/CLAUDE.md"
  fi
  if $PRUNE; then
    prune_path "$CLAUDE_HOME/CLAUDE.md"
  fi
}

install_codex() {
  # Codex support is intentionally limited to direct AGENTS.md instructions at
  # an explicit target directory supplied by the user.
  if [ -f "$REPO_ROOT/global/AGENTS.md" ]; then
    echo "Codex global instructions:"
    link_item "$REPO_ROOT/global/AGENTS.md" "$CODEX_HOME/AGENTS.md"
  fi
  if $PRUNE; then
    prune_path "$CODEX_HOME/AGENTS.md"
  fi
}

case "$PROVIDER" in
  claude)
    install_claude
    ;;
  codex)
    install_codex
    ;;
  all)
    install_claude
    install_codex
    ;;
esac

echo
echo "Done: ${linked} linked, ${current} already current, ${conflicts} conflicts, ${pruned} pruned."
if [ -f "$REPO_ROOT/VERSION" ]; then
  echo "Bindle v$(cat "$REPO_ROOT/VERSION") installed for provider(s): $PROVIDER"
else
  echo "Bindle installed for provider(s): $PROVIDER"
fi
case "$PROVIDER" in
  claude) echo "Claude home: $CLAUDE_HOME" ;;
  codex) echo "Codex home: $CODEX_HOME" ;;
  all)
    echo "Claude home: $CLAUDE_HOME"
    echo "Codex home: $CODEX_HOME"
    ;;
esac
[ "$conflicts" -eq 0 ] || echo "Conflicts left untouched — nothing owned by another source was modified."
