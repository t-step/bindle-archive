#!/usr/bin/env bash
#
# install-claude-hooks.sh — opt-in installer for the Claude Code hooks Bindle
# ships: the two SessionStart/SessionEnd session-continuity hooks (#21) and the
# three PreToolUse guards (#264, #287, #309). NOT part of `bin/install.sh` —
# wiring means writing into ~/.claude/settings.json, foreign territory per
# docs/ownership-boundaries.md, so this is its own explicit command.
#
# This is NOT bin/install-hooks.sh, which enables *git* hooks via pre-commit.
# Two different hook systems; this one owns ~/.claude/settings.json alone.
#
# Wiring is opt-in PER HOOK (#323). Installing Bindle symlinks every hook into
# ~/.claude/hooks/, but a guard that is merely present does nothing — and a
# guard that starts intercepting tool calls because someone ran a broad install
# is the failure mode this granularity exists to prevent. So:
#
#   install                      wires the two session hooks (and nothing else)
#   install --guard codegraph    wires exactly that guard
#
# A guard is never wired unless it is named. `bin/doctor.sh` reports which
# shipped hooks are installed-but-unwired, so opt-in does not mean invisible.
#
# Same discipline as bin/notes-home.sh: validate the JSON, back the file up
# first, touch only the entries this command owns, show a diff — and never
# write at all unless explicitly told to.
#
# Usage:
#   bin/install-claude-hooks.sh [status]           # report wiring for every hook
#   bin/install-claude-hooks.sh install   [SELECTORS] [--apply]
#   bin/install-claude-hooks.sh uninstall [SELECTORS] [--apply]
#   bin/install-claude-hooks.sh ... --home DIR      # Claude home override (tests)
#
# SELECTORS (default: --session):
#   --session                 the SessionStart + SessionEnd session hooks
#   --guard NAME              one PreToolUse guard; repeatable.
#                             NAME is nested-notes | label-hygiene | codegraph
#
# Without --apply, install/uninstall only PREVIEW: print exactly what would
# change and exit 0 with "no changes written". A TTY user is prompted
# instead; answering y is equivalent to --apply. Idempotent: re-running
# install when already installed, or uninstall when not installed, is a
# clean no-op.
#
# Exit codes:
#   0  success (including previews and no-ops)
#   1  refused or failed (e.g. settings file is not valid JSON)
#   2  usage error
#
set -euo pipefail

CLAUDE_HOME="${HOME}/.claude"
SUBCMD=""
APPLY=false
SELECTED=""

# hook_table — the ONE declared place a hook's event and matcher live (#323).
# Fields, ';'-separated: selector, script, event, matcher (empty = no matcher
# key). Retyping a matcher per install is what let #287's guard ship unwired
# and #309's get hand-wired, so nothing below duplicates these strings:
# bin/test-install-claude-hooks.sh asserts every matcher here matches the one
# in the hook's own docstring, so the table and the scripts cannot drift.
#
# Paths written into settings.json point at $CLAUDE_HOME/hooks/, the stable
# symlinks bin/install.sh creates — not into this checkout (#264). A repo move
# then leaves a dangling symlink that reports itself instead of silently
# disabling the hook.
hook_table() {
  cat <<'TABLE'
session;session-start-context.py;SessionStart;startup|resume
session;session-end-breadcrumb.py;SessionEnd;
nested-notes;nested-notes-guard.py;PreToolUse;Bash|mcp__.*github.*
label-hygiene;label-hygiene-guard.py;PreToolUse;Bash
codegraph;codegraph-chaining-guard.py;PreToolUse;Bash|mcp__.*codegraph.*
git-push-merged;git-push-merged-branch-guard.py;PreToolUse;Bash
TABLE
}

GUARD_SELECTORS="nested-notes label-hygiene codegraph git-push-merged"

usage_error() {
  echo "install-claude-hooks.sh: $1" >&2
  echo "usage: bin/install-claude-hooks.sh [status | install [SELECTORS] [--apply] | uninstall [SELECTORS] [--apply]] [--home DIR]" >&2
  echo "       SELECTORS: --session | --guard <nested-notes|label-hygiene|codegraph|git-push-merged> (repeatable); default --session" >&2
  exit 2
}

