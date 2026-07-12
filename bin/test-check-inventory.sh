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

echo "clean-type bijection:"
REPO="$TMP/missing-skill"
mkfixture "$REPO"
mkdir -p "$REPO/skills/extra"
printf -- '---\nname: extra\ndescription: Extra.\n---\n# extra\n' >"$REPO/skills/extra/SKILL.md"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m extra)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "on-disk skill absent from inventory fails" contains "skill 'extra' exists on disk but is missing from the inventory" "$out"

REPO="$TMP/phantom-skill"
mkfixture "$REPO"
sed -i.bak 's/"name": "demo", "type": "skill"/"name": "ghost", "type": "skill"/' "$REPO/capabilities.json"
rm -f "$REPO/capabilities.json.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "inventory skill absent from disk fails" contains "skill 'ghost' is in the inventory but not found on disk" "$out"

echo "fuzzy-type classified ledger:"
REPO="$TMP/unclassified-script"
mkfixture "$REPO"
mkdir -p "$REPO/bin"
printf '#!/usr/bin/env bash\necho hi\n' >"$REPO/bin/thing.sh"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m thing)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "unclassified bin script fails" contains "bin/thing.sh: unclassified" "$out"

REPO="$TMP/auto-excluded"
mkfixture "$REPO"
mkdir -p "$REPO/bin"
printf '#!/usr/bin/env bash\necho hi\n' >"$REPO/bin/test-thing.sh"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m testthing)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "bin/test-*.sh is auto-excluded (still passes)" test "$status" -eq 0

echo "path existence + cross-checks:"
REPO="$TMP/dead-path"
mkfixture "$REPO"
sed -i.bak 's#"path": "commands/foo.md"#"path": "commands/gone.md"#' "$REPO/capabilities.json"
rm -f "$REPO/capabilities.json.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "a dead path is reported" contains "path 'commands/gone.md' does not exist" "$out"

REPO="$TMP/desc-drift"
mkfixture "$REPO"
sed -i.bak 's/"description": "Demo skill."/"description": "Wrong."/' "$REPO/capabilities.json"
rm -f "$REPO/capabilities.json.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "description drift vs frontmatter is caught" contains "description does not match skill frontmatter" "$out"

REPO="$TMP/tested-no-pt"
mkfixture "$REPO"
rm -f "$REPO/skills/demo/PRESSURE-TESTS.md"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m rmpt)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "tested skill without PRESSURE-TESTS.md is caught" contains "maturity 'tested' but no PRESSURE-TESTS.md" "$out"

echo "bound-table drift (skill-portability-audit):"
REPO="$TMP/audit-drift"
mkfixture "$REPO"
# audit table lists demo; add a second skill to the inventory + disk but NOT the table
mkdir -p "$REPO/skills/second"
printf -- '---\nname: second\ndescription: Second.\n---\n# second\n' >"$REPO/skills/second/SKILL.md"
printf 'x\n' >"$REPO/skills/second/PRESSURE-TESTS.md"
# Author the inventory with `second` present (on disk + inventory) but NOT in
# the audit table, so only the bound-table drift check should fire.
cat >"$REPO/capabilities.json" <<'JSON'
{
  "capabilities": [
    {"name": "demo", "type": "skill", "path": "skills/demo", "description": "Demo skill.", "provider": {"claude": "installed", "codex": "untested"}, "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "second", "type": "skill", "path": "skills/second", "description": "Second.", "provider": {"claude": "installed", "codex": "untested"}, "maturity": "tested", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "foo", "type": "command", "path": "commands/foo.md", "description": "Demo command.", "provider": {"claude": "installed", "codex": "unsupported"}, "maturity": "documented", "mutation": ["disk"], "version_introduced": "0.1.0"},
    {"name": "claude", "type": "global-guidance", "path": "global/CLAUDE.md", "description": "Global Claude guidance.", "provider": {"claude": "installed", "codex": "n/a"}, "maturity": "documented", "mutation": [], "version_introduced": "0.1.0"},
    {"name": "agents", "type": "global-guidance", "path": "global/AGENTS.md", "description": "Global Codex guidance.", "provider": {"claude": "n/a", "codex": "manual"}, "maturity": "documented", "mutation": [], "version_introduced": "0.1.0"}
  ],
  "not_a_capability": [
    {"path": "docs/skill-portability-audit.md", "reason": "audit doc"}
  ]
}
JSON
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m second)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "inventory skill absent from audit table is caught" contains "skill 'second' in inventory but not in skill-portability-audit table" "$out"

REPO="$TMP/audit-template-row"
mkfixture "$REPO"
# shellcheck disable=SC2016 # single-quoted on purpose: backticks are literal markdown, not command substitution
printf -- '| `skills/_template/` | n/a |\n' >>"$REPO/docs/skill-portability-audit.md"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m template-row)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "template row in audit table is ignored (still passes)" test "$status" -eq 0

REPO="$TMP/audit-reverse-drift"
mkfixture "$REPO"
# shellcheck disable=SC2016 # single-quoted on purpose: backticks are literal markdown, not command substitution
printf -- '| `ghost` | ok |\n' >>"$REPO/docs/skill-portability-audit.md"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m ghost-row)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
check "audit-table skill absent from inventory fails" contains "skill 'ghost' in skill-portability-audit table but not in inventory" "$out"

echo "new.sh appends a valid stub row:"
REPO="$TMP/newsh"
mkfixture "$REPO"
mkdir -p "$REPO/bin"
cp "$REPO_ROOT/bin/new.sh" "$REPO/bin/new.sh"
python3 -c '
import json
p = "'"$REPO"'/capabilities.json"
d = json.load(open(p, encoding="utf-8"))
d["not_a_capability"].append({"path": "bin/new.sh", "reason": "scaffolding tool, not a shipped capability"})
json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
'
mkdir -p "$REPO/skills/_template"
printf -- '---\nname: Skill-Name\ndescription: Use when placeholder.\n---\n' >"$REPO/skills/_template/SKILL.md"
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m tmpl)
(cd "$REPO" && bin/new.sh skill widget >/dev/null)
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m widget)
# shellcheck disable=SC2016 # single-quoted on purpose: backticks are literal markdown, not command substitution
printf '| `widget` | ok |\n' >>"$REPO/docs/skill-portability-audit.md"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "repo still validates after new.sh skill" test "$status" -eq 0
check "stub row present for the new skill" contains '"name": "widget"' "$(cat "$REPO/capabilities.json")"

echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
