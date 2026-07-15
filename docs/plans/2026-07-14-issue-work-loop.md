# Portable Issue Work Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship slice 1 of #60 — a portable issue work loop as a contract + Claude skill + deterministic dedup adapter — so Claude and Codex follow one neutral discover→dedup→execute→verify→report loop without depending on DomI-fleet skills.

**Architecture:** Three artifacts mirroring the repo's `domi-consumer` trio: `docs/workflows/issue-work-loop.md` (normative portable contract), `skills/issue-work-loop/SKILL.md` (Claude-native orchestrator that delegates each phase to existing Bindle-native skills, ships **draft**), and `bin/issue-dedup-scan.sh` (portable bash dedup adapter with tests). The helper is honest by construction: it proves `no-evidence`/`evidence-found`/`uncertain` via exit code; the model classifies `already-done` vs `partially-done` from the emitted evidence JSON.

**Tech Stack:** Bash (`set -uo pipefail`, `git` + `gh`), Markdown, `capabilities.json` (python3-edited), pre-commit local hooks.

## Global Constraints

- Branch `feature/issue-work-loop-60` (already created); one PR to `main`; never commit to `main`, never `--no-verify`, never push unless the operator asks.
- `make check` must be green before every commit; all pre-commit hooks must pass.
- Bash scripts: `#!/usr/bin/env bash`, `set -uo pipefail`, a header comment block with `Usage:` and `Exit codes:`, a `-h|--help` path that prints the header. Read-only toward any target repo. **No Claude-only primitive** — pure `git`/`gh` so the helper is portable to Codex.
- The dedup helper's core guarantee: a sub-query *failure* (tool error / no network) yields exit 4 (`uncertain`) and is structurally distinct from a *successful-but-empty* scan (exit 0, `not-started`). Failure must NEVER read as "no prior work".
- Cross-doc references inside `docs/**` bodies use inline-code (`` `x.md` ``), never markdown links resolved relative to the file's own dir (link-checker gotcha).
- Adding a skill touches THREE places or `make check` fails: the skill dir, a `capabilities.json` row, and a `docs/skill-portability-audit.md` row. A new `bin/*.sh` or a `docs/**/*.md` outside `docs/design/`/`docs/plans/` also needs a `capabilities.json` row (or `not_a_capability` entry).
- Skill is **draft** (unverified) — mark it draft in `CHANGELOG.md`; pressure-tests are a follow-up session, not this slice.

---

### Task 1: Dedup adapter `bin/issue-dedup-scan.sh` + tests

The deterministic core and the one net-new capability. Emits evidence JSON on stdout; verdict via exit code. `gh` is invoked through a `${GH:-gh}` indirection so tests inject a fake `gh` (no network). `git` runs against the current repo / a fixture repo.

**Files:**
- Create: `bin/issue-dedup-scan.sh`
- Create: `bin/test-issue-dedup-scan.sh`
- Modify: `.pre-commit-config.yaml` (register the test as an always-run local hook)
- Modify: `capabilities.json` (add the `script` row)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `bin/issue-dedup-scan.sh <issue-number>` — scans the current git repo + GitHub for prior work referencing `#<n>`. Stdout: JSON `{"issue": N, "verdict": "no-evidence"|"evidence-found"|"uncertain", "evidence": [{"source","ref","detail"}], "queries": [{"name","status": "ok"|"failed"}]}`. Exit: `0` no-evidence, `3` evidence-found, `4` uncertain, `64` usage error. Sub-queries: `git log --all --grep="#N"`; grep of `docs/design`/`docs/plans`/`specs` for `#N`; `gh pr list --state open`; `gh pr list --state merged`; `gh issue view N` comments. Any sub-query exiting non-zero ⇒ verdict `uncertain`, exit 4.

- [ ] **Step 1: Write the failing test**

Create `bin/test-issue-dedup-scan.sh`. It builds a throwaway git fixture, injects a fake `gh`, and asserts exit code + `verdict` for the three deterministic paths plus the fail-closed path.

