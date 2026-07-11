#!/usr/bin/env bash
#
# test-check-inventory.sh — exercise bin/check-inventory.py against throwaway
# fixture repos. The validator takes --root, so each test builds a tiny fake
# Bindle repo and points the validator at it. Nothing touches this repo.
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="$REPO_ROOT/bin/check-inventory.py"

pass=0 fail=0
check() { # check "description" command...
  local desc="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  ✗ %s\n' "$desc"
    fail=$((fail + 1))
  fi
}
contains() { grep -qF -- "$1" <<<"$2"; }
not_contains() { ! grep -qF -- "$1" <<<"$2"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# mkfixture DIR — a minimal, fully VALID fixture repo the validator passes.
# Individual tests copy it and perturb one thing.
mkfixture() {
  local r="$1"
  mkdir -p "$r/skills/demo" "$r/commands" "$r/global" "$r/docs"
  printf '0.3.0\n' >"$r/VERSION"
  printf -- '---\nname: demo\ndescription: Demo skill.\n---\n# demo\n' >"$r/skills/demo/SKILL.md"
  printf 'tested\n' >"$r/skills/demo/PRESSURE-TESTS.md"
  printf -- '---\ndescription: Demo command.\n---\n# foo\n' >"$r/commands/foo.md"
  printf '# claude\n' >"$r/global/CLAUDE.md"
  printf '# agents\n' >"$r/global/AGENTS.md"
  # shellcheck disable=SC2016 # single-quoted on purpose: backticks are literal markdown, not command substitution
  printf '## Audit\n\n| Skill | X |\n|---|---|\n| `demo` | ok |\n' >"$r/docs/skill-portability-audit.md"
  cat >"$r/capabilities.json" <<'JSON'
{
  "capabilities": [
    {"name": "demo", "type": "skill", "path": "skills/demo",
     "description": "Demo skill.",
     "provider": {"claude": "installed", "codex": "untested"},
     "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "foo", "type": "command", "path": "commands/foo.md",
     "description": "Demo command.",
     "provider": {"claude": "installed", "codex": "unsupported"},
     "maturity": "documented", "mutation": ["disk"], "version_introduced": "0.1.0"},
    {"name": "claude", "type": "global-guidance", "path": "global/CLAUDE.md",
     "description": "Global Claude guidance.",
     "provider": {"claude": "installed", "codex": "n/a"},
     "maturity": "documented", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "agents", "type": "global-guidance", "path": "global/AGENTS.md",
     "description": "Global Codex guidance.",
     "provider": {"claude": "n/a", "codex": "manual"},
     "maturity": "documented", "mutation": [], "version_introduced": "0.1.0"}
  ],
  "not_a_capability": [
    {"path": "docs/skill-portability-audit.md", "reason": "audit doc, not a shipped capability"}
  ]
}
JSON
  (cd "$r" && git init -q && git symbolic-ref HEAD refs/heads/main &&
    git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m init)
}

echo "valid fixture passes:"
REPO="$TMP/ok"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "valid inventory exits 0" test "$status" -eq 0
check "reports the capability count" contains "capability inventory OK" "$out"

echo "schema violations are caught:"
REPO="$TMP/bad-enum"
mkfixture "$REPO"
# break the maturity enum on the demo skill
sed -i.bak 's/"maturity": "tested"/"maturity": "bogus"/' "$REPO/capabilities.json"
rm -f "$REPO/capabilities.json.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "invalid maturity exits nonzero" test "$status" -ne 0
check "names the bad maturity value" contains "invalid maturity 'bogus'" "$out"

REPO="$TMP/bad-json"
mkfixture "$REPO"
printf 'not json\n' >"$REPO/capabilities.json"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "invalid JSON is reported cleanly" contains "invalid JSON" "$out"

echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
