#!/usr/bin/env bash
#
# test-context-graph-skill.sh — graduation gate for the optional
# `context-graph` skill (issue #186). Thin wrapper around the Python driver
# skills/context-graph/tests/ontology_safety.py, which drives the real
# deterministic CLI (bin/context-graph.py) to prove the skill can never bypass,
# reinterpret, or silently repair endpoint legality: every producer path —
# human, skill, fixture — reduces through the same propose/confirm authority.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO_ROOT/skills/context-graph/tests/ontology_safety.py" "$REPO_ROOT"