```bash
#!/usr/bin/env bash
#
# test-issue-dedup-scan.sh — exercise bin/issue-dedup-scan.sh against a
# throwaway git fixture with an injected fake `gh` (never touches the network
# or a real repo). Proves the honest-by-construction guarantee: a failed
# sub-query yields `uncertain` (exit 4), distinct from an empty scan (exit 0).
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCAN="$REPO_ROOT/bin/issue-dedup-scan.sh"

pass=0 fail=0
ok() {
  printf '  ✓ %s\n' "$1"
  pass=$((pass + 1))
}
bad() {
  printf '  ✗ %s\n' "$1"
  fail=$((fail + 1))
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# fixture git repo with one unrelated commit
FIX="$TMP/repo"
mkdir -p "$FIX"
git -C "$FIX" init -q
git -C "$FIX" config user.email t@e.st
git -C "$FIX" config user.name t
: >"$FIX/f"
git -C "$FIX" add f
git -C "$FIX" commit -qm "chore: seed unrelated commit"

# make_gh <mode> — write a fake gh into $TMP/bin that behaves per mode.
#   empty  : all subcommands succeed, emit []
#   haspr  : `pr list` emits one matching PR; others []
#   fail   : any invocation exits 1 (simulates network/tool failure)
make_gh() {
  local mode="$1"
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/gh" <<EOF
#!/usr/bin/env bash
mode="$mode"
if [ "\$mode" = fail ]; then exit 1; fi
case "\$1 \$2" in
  "pr list")
    if [ "\$mode" = haspr ]; then
      echo '[{"number":42,"title":"prior work #123","state":"MERGED","url":"u"}]'
    else echo '[]'; fi ;;
  "issue view") echo '{"comments":[]}' ;;
  *) echo '[]' ;;
esac
EOF
  chmod +x "$TMP/bin/gh"
}

run() { # run <issue#> <ghmode> ; sets $code and $out
  make_gh "$2"
  out="$(cd "$FIX" && GH="$TMP/bin/gh" "$SCAN" "$1" 2>/dev/null)"
  code=$?
}

# 1. clean repo, all queries succeed empty -> no-evidence / exit 0
run 123 empty
if [ "$code" -eq 0 ] && printf '%s' "$out" | grep -q '"verdict": "no-evidence"'; then
  ok "empty scan -> no-evidence (exit 0)"
else bad "empty scan: code=$code out=$out"; fi

# 2. a merged PR references the issue -> evidence-found / exit 3
run 123 haspr
if [ "$code" -eq 3 ] && printf '%s' "$out" | grep -q '"verdict": "evidence-found"'; then
  ok "matching PR -> evidence-found (exit 3)"
else bad "haspr: code=$code out=$out"; fi

# 3. a git commit references the issue -> evidence-found / exit 3
git -C "$FIX" commit -q --allow-empty -m "fix(#777): prior commit"
run 777 empty
if [ "$code" -eq 3 ]; then ok "matching commit -> evidence-found (exit 3)"
else bad "commit-evidence: code=$code out=$out"; fi

# 4. a sub-query FAILS -> uncertain / exit 4 (never no-evidence)
run 999 fail
if [ "$code" -eq 4 ] && printf '%s' "$out" | grep -q '"verdict": "uncertain"'; then
  ok "gh failure -> uncertain (exit 4), NOT no-evidence"
else bad "fail-closed: code=$code out=$out"; fi

# 5. usage error -> exit 64
(cd "$FIX" && "$SCAN" >/dev/null 2>&1); [ $? -eq 64 ] \
  && ok "no arg -> usage error (exit 64)" || bad "usage error not 64"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash bin/test-issue-dedup-scan.sh`
Expected: FAIL — `bin/issue-dedup-scan.sh` does not exist yet (all cases error / non-zero).

- [ ] **Step 3: Implement `bin/issue-dedup-scan.sh`**