select_add() { # select_add SELECTOR — record a selector once
  case " $SELECTED " in
    *" $1 "*) ;;
    *) SELECTED="${SELECTED:+$SELECTED }$1" ;;
  esac
}

while [ $# -gt 0 ]; do
  case "$1" in
    --home)
      [ $# -ge 2 ] || usage_error "--home needs a directory argument"
      CLAUDE_HOME="$2"
      shift 2
      ;;
    --apply)
      APPLY=true
      shift
      ;;
    --session)
      select_add session
      shift
      ;;
    --guard)
      [ $# -ge 2 ] || usage_error "--guard needs a guard name ($GUARD_SELECTORS)"
      case " $GUARD_SELECTORS " in
        *" $2 "*) select_add "$2" ;;
        *) usage_error "unknown guard: $2 (expected one of: $GUARD_SELECTORS)" ;;
      esac
      shift 2
      ;;
    status | install | uninstall)
      [ -z "$SUBCMD" ] || usage_error "more than one subcommand given"
      SUBCMD="$1"
      shift
      ;;
    *)
      usage_error "unknown argument: $1"
      ;;
  esac
done
[ -n "$SUBCMD" ] || SUBCMD="status"
# Default selection is the two session hooks — today's behavior. A guard is
# wired only when named, so a bare `install` can never start blocking tool
# calls someone did not ask to have intercepted (#323).
[ -n "$SELECTED" ] || SELECTED="session"
SETTINGS="$CLAUDE_HOME/settings.json"
HOOKS_DIR="$CLAUDE_HOME/hooks"

# selected_rows — the 'script;event;matcher' rows matching the current selection.
selected_rows() {
  local selector script event matcher
  while IFS=';' read -r selector script event matcher; do
    [ -n "$selector" ] || continue
    case " $SELECTED " in
      *" $selector "*) printf '%s;%s;%s\n' "$script" "$event" "$matcher" ;;
    esac
  done <<EOF
$(hook_table)
EOF
}

settings_valid_or_die() {
  if [ -f "$SETTINGS" ] && ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$SETTINGS" 2>/dev/null; then
    echo "ERROR: $SETTINGS is not valid JSON — fix it by hand first; refusing to touch it." >&2
    exit 1
  fi
}

# hook_command SCRIPT — the exact settings.json command string for a hook.
# $HOME is spelled out: settings.json is JSON, so a leading ~ survives only if
# the shell running the command expands it — do not rely on that (#312).
hook_command() { printf 'python3 %s/%s\n' "$HOOKS_DIR" "$1"; }

# entry_wired SCRIPT — true when settings.json already names this hook.
entry_wired() {
  [ -f "$SETTINGS" ] && python3 -c 'import json,sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
cmd = sys.argv[2]
for entries in (data.get("hooks") or {}).values():
    for entry in entries or []:
        for h in entry.get("hooks") or []:
            if h.get("command") == cmd:
                sys.exit(0)
sys.exit(1)' "$SETTINGS" "$(hook_command "$1")"
}

# work_to_do MODE — does MODE have anything left to change for the selection?
# Drives the idempotent no-op: install is done when every selected hook is
# already wired, uninstall when none of them is.
work_to_do() {
  local script event matcher
  while IFS=';' read -r script event matcher; do
    [ -n "$script" ] || continue
    if [ "$1" = install ]; then
      entry_wired "$script" || return 0
    else
      entry_wired "$script" && return 0
    fi
  done <<EOF
$(selected_rows)
EOF
  return 1
}

