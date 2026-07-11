#!/usr/bin/env bash
#
# notes-home.sh — inspect and durably configure where Bindle's session
# workflows keep their notes (docs/notes-home.md).
#
# The durable mechanism is the `env` block of Claude Code's settings file
# (~/.claude/settings.json): a Bash `export` does not survive to the next
# session, the settings file does. That file is FOREIGN territory per
# docs/ownership-boundaries.md, so every write here is surgical (per
# docs/runtime-security-privacy.md rule 7): validate the JSON, back the file
# up first, touch only the one key (`env.BINDLE_NOTES_DIR`), show a diff —
# and never write at all unless explicitly told to.
#
# Usage:
#   bin/notes-home.sh [status]            # resolution chain + note counts
#   bin/notes-home.sh set <path> [--apply]    # persist BINDLE_NOTES_DIR
#   bin/notes-home.sh migrate <path> [--apply] # copy notes to a new home
#   bin/notes-home.sh reset [--apply]     # remove the persisted key
#   bin/notes-home.sh ... --home DIR      # Claude home override (tests)
#
# Without --apply, `set`, `migrate`, and `reset` only PREVIEW: they print
# exactly what would change and exit 0 with "no changes written". A TTY user
# is prompted instead; answering y is equivalent to --apply. `migrate`
# copies — it never deletes the old home, and it skips any project that
# already exists at the destination.
#
# Exit codes:
#   0  success (including previews and no-ops)
#   1  refused or failed (e.g. settings file is not valid JSON)
#   2  usage error (bad flag, missing argument)
#
set -euo pipefail

CLAUDE_HOME="${HOME}/.claude"
SUBCMD=""
TARGET=""
APPLY=false

usage_error() {
  echo "notes-home.sh: $1" >&2
  echo "usage: bin/notes-home.sh [status | set <path> [--apply] | migrate <path> [--apply] | reset [--apply]] [--home DIR]" >&2
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
    status | set | migrate | reset)
      [ -z "$SUBCMD" ] || usage_error "more than one subcommand given"
      SUBCMD="$1"
      shift
      ;;
    -*)
      usage_error "unknown option: $1"
      ;;
    *)
      [ -z "$TARGET" ] || usage_error "unexpected argument: $1"
      TARGET="$1"
      shift
      ;;
  esac
done

if [ -z "$SUBCMD" ] && [ -n "$TARGET" ]; then
  usage_error "unknown subcommand: $TARGET"
fi
if [ "$SUBCMD" = "status" ] || [ "$SUBCMD" = "reset" ]; then
  [ -z "$TARGET" ] || usage_error "$SUBCMD takes no path argument"
fi
[ -n "$SUBCMD" ] || SUBCMD="status"
SETTINGS="$CLAUDE_HOME/settings.json"

# --- shared helpers ---------------------------------------------------------

# resolve_notes_home: sets NOTES_DIR and NOTES_SOURCE per docs/notes-home.md.
resolve_notes_home() {
  if [ -n "${BINDLE_NOTES_DIR:-}" ]; then
    NOTES_DIR="$BINDLE_NOTES_DIR"
    NOTES_SOURCE="BINDLE_NOTES_DIR"
  elif [ -n "${CLAUDE_KIT_NOTES_DIR:-}" ]; then
    NOTES_DIR="$CLAUDE_KIT_NOTES_DIR"
    NOTES_SOURCE="CLAUDE_KIT_NOTES_DIR (deprecated; prefer BINDLE_NOTES_DIR)"
  else
    NOTES_DIR="${HOME}/.bindle"
    NOTES_SOURCE="default"
  fi
}

# abspath PATH — absolute form without requiring the path to exist.
abspath() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$PWD" "$1" ;;
  esac
}

# settings_valid_or_die — refuse to go near a settings file we can't parse.
settings_valid_or_die() {
  if [ -f "$SETTINGS" ] && ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$SETTINGS" 2>/dev/null; then
    echo "ERROR: $SETTINGS is not valid JSON — fix it by hand first; refusing to touch it." >&2
    exit 1
  fi
}