```bash
#!/usr/bin/env bash
#
# issue-dedup-scan.sh — read-only prior-work scan for a repository issue.
# Deterministically gathers evidence that issue #<n> may already be worked or
# done (git history, in-repo specs/plans, open + merged PRs, issue comments)
# and emits it as JSON, with the verdict in the EXIT CODE. Honest by
# construction: a failed sub-query yields `uncertain` (exit 4), never a clean
# verdict — an empty-but-successful scan is exit 0. Classification of an
# evidence-found result into in-progress / already-done / partially-done is
# left to the caller reading the emitted evidence (bash cannot judge it).
#
# Usage: bin/issue-dedup-scan.sh <issue-number>
#   GH env var overrides the `gh` binary (for testing).
#
# Exit codes:
#   0  no-evidence    all sub-queries ran, found nothing referencing #<n>
#   3  evidence-found at least one sub-query surfaced a reference
#   4  uncertain      at least one sub-query FAILED (tool/network error)
#   64 usage error
#
set -uo pipefail

GH="${GH:-gh}"
N=""
case "${1:-}" in
  -h | --help)
    tail -n +2 "$0" | grep '^#' | sed 's/^#\{1,\} \{0,1\}//'
    exit 0
    ;;
  '')
    echo "issue-dedup-scan.sh: missing <issue-number>" >&2
    exit 64
    ;;
  *[!0-9]* | '')
    echo "issue-dedup-scan.sh: <issue-number> must be numeric, got '$1'" >&2
    exit 64
    ;;
  *) N="$1" ;;
esac

failed=0        # 1 if any sub-query errored
evidence_json="" # accumulated JSON objects
queries_json=""  # per-query status objects

# record_query NAME STATUS
record_query() {
  local obj
  obj=$(printf '{"name": "%s", "status": "%s"}' "$1" "$2")
  queries_json="${queries_json:+$queries_json, }$obj"
  [ "$2" = failed ] && failed=1
}

# add_evidence SOURCE REF DETAIL
add_evidence() {
  local obj
  obj=$(printf '{"source": "%s", "ref": "%s", "detail": "%s"}' \
    "$1" "$2" "$3")
  evidence_json="${evidence_json:+$evidence_json, }$obj"
}

# 1. git log referencing #N
if out=$(git log --all --oneline --grep="#$N" 2>/dev/null); then
  if [ -n "$out" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] && add_evidence "git-log" "${line%% *}" \
        "$(printf '%s' "${line#* }" | tr '"' "'" | cut -c1-80)"
    done <<<"$out"
  fi
  record_query git-log ok
else
  record_query git-log failed
fi

# 2. in-repo specs/plans/ADRs referencing #N (only dirs that exist)
spec_dirs=()
for d in docs/design docs/plans specs; do [ -d "$d" ] && spec_dirs+=("$d"); done
if [ "${#spec_dirs[@]}" -eq 0 ]; then
  record_query specs ok
elif out=$(grep -rIl -- "#$N" "${spec_dirs[@]}" 2>/dev/null); then
  while IFS= read -r f; do
    [ -n "$f" ] && add_evidence "spec" "$f" "references #$N"
  done <<<"$out"
  record_query specs ok
else
  # grep exit 1 == no match (success-empty); >1 == real error
  rc=$?
  if [ "$rc" -eq 1 ]; then record_query specs ok
  else record_query specs failed; fi
fi

# 3 + 4. open and merged PRs referencing the issue
scan_prs() { # scan_prs <state>
  local state="$1" json
  if json=$("$GH" pr list --state "$state" --search "$N" \
    --json number,title,state,url 2>/dev/null); then
    # count matches by presence of a number field
    if printf '%s' "$json" | grep -q '"number"'; then
      add_evidence "pr-$state" "$json" "PR(s) referencing #$N"
    fi
    record_query "pr-$state" ok
  else
    record_query "pr-$state" failed
  fi
}
scan_prs open
scan_prs merged

# 5. the issue's own comments
if json=$("$GH" issue view "$N" --json comments 2>/dev/null); then
  if printf '%s' "$json" | grep -q '"body"'; then
    add_evidence "issue-comments" "#$N" "issue has comments to review"
  fi
  record_query issue-comments ok
else
  record_query issue-comments failed
fi

# verdict
if [ "$failed" -eq 1 ]; then
  verdict="uncertain"; code=4
elif [ -n "$evidence_json" ]; then
  verdict="evidence-found"; code=3
else
  verdict="no-evidence"; code=0
fi

printf '{"issue": %s, "verdict": "%s", "evidence": [%s], "queries": [%s]}\n' \
  "$N" "$verdict" "$evidence_json" "$queries_json"
exit "$code"
```

