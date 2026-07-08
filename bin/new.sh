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
    ;;
  agent)
    dest="agents/$name.md"
    if [ -e "$dest" ]; then
      echo "Already exists: $dest" >&2
      exit 1
    fi
    sed "s/^name: .*/name: $name/" agents/_template.md >"$dest"
    ;;
  command)
    dest="commands/$name.md"
    if [ -e "$dest" ]; then
      echo "Already exists: $dest" >&2
      exit 1
    fi
    cp commands/_template.md "$dest"
    ;;
  *)
    echo "Unknown type '$kind' (use: skill | agent | command)" >&2
    exit 2
    ;;
esac

echo "Created $dest"
echo "Next: edit it, then run bin/install.sh --provider claude to link it into ~/.claude/"