# render_settings MODE VALUE OUTFILE — write the would-be settings content.
# MODE=set stores VALUE under env.BINDLE_NOTES_DIR; MODE=reset removes the
# key. Everything else in the file is preserved byte-for-byte semantically.
render_settings() {
  python3 - "$1" "$2" "$SETTINGS" "$3" <<'PYEOF'
import json, os, sys

mode, value, settings, out = sys.argv[1:5]
data = {}
if os.path.exists(settings):
    with open(settings) as f:
        data = json.load(f)
if mode == "set":
    data.setdefault("env", {})["BINDLE_NOTES_DIR"] = value
else:
    data.get("env", {}).pop("BINDLE_NOTES_DIR", None)
with open(out, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PYEOF
}

# show_settings_diff NEWFILE — unified diff of the current file vs. NEWFILE.
show_settings_diff() {
  echo "planned change to $SETTINGS:"
  if [ -f "$SETTINGS" ]; then
    diff -u "$SETTINGS" "$1" || true
  else
    echo "  (file does not exist yet; it would be created as:)"
    sed 's/^/  /' "$1"
  fi
}

# confirm_or_preview — returns 0 to proceed with the write. In a TTY without
# --apply, asks. Otherwise --apply decides; without it, print the preview
# notice and exit 0 having written nothing.
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

# backup_settings — timestamped copy next to the file; prints the path.
backup_settings() {
  local stamp backup
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="$SETTINGS.bak-$stamp"
  cp "$SETTINGS" "$backup"
  echo "backup written: $backup"
}

# warn_if_in_git_repo PATH — the leak the session-continuity skill exists to
# prevent: notes inside a repo are one `git add -A` from publication.
warn_if_in_git_repo() {
  local probe="$1"
  while [ ! -d "$probe" ] && [ "$probe" != "/" ]; do
    probe="$(dirname "$probe")"
  done
  if git -C "$probe" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "WARNING: $1 is inside a git repo — session notes there are one 'git add -A' away from being committed/published. Pick a location outside every repo unless you have thought this through."
  fi
}

# --- subcommands ------------------------------------------------------------

cmd_status() {
  resolve_notes_home
  echo "notes home: $NOTES_DIR (via $NOTES_SOURCE)"

  if [ -f "$SETTINGS" ]; then
    local persisted
    persisted="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("env", {}).get("BINDLE_NOTES_DIR", ""))
except Exception:
    print("")' "$SETTINGS")"
    if [ -n "$persisted" ]; then
      echo "persisted: env.BINDLE_NOTES_DIR = $persisted (in $SETTINGS)"
      if [ "$persisted" != "$NOTES_DIR" ]; then
        echo "  note: this session resolved differently ($NOTES_DIR) — a session-level export or deprecated variable is overriding, or the setting is new and takes effect next session."
      fi
    else
      echo "persisted: (no env.BINDLE_NOTES_DIR in $SETTINGS — resolution relies on the environment/default)"
    fi
  else
    echo "persisted: ($SETTINGS does not exist)"
  fi

  if [ ! -d "$NOTES_DIR" ]; then
    echo "contents: (directory does not exist yet — it is created on first use)"
    return 0
  fi

  echo "projects:"
  local found=false p name count
  if [ -d "$NOTES_DIR/projects" ]; then
    for p in "$NOTES_DIR/projects"/*/; do
      [ -d "$p" ] || continue
      found=true
      name="$(basename "$p")"
      count="$(find "$p" -name '*.md' -type f | wc -l | tr -d ' ')"
      echo "  - $name ($count note file(s))"
    done
  fi
  [ "$found" = true ] || echo "  (none yet)"
}

cmd_set() {
  [ -n "$TARGET" ] || usage_error "set needs a path argument"
  local new_dir
  new_dir="$(abspath "$TARGET")"
  settings_valid_or_die

  resolve_notes_home
  echo "current notes home: $NOTES_DIR (via $NOTES_SOURCE)"
  echo "requested: BINDLE_NOTES_DIR = $new_dir"
  [ -d "$new_dir" ] || echo "note: $new_dir does not exist yet; it will be created."
  warn_if_in_git_repo "$new_dir"
  echo

  local tmp_json
  tmp_json="$(mktemp)"
  trap 'rm -f "$tmp_json"' EXIT
  render_settings set "$new_dir" "$tmp_json"
  show_settings_diff "$tmp_json"

  confirm_or_preview

  mkdir -p "$new_dir"
  [ -f "$SETTINGS" ] && backup_settings
  mkdir -p "$CLAUDE_HOME"
  mv "$tmp_json" "$SETTINGS"
  trap - EXIT
  echo "written: env.BINDLE_NOTES_DIR = $new_dir"
  echo
  echo "This takes effect next session (Claude Code reads env at session start)."
  echo "For non-Claude consumers, optionally add to your shell profile:"
  echo "  export BINDLE_NOTES_DIR=\"$new_dir\""
  echo "Existing notes are NOT moved; run 'bin/notes-home.sh migrate $new_dir' to copy them."
}

cmd_reset() {
  settings_valid_or_die
  local current=""
  if [ -f "$SETTINGS" ]; then
    current="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("env", {}).get("BINDLE_NOTES_DIR", ""))' "$SETTINGS")"
  fi
  if [ -z "$current" ]; then
    echo "env.BINDLE_NOTES_DIR is not set in $SETTINGS — nothing to reset."
    return 0
  fi

  echo "currently persisted: env.BINDLE_NOTES_DIR = $current"
  local tmp_json
  tmp_json="$(mktemp)"
  trap 'rm -f "$tmp_json"' EXIT
  render_settings reset "" "$tmp_json"
  show_settings_diff "$tmp_json"

  confirm_or_preview

  backup_settings
  mv "$tmp_json" "$SETTINGS"
  trap - EXIT
  echo "removed env.BINDLE_NOTES_DIR; resolution falls back to \$BINDLE_NOTES_DIR/\$CLAUDE_KIT_NOTES_DIR in the environment, then ~/.bindle."
  echo "This takes effect next session."
}

cmd_migrate() {
  [ -n "$TARGET" ] || usage_error "migrate needs a destination path argument"
  local dest
  dest="$(abspath "$TARGET")"
  resolve_notes_home

  if [ ! -d "$NOTES_DIR" ]; then
    echo "current notes home $NOTES_DIR does not exist — nothing to migrate."
    return 0
  fi
  if [ "$dest" = "$NOTES_DIR" ]; then
    echo "destination is the current notes home — nothing to migrate."
    return 0
  fi

  echo "migrate (copy) from: $NOTES_DIR"
  echo "                 to: $dest"
  echo
  echo "plan:"
  local p name any=false
  if [ -d "$NOTES_DIR/projects" ]; then
    for p in "$NOTES_DIR/projects"/*/; do
      [ -d "$p" ] || continue
      any=true
      name="$(basename "$p")"
      if [ -e "$dest/projects/$name" ]; then
        echo "  - skip project $name (already exists at destination)"
      else
        echo "  - copy project $name"
      fi
    done
  fi
  if [ -f "$NOTES_DIR/private-denylist.txt" ]; then
    any=true
    if [ -e "$dest/private-denylist.txt" ]; then
      echo "  - skip private-denylist.txt (already exists at destination)"
    else
      echo "  - copy private-denylist.txt"
    fi
  fi
  [ "$any" = true ] || {
    echo "  (nothing to copy)"
    return 0
  }

  confirm_or_preview

  mkdir -p "$dest/projects"
  if [ -d "$NOTES_DIR/projects" ]; then
    for p in "$NOTES_DIR/projects"/*/; do
      [ -d "$p" ] || continue
      name="$(basename "$p")"
      if [ -e "$dest/projects/$name" ]; then
        echo "skipped (already exists): $name"
      else
        cp -R "$p" "$dest/projects/$name"
        echo "copied: $name"
      fi
    done
  fi
  if [ -f "$NOTES_DIR/private-denylist.txt" ] && [ ! -e "$dest/private-denylist.txt" ]; then
    cp "$NOTES_DIR/private-denylist.txt" "$dest/private-denylist.txt"
    echo "copied: private-denylist.txt"
  fi
  echo
  echo "done. The old notes home is left untouched at $NOTES_DIR — delete it yourself once you're comfortable everything arrived (Bindle never deletes user data)."
  echo "If you haven't yet, persist the new location: bin/notes-home.sh set $dest"
}

case "$SUBCMD" in
  status) cmd_status ;;
  set) cmd_set ;;
  reset) cmd_reset ;;
  migrate) cmd_migrate ;;
esac