- [ ] **Step 4: Make both scripts executable and run the test to verify it passes**

Run:
```bash
chmod +x bin/issue-dedup-scan.sh bin/test-issue-dedup-scan.sh
bash bin/test-issue-dedup-scan.sh
```
Expected: PASS — `5 passed, 0 failed`.

- [ ] **Step 5: Register the test as a pre-commit local hook**

In `.pre-commit-config.yaml`, alongside the other `bindle-test-*` local hooks (after `bindle-test-package-release-integrity`), add:

```yaml
      - id: bindle-test-issue-dedup-scan
        name: issue-dedup-scan.sh helper tests
        entry: bin/test-issue-dedup-scan.sh
        language: script
        pass_filenames: false
        always_run: true
```

- [ ] **Step 6: Add the `script` capability row to `capabilities.json`**

Insert into the `capabilities` array (keep JSON valid; description one line):

```json
{
  "name": "issue-dedup-scan",
  "type": "script",
  "path": "bin/issue-dedup-scan.sh",
  "description": "Read-only prior-work dedup scan for a repository issue: deterministically gathers evidence (git history, in-repo specs/plans, open + merged PRs, issue comments) that #<n> may already be worked/done, emitting evidence JSON with the verdict in the exit code (0 no-evidence, 3 evidence-found, 4 uncertain); a failed sub-query yields uncertain, never a clean verdict. Phase-3 adapter for the issue-work-loop contract.",
  "provider": { "claude": "installed", "codex": "untested" },
  "maturity": "tested",
  "mutation": [],
  "version_introduced": "0.4.0"
}
```

- [ ] **Step 7: Run `make check` and commit**

Run: `make check`
Expected: all checks pass (shellcheck/shfmt clean, inventory OK with the new row).

If `shfmt` reports formatting, run `shfmt -w bin/issue-dedup-scan.sh bin/test-issue-dedup-scan.sh` and re-run `make check`.

```bash
git add bin/issue-dedup-scan.sh bin/test-issue-dedup-scan.sh .pre-commit-config.yaml capabilities.json
git commit -m "feat(#60): deterministic issue-dedup-scan adapter with tests"
```

---

### Task 2: The portable contract `docs/workflows/issue-work-loop.md`

The normative provider-neutral loop. References Task 1's helper for Phase 3.

**Files:**
- Create: `docs/workflows/issue-work-loop.md`
- Modify: `capabilities.json` (add the `contract` row)

**Interfaces:**
- Consumes: `bin/issue-dedup-scan.sh` (named in Phase 3).
- Produces: the contract other agents/skills cite by path `docs/workflows/issue-work-loop.md`.

- [ ] **Step 1: Write the contract**

Create `docs/workflows/issue-work-loop.md` with these sections (cross-doc refs as inline-code, not links):