# render MODE OUTFILE — write the would-be settings content. Only entries
# whose command matches a SELECTED hook are ever added or removed; every other
# key (including unrelated hooks in the same event) is preserved.
render() {
  local rows
  rows="$(selected_rows)"
  # shellcheck disable=SC2086 # each row is one ';'-joined word; splitting on whitespace is intended
  python3 - "$1" "$SETTINGS" "$2" "$HOOKS_DIR" $rows <<'PYEOF'
import json, os, sys

mode, settings, out, hooks_dir = sys.argv[1:5]
rows = [r.split(";") for r in sys.argv[5:]]

data = {}
if os.path.exists(settings):
    with open(settings) as f:
        data = json.load(f)

def has_command(entries, cmd):
    return any(h.get("command") == cmd
               for group in entries for h in group.get("hooks", []))

def remove_command(entries, cmd):
    kept = []
    for group in entries:
        hooks = [h for h in group.get("hooks", []) if h.get("command") != cmd]
        if hooks:
            new_group = dict(group)
            new_group["hooks"] = hooks
            kept.append(new_group)
    return kept

hooks = data.setdefault("hooks", {})

for script, event, matcher in rows:
    cmd = f"python3 {hooks_dir}/{script}"
    if mode == "install":
        entries = hooks.get(event, [])
        if not has_command(entries, cmd):
            group = {"hooks": [{"type": "command", "command": cmd, "timeout": 10}]}
            if matcher:
                group = {"matcher": matcher, **group}
            entries = entries + [group]
        hooks[event] = entries
    elif event in hooks:
        hooks[event] = remove_command(hooks[event], cmd)
        if not hooks[event]:
            del hooks[event]

if not hooks:
    data.pop("hooks", None)

with open(out, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PYEOF
}

show_diff() {
  echo "planned change to $SETTINGS:"
  if [ -f "$SETTINGS" ]; then
    diff -u "$SETTINGS" "$1" || true
  else
    echo "  (file does not exist yet; it would be created as:)"
    sed 's/^/  /' "$1"
  fi
}

confirm_or_preview() {
  if [ "$APPLY" = true ]; then
    return 0
  fi
  if [ -t 0 ]; then
    printf 'Proceed? [y/N] '
    local answer
    IFS= read -r answer
    case "$answer" in
      y | Y | yes) return 0 ;;
    esac
  fi
  echo
  echo "no changes written (preview). Re-run with --apply to make this change."
  exit 0
}

backup_settings() {
  local stamp backup
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="$SETTINGS.bak-$stamp"
  cp "$SETTINGS" "$backup"
  echo "backup written: $backup"
}

# cmd_status reports EVERY shipped hook, not only the selected ones — a guard
# that is installed but unwired is exactly the state that used to be invisible
# (#323), so status names it and prints the command that would wire it.
cmd_status() {
  local selector script event matcher state
  echo "claude hook wiring ($SETTINGS):"
  while IFS=';' read -r selector script event matcher; do
    [ -n "$selector" ] || continue
    if entry_wired "$script"; then
      state="wired"
    elif [ "$selector" = session ]; then
      state="not wired  → bin/install-claude-hooks.sh install"
    else
      state="not wired  → bin/install-claude-hooks.sh install --guard $selector"
    fi
    printf '  %-27s %-12s %s\n' "$script" "$event" "$state"
    [ -f "$HOOKS_DIR/$script" ] || printf '      WARNING: script missing at %s/%s — re-run bin/install.sh\n' "$HOOKS_DIR" "$script"
  done <<EOF
$(hook_table)
EOF
}

cmd_install() {
  settings_valid_or_die
  if ! work_to_do install; then
    echo "already wired: $SELECTED (in $SETTINGS) — nothing to do."
    return 0
  fi

  local tmp_json
  tmp_json="$(mktemp)"
  trap 'rm -f "$tmp_json"' EXIT
  render install "$tmp_json"
  show_diff "$tmp_json"

  confirm_or_preview

  [ -f "$SETTINGS" ] && backup_settings
  mkdir -p "$CLAUDE_HOME"
  mv "$tmp_json" "$SETTINGS"
  trap - EXIT
  echo "installed: $SELECTED. Session hooks take effect at the next session boundary; a PreToolUse guard applies once settings.json is re-read."
}

cmd_uninstall() {
  settings_valid_or_die
  if ! work_to_do uninstall; then
    echo "not wired: $SELECTED — nothing to do."
    return 0
  fi

  local tmp_json
  tmp_json="$(mktemp)"
  trap 'rm -f "$tmp_json"' EXIT
  render uninstall "$tmp_json"
  show_diff "$tmp_json"

  confirm_or_preview

  backup_settings
  mv "$tmp_json" "$SETTINGS"
  trap - EXIT
  echo "uninstalled: $SELECTED. Hooks this command was not asked to remove are untouched."
}

case "$SUBCMD" in
  status) cmd_status ;;
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
esac
