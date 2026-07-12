#!/usr/bin/env bash
#
# test-check-inventory.sh — exercise bin/check-inventory.py against throwaway
# fixture repos. The validator takes --root, so each test builds a tiny fake
# Bindle repo and points the validator at it. Nothing touches this repo.
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so the fixture-repo git
# calls below would hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

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
cp "$REPO_ROOT/bin/check-inventory.py" "$REPO/bin/check-inventory.py"
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
check "new.sh regenerated the manifest with the new skill" contains "$(printf 'claude\tskill\twidget\tskills/widget\tskills/widget')" "$(cat "$REPO/install-manifest.tsv")"

echo "malformed capability entries:"
REPO="$TMP/bad-entry"
mkfixture "$REPO"
python3 -c '
import json
p = "'"$REPO"'/capabilities.json"
d = json.load(open(p, encoding="utf-8"))
d["capabilities"].append("not-an-object")
json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
'
(cd "$REPO" && git add -A && git -c user.email=t@e.com -c user.name=t commit -q -m bad-entry)
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "non-dict capability entry exits nonzero" test "$status" -ne 0
check "non-dict capability entry gets a clean diagnostic" contains "not an object" "$out"
check "non-dict capability entry does not produce a traceback" not_contains "Traceback" "$out"

echo "manifest generation:"
REPO="$TMP/emit"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" --emit-manifest - 2>&1)"
check "banner is first line" contains "# GENERATED from capabilities.json" "$out"
check "skill row emitted" contains "$(printf 'claude\tskill\tdemo\tskills/demo\tskills/demo')" "$out"
check "command row emitted" contains "$(printf 'claude\tcommand\tfoo\tcommands/foo.md\tcommands/foo.md')" "$out"
check "claude global row: dest is basename" contains "$(printf 'claude\tglobal-guidance\tclaude\tglobal/CLAUDE.md\tCLAUDE.md')" "$out"
check "codex global row: provider is codex" contains "$(printf 'codex\tglobal-guidance\tagents\tglobal/AGENTS.md\tAGENTS.md')" "$out"
check "no script/contract rows" not_contains "docs/skill-portability-audit.md" "$out"
# deterministic ordering: claude skill < claude command < claude global < codex global
check "codex row is last" test "$(printf '%s\n' "$out" | tail -1)" = "$(printf 'codex\tglobal-guidance\tagents\tglobal/AGENTS.md\tAGENTS.md')"

REPO="$TMP/emit-override"
mkfixture "$REPO"
python3 -c '
import json
p = "'"$REPO"'/capabilities.json"
d = json.load(open(p, encoding="utf-8"))
for c in d["capabilities"]:
    if c["name"] == "demo":
        c["install_destination"] = "skills/renamed-demo"
json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
'
out="$(python3 "$VALIDATOR" --root "$REPO" --emit-manifest - 2>&1)"
check "explicit install_destination override is emitted verbatim" contains "$(printf 'claude\tskill\tdemo\tskills/demo\tskills/renamed-demo')" "$out"

echo "manifest drift guard:"
REPO="$TMP/manifest-ok"
mkfixture "$REPO"
python3 "$VALIDATOR" --root "$REPO" --emit-manifest >/dev/null
out="$(python3 "$VALIDATOR" --root "$REPO" --check-manifest 2>&1)"
status=$?
check "matching manifest passes --check-manifest" test "$status" -eq 0

REPO="$TMP/manifest-missing"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" --check-manifest 2>&1)"
status=$?
check "missing manifest fails" test "$status" -ne 0
check "missing manifest names the fix" contains "install-manifest.tsv: missing" "$out"

REPO="$TMP/manifest-stale"
mkfixture "$REPO"
python3 "$VALIDATOR" --root "$REPO" --emit-manifest >/dev/null
printf 'claude\tskill\tbogus\tskills/bogus\tskills/bogus\n' >>"$REPO/install-manifest.tsv"
out="$(python3 "$VALIDATOR" --root "$REPO" --check-manifest 2>&1)"
status=$?
check "stale manifest fails" test "$status" -ne 0
check "stale manifest names the fix" contains "install-manifest.tsv: stale" "$out"

REPO="$TMP/manifest-off"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "without --check-manifest, missing manifest is ignored" test "$status" -eq 0

# seed_doc_stubs DIR — minimal README.md/docs/provider-interop.md carrying
# empty GENERATED marker pairs for the three doc-table blocks (#78).
seed_doc_stubs() {
  local r="$1"
  cat >"$r/README.md" <<'EOF'
# Test
<!-- GENERATED:readme-claude:BEGIN -->
placeholder
<!-- GENERATED:readme-claude:END -->
<!-- GENERATED:readme-codex:BEGIN -->
placeholder
<!-- GENERATED:readme-codex:END -->
EOF
  mkdir -p "$r/docs"
  cat >"$r/docs/provider-interop.md" <<'EOF'
# Test
<!-- GENERATED:provider-interop-install-table:BEGIN -->
placeholder
<!-- GENERATED:provider-interop-install-table:END -->
EOF
}

echo "doc-table generation (README/provider-interop, #78):"
REPO="$TMP/docs-ok"
mkfixture "$REPO"
seed_doc_stubs "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" --emit-docs 2>&1)"
status=$?
check "emit-docs exits 0" test "$status" -eq 0
check "readme claude block populated" contains "Claude skills" "$(cat "$REPO/README.md")"
check "readme codex block populated" contains "AGENTS.md" "$(cat "$REPO/README.md")"
check "provider-interop table populated" contains "Claude install target" "$(cat "$REPO/docs/provider-interop.md")"
out="$(python3 "$VALIDATOR" --root "$REPO" --check-docs 2>&1)"
check "freshly emitted docs pass --check-docs" test "$?" -eq 0

echo "doc-table drift guard:"
REPO="$TMP/docs-stale"
mkfixture "$REPO"
seed_doc_stubs "$REPO"
python3 "$VALIDATOR" --root "$REPO" --emit-docs >/dev/null
sed -i.bak 's/Claude skills/Claude widgets/' "$REPO/README.md"
rm -f "$REPO/README.md.bak"
out="$(python3 "$VALIDATOR" --root "$REPO" --check-docs 2>&1)"
status=$?
check "stale doc block fails --check-docs" test "$status" -ne 0
check "stale doc block names the fix" contains "README.md: generated doc tables stale" "$out"

REPO="$TMP/docs-missing-markers"
mkfixture "$REPO"
printf '# Test\nno markers here\n' >"$REPO/README.md"
printf '# Test\nno markers here\n' >"$REPO/docs/provider-interop.md"
out="$(python3 "$VALIDATOR" --root "$REPO" --check-docs 2>&1)"
status=$?
check "missing markers fails --check-docs" test "$status" -ne 0
check "missing markers names the fix" contains "not found" "$out"

REPO="$TMP/docs-missing-file"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" --check-docs 2>&1)"
status=$?
check "missing README.md/provider-interop.md fails --check-docs" test "$status" -ne 0
check "missing README.md names the fix" contains "README.md: missing" "$out"
check "missing provider-interop.md names the fix" contains "docs/provider-interop.md: missing" "$out"

REPO="$TMP/docs-off"
mkfixture "$REPO"
out="$(python3 "$VALIDATOR" --root "$REPO" 2>&1)"
status=$?
check "without --check-docs, missing doc files are ignored" test "$status" -eq 0

echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
