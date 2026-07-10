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
#   bin/install.sh --allow-conflicts                    # don't fail on conflicts
#   bin/install.sh --adopt                              # adopt links from a moved repo
#
# --adopt: before the normal linking pass, scan for symlinks that are broken,
# point outside this repo, and whose target path ends with the same
# repo-relative suffix as an expected item — i.e. they look like they came
# from an earlier checkout of this same repo that has since moved or been
# deleted (the same heuristic doctor.sh uses for its "earlier-checkout"
# finding). If any are found, print a preview and ask for one-time
# confirmation before removing them; the normal linking pass then relinks
# them fresh from this checkout. Declining (or no candidates) changes
# nothing; declined candidates fall through to the normal linking pass and
# are reported as ordinary conflicts. Composes with --provider, --home,
# --codex-home, --prune, and --allow-conflicts.
#
# Exit codes:
#   0  every requested item was linked or already current (or a conflict
#      occurred and --allow-conflicts was passed)
#   1  one or more conflicts prevented installation of a requested item;
#      conflicting paths were left untouched (this also covers declined
#      --adopt candidates, which are reported as ordinary conflicts)
#   2  usage error (bad flag, missing required argument)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_HOME="${HOME}/.claude"
CODEX_HOME=""
PROVIDER="claude"
PRUNE=false
ALLOW_CONFLICTS=false
ADOPT=false

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
    --allow-conflicts)
      ALLOW_CONFLICTS=true
      shift
      ;;
    --adopt)
      ADOPT=true
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

linked=0 current=0 conflicts=0 pruned=0 adopted=0

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

# each_expected_item CALLBACK — invoke CALLBACK "$src" "$dest" for every
# expected (src, dest) pair install_claude/install_codex would link for the
# selected $PROVIDER, in the same enumeration order. Read-only enumeration:
# no output, no mkdir. Used by the --adopt pre-pass below.
#
# NOTE: this intentionally duplicates the item lists inside install_claude
# and install_codex rather than having them call through this helper. Those
# functions interleave per-category headers, mkdir -p, and --prune sweeps
# with their linking loops, and today's output must stay byte-identical when
# --adopt isn't passed; routing them through a shared enumerator risked
# subtly reordering or dropping that output. A small amount of duplicated
# enumeration in this read-only pre-pass is lower risk than restructuring
# the linking functions.
each_expected_item() {
  local cb="$1" dir f name
  case "$PROVIDER" in
    claude | all)
      for dir in "$REPO_ROOT"/skills/*/; do
        name="$(basename "$dir")"
        case "$name" in _* | .*) continue ;; esac
        [ -f "${dir}SKILL.md" ] || continue
        "$cb" "${REPO_ROOT}/skills/${name}" "${CLAUDE_HOME}/skills/${name}"
      done
      for f in "$REPO_ROOT"/agents/*.md; do
        [ -e "$f" ] || continue
        name="$(basename "$f")"
        case "$name" in _* | .*) continue ;; esac
        "$cb" "$f" "${CLAUDE_HOME}/agents/${name}"
      done
      for f in "$REPO_ROOT"/commands/*.md; do
        [ -e "$f" ] || continue
        name="$(basename "$f")"
        case "$name" in _* | .*) continue ;; esac
        "$cb" "$f" "${CLAUDE_HOME}/commands/${name}"
      done
      if [ -f "$REPO_ROOT/global/CLAUDE.md" ]; then
        "$cb" "$REPO_ROOT/global/CLAUDE.md" "$CLAUDE_HOME/CLAUDE.md"
      fi
      ;;
  esac
  case "$PROVIDER" in
    codex | all)
      if [ -f "$REPO_ROOT/global/AGENTS.md" ]; then
        "$cb" "$REPO_ROOT/global/AGENTS.md" "$CODEX_HOME/AGENTS.md"
      fi
      ;;
  esac
}

# ADOPT_CANDIDATES accumulates tab-separated "dest<TAB>cur<TAB>src" lines, one
# per adoption candidate found by _adopt_collect.
ADOPT_CANDIDATES=""

# _adopt_collect SRC DEST — each_expected_item callback for the --adopt
# pre-pass. A candidate is a symlink at DEST that is (1) broken, (2) pointing
# outside this repo, and (3) whose target path ends with this item's
# repo-relative suffix — the same rule doctor.sh uses for earlier-checkout.
_adopt_collect() {
  local src="$1" dest="$2" cur suffix
  [ -L "$dest" ] || return 0
  cur="$(readlink "$dest")"
  case "$cur" in "$REPO_ROOT"/*) return 0 ;; esac
  if [ -e "$dest" ]; then
    return 0
  fi
  suffix="${src#"$REPO_ROOT"}"
  case "$cur" in
    *"$suffix")
      ADOPT_CANDIDATES="${ADOPT_CANDIDATES}${dest}"$'\t'"${cur}"$'\t'"${src}"$'\n'
      ;;
  esac
}

# run_adopt_prepass — find adoption candidates, preview them, ask for
# one-time confirmation, and on yes rm them so the normal linking pass below
# relinks them fresh from this checkout. On no (or no candidates) this
# changes nothing.
run_adopt_prepass() {
  each_expected_item _adopt_collect
  [ -n "$ADOPT_CANDIDATES" ] || return 0

  echo "Adoption candidates (broken links from an earlier Bindle checkout):"
  local dest cur src suffix old_prefix count reply
  count=0
  while IFS=$'\t' read -r dest cur src; do
    [ -n "$dest" ] || continue
    suffix="${src#"$REPO_ROOT"}"
    old_prefix="${cur%"$suffix"}"
    echo "  $dest -> $cur"
    echo "      old checkout prefix: $old_prefix"
    count=$((count + 1))
  done <<<"$ADOPT_CANDIDATES"
  echo "Caution: verify each old checkout prefix above really was your previous Bindle checkout before confirming."

  printf 'relink these %d item(s) to %s? [y/N] ' "$count" "$REPO_ROOT"
  reply=""
  read -r reply || reply=""
  case "$reply" in
    y | Y | yes) ;;
    *)
      echo "Adoption declined; candidates above are left untouched."
      return 0
      ;;
  esac

  while IFS=$'\t' read -r dest cur src; do
    [ -n "$dest" ] || continue
    rm "$dest"
    adopted=$((adopted + 1))
  done <<<"$ADOPT_CANDIDATES"
  echo
}

if $ADOPT; then
  run_adopt_prepass
fi

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
if [ "$adopted" -gt 0 ]; then
  echo "adopted ${adopted} link(s) from an earlier checkout"
fi
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
if [ "$conflicts" -gt 0 ]; then
  echo "Conflicts left untouched — nothing owned by another source was modified."
  if ! $ALLOW_CONFLICTS; then
    echo "Exiting nonzero because conflicts prevented installation (use --allow-conflicts to suppress)." >&2
    exit 1
  fi
fi
