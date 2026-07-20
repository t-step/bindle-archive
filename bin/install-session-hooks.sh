#!/usr/bin/env bash
#
# install-session-hooks.sh — opt-in installer for the SessionStart/SessionEnd
# session-continuity hooks (issue #21). NOT part of `bin/install.sh` — hooks
# mean writing into ~/.claude/settings.json, foreign territory per
# docs/ownership-boundaries.md, so this is its own explicit command.
#
# Wires:
#   SessionStart (matcher startup|resume) -> global/hooks/session-start-context.py
#   SessionEnd                             -> global/hooks/session-end-breadcrumb.py
#
# Same discipline as bin/notes-home.sh: validate the JSON, back the file up
# first, touch only the two hook arrays this command owns, show a diff — and
# never write at all unless explicitly told to.
#
# Usage:
#   bin/install-session-hooks.sh [status]         # report current wiring
#   bin/install-session-hooks.sh install [--apply]
#   bin/install-session-hooks.sh uninstall [--apply]
#   bin/install-session-hooks.sh ... --home DIR    # Claude home override (tests)
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

# Hook paths written into settings.json point at $CLAUDE_HOME/hooks/, the stable
# symlinks bin/install.sh creates — not into this checkout (#264). A repo move
# then leaves a dangling symlink that reports itself instead of silently
# disabling the hook. Resolved after --home parsing, since CLAUDE_HOME is a flag.
set_hook_paths() {
  START_HOOK="$CLAUDE_HOME/hooks/session-start-context.py"
  END_HOOK="$CLAUDE_HOME/hooks/session-end-breadcrumb.py"
}

usage_error() {
  echo "install-session-hooks.sh: $1" >&2
  echo "usage: bin/install-session-hooks.sh [status | install [--apply] | uninstall [--apply]] [--home DIR]" >&2
  exit 2
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
SETTINGS="$CLAUDE_HOME/settings.json"
set_hook_paths

settings_valid_or_die() {
  if [ -f "$SETTINGS" ] && ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$SETTINGS" 2>/dev/null; then
    echo "ERROR: $SETTINGS is not valid JSON — fix it by hand first; refusing to touch it." >&2
    exit 1
  fi
}

# render MODE OUTFILE — write the would-be settings content. MODE is
# install or uninstall. Only hooks.SessionStart/hooks.SessionEnd entries
# whose command matches our two scripts are ever added or removed; every
# other key (including other SessionStart/SessionEnd entries and the
# unrelated PreToolUse guard) is preserved byte-for-byte semantically.
render() {
  python3 - "$1" "$SETTINGS" "$2" "$START_HOOK" "$END_HOOK" <<'PYEOF'
import json, os, sys

mode, settings, out, start_cmd, end_cmd = sys.argv[1:6]
start_cmd = f"python3 {start_cmd}"
end_cmd = f"python3 {end_cmd}"

data = {}
if os.path.exists(settings):
    with open(settings) as f:
        data = json.load(f)

def has_command(entries, cmd):
    for group in entries:
        for h in group.get("hooks", []):
            if h.get("command") == cmd:
                return True
    return False

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

if mode == "install":
    start_entries = hooks.get("SessionStart", [])
    if not has_command(start_entries, start_cmd):
        start_entries = start_entries + [{
            "matcher": "startup|resume",
            "hooks": [{"type": "command", "command": start_cmd, "timeout": 10}],
        }]
    hooks["SessionStart"] = start_entries

    end_entries = hooks.get("SessionEnd", [])
    if not has_command(end_entries, end_cmd):
        end_entries = end_entries + [{
            "hooks": [{"type": "command", "command": end_cmd, "timeout": 10}],
        }]
    hooks["SessionEnd"] = end_entries
else:
    if "SessionStart" in hooks:
        hooks["SessionStart"] = remove_command(hooks["SessionStart"], start_cmd)
        if not hooks["SessionStart"]:
            del hooks["SessionStart"]
    if "SessionEnd" in hooks:
        hooks["SessionEnd"] = remove_command(hooks["SessionEnd"], end_cmd)
        if not hooks["SessionEnd"]:
            del hooks["SessionEnd"]
    if not hooks:
        data.pop("hooks", None)

with open(out, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PYEOF
}

is_installed() {
  [ -f "$SETTINGS" ] && python3 -c 'import json,sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
cmd = "python3 " + sys.argv[2]
for group in data.get("hooks", {}).get("SessionStart", []):
    for h in group.get("hooks", []):
        if h.get("command") == cmd:
            sys.exit(0)
sys.exit(1)' "$SETTINGS" "$START_HOOK"
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

cmd_status() {
  if is_installed; then
    echo "session-continuity hooks: installed (in $SETTINGS)"
  else
    echo "session-continuity hooks: not installed"
  fi
  echo "SessionStart script: $START_HOOK"
  echo "SessionEnd script:   $END_HOOK"
  [ -f "$START_HOOK" ] || echo "  WARNING: SessionStart script is missing at that path"
  [ -f "$END_HOOK" ] || echo "  WARNING: SessionEnd script is missing at that path"
}

cmd_install() {
  settings_valid_or_die
  if is_installed; then
    echo "already installed (in $SETTINGS) — nothing to do."
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
  echo "installed. Takes effect next session (SessionStart/SessionEnd hooks are read at session boundaries)."
}

cmd_uninstall() {
  settings_valid_or_die
  if ! is_installed; then
    echo "not installed — nothing to do."
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
  echo "uninstalled. Other hooks (e.g. the nested-notes guard) are untouched."
}

case "$SUBCMD" in
  status) cmd_status ;;
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
esac