1. **Purpose & scope** — provider-neutral loop for taking an issue discovery→honest-end-state; portability goal (Claude + Codex, no DomI-fleet dependence); the slice-1 non-goals (no scheduler/queue/wave/auto-merge/auto-close).
2. **The two authorities (invariant)** — repo mutation (edit/commit/branch) vs external mutation (`gh` comment/label/close, push, open PR) are separate grants; general permission to implement does NOT imply close/merge/publish/deploy; never trust another agent's `done` without checking the checkout + real remote; network/tool failure produces `uncertain` or a degraded report, never a false `already-done`.
3. **Phase 1 Orient** — read authoritative instructions + precedence (`CLAUDE.md`); inspect branch/remotes/status; identify verification commands + mutation boundaries; detect `.domi-pin` (Claude: `domi-consumer` skill / `bin/domi-status.sh`).
4. **Phase 2 Discover & qualify** — read the issue + comments (`gh issue view`); confirm open/actionable/unblocked; classify the task and delegation profile (`docs/delegation-profiles.md`); name the expected deliverable (analysis / patch / branch / PR / issue update / handoff).
5. **Phase 3 Deduplicate before claiming** — run the bounded evidence scan `bin/issue-dedup-scan.sh <n>`; MAP its result: exit 0 → `not-started`; exit 4 → `uncertain` (STOP or degrade, never claim no-work); exit 3 → read the emitted evidence and classify into `in-progress-elsewhere` / `already-done` / `partially-done`. No issue is claimed solely because its GitHub state is open. A failed/empty query is never proof of no prior work.
6. **Phase 4 Bound & execute** — state exact scope + explicit non-goals; select minimal applicable workflows (`docs/workflow-composition.md`); delegate only within granted authority (`docs/delegation-profiles.md`, `docs/delegated-implementation-packets.md`); keep repo mutation separate from external mutation; preserve no-push/no-publish defaults unless explicitly overridden (`scoped-sequential-prs`, `fork-pr-flow`).
7. **Phase 5 Verify** — run the repo's actual checks; review the final diff + git state; verify any claimed remote state on the real remote; report `not run` / `failed` / `passed` without optimistic language (`verify-then-commit`).
8. **Phase 6 Close out honestly** — open/update the intended PR; comment with evidence + remaining work; close only when closure criteria are met AND closure authority is explicit; leave a session note/handoff when incomplete (`session-continuity`); record noticed adjacent work without silently expanding scope.
9. **State vocabulary** — the five dedup verdicts + the deliverable states, as an enumerated list.
10. **Provider mapping** — a short table: each phase → Claude asset vs Codex-native equivalent, showing the contract is neutral and the skill is Claude's adapter.

- [ ] **Step 2: Add the `contract` capability row to `capabilities.json`**

```json
{
  "name": "issue-work-loop",
  "type": "contract",
  "path": "docs/workflows/issue-work-loop.md",
  "description": "The provider-neutral issue work loop: the six phases (orient, discover, deduplicate, bound+execute, verify, close-out), the state vocabulary, and the two-authority invariant (repository mutation vs external/GitHub mutation are separate grants). Claude automates it via the issue-work-loop skill and bin/issue-dedup-scan.sh; Codex follows it directly.",
  "provider": { "claude": "installed", "codex": "manual" },
  "maturity": "documented",
  "mutation": [],
  "version_introduced": "0.4.0"
}
```

- [ ] **Step 3: Run `make check` and commit**

Run: `make check`
Expected: pass — links resolve (inline-code refs, no relative-link resolution), inventory OK with the contract row.

```bash
git add docs/workflows/issue-work-loop.md capabilities.json
git commit -m "docs(#60): portable issue-work-loop contract"
```

---

### Task 3: The Claude skill `skills/issue-work-loop/` (draft)

Thin orchestrator that walks the contract, delegating each phase. Ships **draft** (pressure-tests deferred).

**Files:**
- Create: `skills/issue-work-loop/SKILL.md` (via `bin/new.sh`, then edit body)
- Modify: `capabilities.json` (the row `bin/new.sh` appended — set `maturity: "draft"`)
- Modify: `docs/skill-portability-audit.md` (add the bound-table row — required or `make check` fails)
- Modify: `CHANGELOG.md` (draft entry)

**Interfaces:**
- Consumes: `docs/workflows/issue-work-loop.md` (the contract it automates), `bin/issue-dedup-scan.sh` (Phase 3), and the Bindle-native skills named per phase.
- Produces: the `issue-work-loop` Claude skill.

- [ ] **Step 1: Scaffold the skill**

Run: `bin/new.sh skill issue-work-loop`
Expected: creates `skills/issue-work-loop/SKILL.md` and appends a draft `capabilities.json` skill row.

- [ ] **Step 2: Write the SKILL.md body**

