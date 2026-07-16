#!/usr/bin/env bash
#
# new.sh — scaffold a new skill, agent, or command from its template, with the
# name pre-filled. Edit the result, then run bin/install.sh to link it.
#
# Usage:
#   bin/new.sh skill   <name>     # -> skills/<name>/SKILL.md
#   bin/new.sh agent   <name>     # -> agents/<name>.md
#   bin/new.sh command <name>     # -> commands/<name>.md
#
# <name> must be lowercase kebab-case (e.g. my-thing).
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# append_inventory_row TYPE NAME PATH SKILLFILE — add a valid stub row to
# capabilities.json (description copied verbatim from the scaffolded
# frontmatter). Uses python3 for safe JSON editing; no-op with a notice if
# python3 or capabilities.json is absent.
append_inventory_row() {
  local ctype="$1" cname="$2" cpath="$3" fmfile="$4"
  if [ ! -f capabilities.json ]; then
    echo "Note: capabilities.json not found; skipping inventory row." >&2
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Note: python3 absent; add the capabilities.json row by hand." >&2
    return 0
  fi
  local version
  VERSION_FILE="$REPO_ROOT/version.txt"
  version="$(cat "$VERSION_FILE")"
  CAP_TYPE="$ctype" CAP_NAME="$cname" CAP_PATH="$cpath" \
    CAP_FM="$fmfile" CAP_VERSION="$version" python3 - <<'PY'
import json, os, re
inv = "capabilities.json"
data = json.load(open(inv, encoding="utf-8"))
desc = ""
try:
    lines = open(os.environ["CAP_FM"], encoding="utf-8").read().splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            m = re.match(r"^description:\s*(.*)$", line)
            if m:
                desc = m.group(1).strip()
except OSError:
    pass
data.setdefault("capabilities", []).append({
    "name": os.environ["CAP_NAME"],
    "type": os.environ["CAP_TYPE"],
    "path": os.environ["CAP_PATH"],
    "description": desc,
    "provider": {"claude": "untested", "codex": "untested"},
    "maturity": "draft",
    "mutation": [],
    "version_introduced": os.environ["CAP_VERSION"],
})
with open(inv, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  echo "Added a draft capabilities.json row for $cname (fill in provider/maturity/mutation)."
  if [ -f capabilities.json ] && command -v python3 >/dev/null 2>&1 && [ -f bin/check-inventory.py ]; then
    python3 bin/check-inventory.py --emit-manifest >/dev/null 2>&1 &&
      echo "Regenerated install-manifest.tsv." ||
      echo "Note: could not regenerate install-manifest.tsv; run 'make manifest'." >&2
  fi
}

kind="${1:-}"
name="${2:-}"

if [ -z "$kind" ] || [ -z "$name" ]; then
  echo "Usage: bin/new.sh <skill|agent|command> <name>" >&2
  exit 2
fi
if ! [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "Name must be lowercase kebab-case (e.g. my-thing): '$name'" >&2
  exit 2
fi

case "$kind" in
  skill)
    dest="skills/$name/SKILL.md"
    if [ -e "$dest" ]; then
      echo "Already exists: $dest" >&2
      exit 1
    fi
    mkdir -p "skills/$name"
    sed "s/^name: .*/name: $name/" skills/_template/SKILL.md >"$dest"
    append_inventory_row skill "$name" "skills/$name" "$dest"
    ;;
  agent)
    dest="agents/$name.md"
    if [ -e "$dest" ]; then
      echo "Already exists: $dest" >&2
      exit 1
    fi
    sed "s/^name: .*/name: $name/" agents/_template.md >"$dest"
    append_inventory_row agent "$name" "agents/$name.md" "$dest"
    ;;
  command)
    dest="commands/$name.md"
    if [ -e "$dest" ]; then
      echo "Already exists: $dest" >&2
      exit 1
    fi
    cp commands/_template.md "$dest"
    append_inventory_row command "$name" "commands/$name.md" "$dest"
    ;;
  *)
    echo "Unknown type '$kind' (use: skill | agent | command)" >&2
    exit 2
    ;;
esac

echo "Created $dest"
echo "Next: edit it, then run bin/install.sh --provider claude to link it into ~/.claude/"