Replace the scaffolded body. Frontmatter `name: issue-work-loop`; `description:` a "Use when …" trigger for taking a repo issue from discovery to an honest end state. Body: a short intro that the normative source is the contract `docs/workflows/issue-work-loop.md` — this skill only automates it for Claude — followed by the six phases as an actionable checklist, each naming the Bindle asset it delegates to (Phase 1 `domi-consumer`; Phase 3 `bin/issue-dedup-scan.sh` with the exit-code→verdict mapping and the "exit 4 never means no-work" rule; Phase 5 `verify-then-commit`; Phase 6 `session-continuity`). Include the two-authority invariant as a hard rule (implement ≠ close/merge/publish) and the honesty rule (never trust a `done` claim without checking checkout + real remote; a failed dedup query is `uncertain`, never `already-done`).

- [ ] **Step 3: Set the skill row maturity to draft**

In `capabilities.json`, on the appended `issue-work-loop` skill row, set `"maturity": "draft"` and `"version_introduced": "0.4.0"` (keep `provider.claude: "installed"`, `provider.codex: "untested"`).

- [ ] **Step 4: Add the skill-portability-audit row**

In `docs/skill-portability-audit.md`, add a row matching the existing 11-column format (`| Skill | Purpose | Owner / source of truth | F: format | C: Claude status | X: Codex status | Invocation assumptions | Runtime dependencies | Evidence level | Disposition | Required cleanup / follow-up |`):

```
| `issue-work-loop` | Walk the portable issue-work-loop contract, delegating each phase to Bindle-native assets | Bindle (portable contract exists separately: `issue-work-loop.md`) | yes (frontmatter only) | installed, **draft** — not pressure-tested | untested | implicit trigger; invokes `bin/issue-dedup-scan.sh` (portable bash) and existing Bindle skills per phase | `bin/issue-dedup-scan.sh`, `docs/workflows/issue-work-loop.md`, `domi-consumer`/`verify-then-commit`/`session-continuity` skills | Claude: draft/untested · Codex: untested | **portable** (contract is provider-neutral; skill is the Claude adapter; helper is portable bash) | pressure-test the 6-phase walk (RED→GREEN); attempt a Codex run against the contract |
```

- [ ] **Step 5: Add the draft CHANGELOG entry**

In `CHANGELOG.md` under the unreleased section, add a bullet marking the skill a **draft** (unverified until pressure-tested), and note the contract + helper as shipped:

```markdown
- **issue-work-loop** (#60): portable issue work loop — contract `docs/workflows/issue-work-loop.md` + `bin/issue-dedup-scan.sh` (tested) + `issue-work-loop` skill (**draft**, pressure-tests deferred).
```

- [ ] **Step 6: Run `make check` and commit**

Run: `make check`
Expected: pass — the skill-row ↔ audit-row bijection holds (skill added to both), frontmatter valid, inventory OK.

```bash
git add skills/issue-work-loop/SKILL.md capabilities.json docs/skill-portability-audit.md CHANGELOG.md
git commit -m "feat(#60): issue-work-loop Claude skill (draft)"
```

---

## Self-Review

**Spec coverage** (checked against `docs/design/2026-07-14-issue-work-loop-design.md`):
- Trio (contract/skill/adapter) → Tasks 2/3/1. ✓
- Six phases + delegation table → Task 2 Step 1. ✓
- Two-authority invariant → Task 2 §2 + Task 3 body. ✓
- Honest dedup helper (exit-code guarantee, no self-`already-done`) → Task 1 (impl + test case 4). ✓
- Helper tested now; skill ships draft; pressure-tests deferred → Task 1 tests, Task 3 Step 3/5. ✓
- #29 inventory 3-place touch → Task 1 Step 6 (script row), Task 2 Step 2 (contract row), Task 3 Steps 3+4 (skill row + audit row). ✓
- `make check` green + helper tests → each task's final step. ✓

**Placeholder scan:** every code step shows full content; no TBD/TODO. ✓

**Type/name consistency:** `bin/issue-dedup-scan.sh`, exit codes 0/3/4/64, verdicts `no-evidence`/`evidence-found`/`uncertain`, and the `GH` env override are identical across the helper impl (Task 1 Step 3), its test (Step 1), the contract Phase 3 mapping (Task 2), and the skill body (Task 3). ✓
