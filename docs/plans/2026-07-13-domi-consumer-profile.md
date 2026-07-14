# DomI Consumer Profile and Drift-Status Preflight — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Bindle a read-only way to detect a DomI-consumer repo, report its
pin/drift status by *delegating* to DomI's own scripts, and record the DomI
dependency — without vendoring or reimplementing DomI-owned policy.

**Architecture:** A dependency-light bash detector (`bin/domi-status.sh`) parses
`.domi-pin` offline and delegates the drift verdict to DomI's
`offline_drift_check.sh` / `check_pin.sh`, mirroring their exit codes. A portable
contract (`docs/domi-consumer.md`) and a thin Claude-native `domi-consumer` skill
sit on top; `capabilities.json` records the script, the contract, the skill, and
DomI itself via a new `external_upstreams` section.

**Tech Stack:** Bash (the detector), Markdown (contract + skill), Python
(`bin/check-inventory.py` extension), the repo's `bin/test-*.sh` harness convention.

Design spec: `docs/design/2026-07-13-domi-consumer-profile.md`. Issue: #58.

## Global Constraints

- **Report, never reimplement.** The detector must delegate the drift verdict to
  DomI's own scripts; it may implement only pin *parsing* and the offline-only
  verdicts (`not-a-domi-consumer`, `malformed`). Never claim `current` without a
  delegated check confirming it.
- **Exit codes are identical to DomI `check_pin.sh`:** `0` current · `1` behind ·
  `2` not-a-domi-consumer (no `.domi-pin`) · `3` forked · `4` unverifiable
  (offline) · `5` malformed. Usage errors exit `64`.
- **`.domi-pin` schema (5 fields):** `upstream`, `branch`, `sha` (`^[0-9a-f]{40}$`),
  `manifest_sha256`, `pinned_at`.
- **`make check` must pass before every commit; `make test` must pass for
  test-bearing tasks.** Never `--no-verify`. Work on branch
  `feature/domi-consumer-profile` (already cut); never commit to `main`.
- **Every new `bin/*.sh` and `docs/**/*.md` must be classified in
  `capabilities.json` in the same commit that adds it, or `make check` fails.**
  Adding the skill touches THREE places (skill dir + `capabilities.json` skill row
  + `docs/skill-portability-audit.md` row).
- **Inventory row values:** `version_introduced: "0.4.0"`; `maturity ∈ {draft,
  documented, tested}` (a `skill` marked `tested` requires a `PRESSURE-TESTS.md`,
  so the unpressured skill ships `draft`); `provider` values ∈ `{installed,
  manual, untested, unsupported, n/a}`.
- **Phase 1: Claude assets stay Claude-native** — do not neutralize the
  `SKILL.md`.
- **Commit trailer** (every commit): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: `bin/domi-status.sh` — pin parsing + offline verdicts

Detector skeleton: argument handling, target-repo resolution, `.domi-pin`
detection, five-field parse, `not-a-domi-consumer` / `malformed` verdicts, and
offline fact reporting. A valid pin with no DomI reachable reports
`unverifiable` (delegation is wired in Task 2). Includes the `script` capability
row so `make check` stays green.

**Files:**
- Create: `bin/domi-status.sh`
- Create: `bin/test-domi-status.sh` (auto-excluded from the inventory scan)
- Modify: `capabilities.json` (add one `script` row)

**Interfaces:**
- Produces: `bin/domi-status.sh [--repo <path>]`. Exit `0/1/2/3/4/5` per the
  Global Constraints; `64` on usage error. Stdout carries a compact verdict line;
  a valid pin also prints `pin: <upstream>@<short-sha> branch=<b> pinned_at=<t>`.
  Later tasks add delegation (Task 2) and the inherited-policy block (Task 4).

- [ ] **Step 1: Write the failing test harness + offline cases**

Create `bin/test-domi-status.sh`:

```bash
#!/usr/bin/env bash
#
# test-domi-status.sh — exercise bin/domi-status.sh against throwaway fixture
# repos. Never touches a real DomI-consumer repo (issue #58). Delegation cases
# (current/behind/forked) require DomI's offline_drift_check.sh to be locatable;
# when it is not, those cases SKIP (honest degraded coverage), never fail.
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DS="$REPO_ROOT/bin/domi-status.sh"

pass=0 fail=0 skip=0
ok()   { printf '  ✓ %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  ✗ %s\n' "$1"; fail=$((fail + 1)); }
skipt(){ printf '  ⊘ %s (skipped: %s)\n' "$1" "$2"; skip=$((skip + 1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# make_consumer <dir> <sha> <manifest_sha256> — write a fixture repo with a pin.
make_consumer() {
  local dir="$1" sha="$2" mhash="$3"
  mkdir -p "$dir"
  cat >"$dir/.domi-pin" <<EOF
upstream: domattioli/DomI
branch: main
sha: $sha
manifest_sha256: $mhash
pinned_at: 2026-07-13T00:00:00Z
EOF
}

# run_ds <target-repo> [env VAR=val ...] — echo exit code, capture stdout+stderr
# via files the caller reads.
OUT=""; ERR=""; CODE=0
run_ds() {
  local target="$1"; shift
  OUT="$TMP/out"; ERR="$TMP/err"
  env "$@" bash "$DS" --repo "$target" >"$OUT" 2>"$ERR"; CODE=$?
}

FORTY="$(printf 'a%.0s' {1..40})"  # 40 'a's — a valid-shaped SHA

# --- not-a-domi-consumer ---
mkdir -p "$TMP/plain"
run_ds "$TMP/plain"
[ "$CODE" -eq 2 ] && grep -q "not-a-domi-consumer" "$OUT" \
  && ok "no .domi-pin → not-a-domi-consumer (exit 2)" \
  || bad "no .domi-pin → not-a-domi-consumer (exit 2) [got $CODE]"

# --- malformed: bad sha ---
make_consumer "$TMP/bad" "not-a-sha" "$(printf 'b%.0s' {1..64})"
run_ds "$TMP/bad"
[ "$CODE" -eq 5 ] && grep -qi "malformed" "$ERR" && grep -qi "sha" "$ERR" \
  && ok "bad sha → malformed (exit 5) naming the field" \
  || bad "bad sha → malformed (exit 5) naming the field [got $CODE]"

# --- malformed: missing upstream ---
mkdir -p "$TMP/noup"
printf 'branch: main\nsha: %s\n' "$FORTY" >"$TMP/noup/.domi-pin"
run_ds "$TMP/noup"
[ "$CODE" -eq 5 ] && grep -qi "upstream" "$ERR" \
  && ok "missing upstream → malformed (exit 5)" \
  || bad "missing upstream → malformed (exit 5) [got $CODE]"

# --- unverifiable: valid pin, no DomI reachable ---
make_consumer "$TMP/unv" "$FORTY" "$(printf 'c%.0s' {1..64})"
# Force the locators to find nothing.
run_ds "$TMP/unv" DOMI_SCRIPTS_DIR=/nonexistent DOMI_LOCAL_CHECKOUT=/nonexistent
[ "$CODE" -eq 4 ] && grep -qi "unverifiable" "$OUT" && grep -q "pin: domattioli/DomI@aaaaaaa" "$OUT" \
  && ok "valid pin, no DomI → unverifiable (exit 4) + reports pin facts" \
  || bad "valid pin, no DomI → unverifiable (exit 4) + pin facts [got $CODE]"

printf '\n%d passed, %d failed, %d skipped\n' "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash bin/test-domi-status.sh`
Expected: FAIL — `bin/domi-status.sh` does not exist yet (`bash: .../domi-status.sh: No such file or directory`), cases report ✗.

- [ ] **Step 3: Write `bin/domi-status.sh` (offline core)**

```bash
#!/usr/bin/env bash
#
# domi-status.sh — read-only DomI-consumer detector. Parses a repo's .domi-pin
# and reports a compact drift verdict, DELEGATING the drift check to DomI's own
# scripts (report inherited policy, do not reimplement it — see
# docs/domi-consumer.md). Read-only toward the target repo.
#
# Usage: bin/domi-status.sh [--repo <path>]
#
# Exit codes (identical to DomI check_pin.sh, so callers can treat the two
# interchangeably):
#   0 current    1 behind    2 not-a-domi-consumer (no .domi-pin)
#   3 forked     4 unverifiable (offline)    5 malformed
#   64 usage error
#
set -uo pipefail

TARGET=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) TARGET="${2:-}"; shift 2 ;;
    -h | --help) grep '^#' "$0" | sed 's/^#\{1,\} \{0,1\}//'; exit 0 ;;
    *) echo "domi-status.sh: unknown argument '$1'" >&2; exit 64 ;;
  esac
done

if [ -z "$TARGET" ]; then
  TARGET="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
fi
PIN_FILE="$TARGET/.domi-pin"

# 1. No pin → not a consumer.
if [ ! -f "$PIN_FILE" ]; then
  echo "not-a-domi-consumer: no .domi-pin in $TARGET"
  exit 2
fi

# 2. Parse the five fields.
pin_get() { grep -E "^$1:" "$PIN_FILE" | head -1 | sed -E "s/^$1:[[:space:]]*//" | tr -d '"'; }
UPSTREAM="$(pin_get upstream)"
BRANCH="$(pin_get branch)"
SHA="$(pin_get sha)"
MANIFEST="$(pin_get manifest_sha256)"
PINNED_AT="$(pin_get pinned_at)"

# 3. Validate (offline-decidable).
if [ -z "$UPSTREAM" ]; then
  echo "malformed: .domi-pin missing 'upstream' field" >&2
  exit 5
fi
if ! printf '%s' "$SHA" | grep -qE '^[0-9a-f]{40}$'; then
  echo "malformed: .domi-pin 'sha' is not a 40-hex commit ('$SHA')" >&2
  exit 5
fi

# 4. Fact reporting (always, offline-safe).
echo "pin: $UPSTREAM@${SHA:0:7} branch=$BRANCH pinned_at=$PINNED_AT"

# 5. Drift verdict. Task 2 wires delegation here; until then, unverifiable.
echo "unverifiable: drift not checked (no DomI delegation reachable)"
exit 4
```

- [ ] **Step 4: Make it executable and run the test**

Run: `chmod +x bin/domi-status.sh && bash bin/test-domi-status.sh`
Expected: PASS — `4 passed, 0 failed, 0 skipped`.

- [ ] **Step 5: Add the `script` capability row**

Add this object to the `capabilities` array in `capabilities.json` (keep the
array's existing formatting/indentation):

```json
{
  "name": "domi-status",
  "type": "script",
  "path": "bin/domi-status.sh",
  "description": "Read-only DomI-consumer detector: parses a repo's .domi-pin and reports a compact drift verdict (current/behind/forked/unverifiable/malformed/not-a-domi-consumer) by delegating the drift check to DomI's own check_pin.sh / offline_drift_check.sh, mirroring their exit codes; never reimplements DomI-owned policy.",
  "provider": {
    "claude": "manual",
    "codex": "manual"
  },
  "maturity": "tested",
  "mutation": [
    "network"
  ],
  "version_introduced": "0.4.0"
}
```

- [ ] **Step 6: Run the gate and commit**

Run: `make check && bash bin/test-domi-status.sh`
Expected: both green (`All checks passed.` and `4 passed, 0 failed`).

```bash
git add bin/domi-status.sh bin/test-domi-status.sh capabilities.json
git commit -m "feat(domi-consumer): pin parsing + offline verdicts in bin/domi-status.sh (#58)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Delegate the drift verdict to DomI's own scripts

Wire the real drift verdict: locate DomI's `offline_drift_check.sh` (and a DomI
checkout), run it against the target repo, and map its exit code straight
through. When no delegation target is reachable, keep `unverifiable`.

**Files:**
- Modify: `bin/domi-status.sh` (replace the Task 1 stub at step 5 of the script)
- Modify: `bin/test-domi-status.sh` (add current/behind/forked cases)

**Interfaces:**
- Consumes: DomI `offline_drift_check.sh` exit codes `0 synced / 1 behind /
  3 forked / 2 unpinned / 4 no-clone`, discovered via `$DOMI_SCRIPTS_DIR` →
  `~/.claude/skills/sync-from-domi/scripts` and a checkout via
  `$DOMI_LOCAL_CHECKOUT` → `../DomI` → `/home/user/DomI`.
- Produces: `bin/domi-status.sh` now emits `current`/`behind`/`forked` when
  delegation succeeds.

- [ ] **Step 1: Add failing delegation cases to the test**

Insert before the final `printf` summary in `bin/test-domi-status.sh`:

```bash
# --- delegation cases: require DomI's offline_drift_check.sh ---
find_odc() {
  local d
  for d in "${DOMI_SCRIPTS_DIR:-}" "$HOME/.claude/skills/sync-from-domi/scripts"; do
    [ -n "$d" ] && [ -f "$d/offline_drift_check.sh" ] && { echo "$d/offline_drift_check.sh"; return 0; }
  done
  return 1
}

if ODC="$(find_odc)"; then
  # Build a fixture DomI checkout: a git repo with a MANIFEST.md at a known SHA.
  DOMI="$TMP/DomI"; mkdir -p "$DOMI"
  git -C "$DOMI" init -q -b main
  git -C "$DOMI" config user.email t@t.t; git -C "$DOMI" config user.name t
  printf 'fixture manifest\n' >"$DOMI/MANIFEST.md"
  git -C "$DOMI" add MANIFEST.md; git -C "$DOMI" commit -qm init
  DHEAD="$(git -C "$DOMI" rev-parse HEAD)"
  DMHASH="$(git -C "$DOMI" show HEAD:MANIFEST.md | sha256sum | awk '{print $1}')"
  SCRIPTS_DIR="$(dirname "$ODC")"

  # current: pin sha == DomI HEAD, manifest hash matches.
  make_consumer "$TMP/cur" "$DHEAD" "$DMHASH"
  run_ds "$TMP/cur" DOMI_SCRIPTS_DIR="$SCRIPTS_DIR" DOMI_LOCAL_CHECKOUT="$DOMI"
  [ "$CODE" -eq 0 ] && grep -q "current" "$OUT" \
    && ok "pin at HEAD → current (exit 0)" \
    || bad "pin at HEAD → current (exit 0) [got $CODE]"

  # behind: pin sha != DomI HEAD.
  make_consumer "$TMP/beh" "$FORTY" "$DMHASH"
  run_ds "$TMP/beh" DOMI_SCRIPTS_DIR="$SCRIPTS_DIR" DOMI_LOCAL_CHECKOUT="$DOMI"
  [ "$CODE" -eq 1 ] && grep -q "behind" "$OUT" \
    && ok "pin behind HEAD → behind (exit 1)" \
    || bad "pin behind HEAD → behind (exit 1) [got $CODE]"

  # forked: pin sha == HEAD but manifest hash wrong.
  make_consumer "$TMP/fork" "$DHEAD" "$(printf 'd%.0s' {1..64})"
  run_ds "$TMP/fork" DOMI_SCRIPTS_DIR="$SCRIPTS_DIR" DOMI_LOCAL_CHECKOUT="$DOMI"
  [ "$CODE" -eq 3 ] && grep -q "forked" "$OUT" \
    && ok "manifest mismatch → forked (exit 3)" \
    || bad "manifest mismatch → forked (exit 3) [got $CODE]"
else
  skipt "delegation (current/behind/forked)" "DomI offline_drift_check.sh not found"
fi
```

- [ ] **Step 2: Run the test to verify the new cases fail**

Run: `bash bin/test-domi-status.sh`
Expected: with DomI installed, the three delegation cases FAIL (script still
prints `unverifiable`); if DomI is absent they SKIP. The Task 1 cases still pass.

- [ ] **Step 3: Replace the stub with delegation**

In `bin/domi-status.sh`, replace the two stub lines under `# 5. Drift verdict.`
(the `echo "unverifiable..."` and `exit 4`) with:

```bash
# 5. Drift verdict — delegate to DomI's own scripts (report, don't reimplement).
find_domi_scripts() {
  local d
  for d in "${DOMI_SCRIPTS_DIR:-}" "$HOME/.claude/skills/sync-from-domi/scripts"; do
    [ -n "$d" ] && [ -f "$d/offline_drift_check.sh" ] && { echo "$d"; return 0; }
  done
  return 1
}
find_domi_checkout() {
  local d
  for d in "${DOMI_LOCAL_CHECKOUT:-}" "../DomI" "/home/user/DomI"; do
    [ -n "$d" ] && [ -d "$d/.git" ] && { echo "$d"; return 0; }
  done
  return 1
}

report_verdict() { # report_verdict <label> <exit-code>
  echo "$1"
  exit "$2"
}

SCRIPTS="$(find_domi_scripts || true)"
CHECKOUT="$(find_domi_checkout || true)"

if [ -n "$SCRIPTS" ] && [ -n "$CHECKOUT" ]; then
  # Delegate to DomI's offline sibling-clone drift checker. Its exit codes:
  # 0 synced, 1 behind, 3 forked, 2 unpinned, 4 no-clone.
  REPO_ROOT="$TARGET" DOMI_LOCAL_CHECKOUT="$CHECKOUT" \
    bash "$SCRIPTS/offline_drift_check.sh" >/dev/null 2>&1
  rc=$?
  case "$rc" in
    0) report_verdict "current: pin verified against DomI@${SHA:0:7}" 0 ;;
    1) report_verdict "behind: pinned ${SHA:0:7} is behind DomI upstream — run sync-from-domi" 1 ;;
    3) report_verdict "forked: MANIFEST.md hash mismatch at pinned SHA — local edit or corruption" 3 ;;
    *) : ;;  # 2/4/other → fall through to unverifiable
  esac
fi

report_verdict "unverifiable: drift not checked (no DomI delegation reachable)" 4
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash bin/test-domi-status.sh`
Expected: PASS — `7 passed, 0 failed, 0 skipped` where DomI is installed, or
`4 passed, 0 failed, 3 skipped` where it is not.

- [ ] **Step 5: Run the gate and commit**

Run: `make check && bash bin/test-domi-status.sh`
Expected: both green.

```bash
git add bin/domi-status.sh bin/test-domi-status.sh
git commit -m "feat(domi-consumer): delegate drift verdict to DomI offline_drift_check.sh (#58)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `docs/domi-consumer.md` — portable contract + inventory row

Write the provider-neutral contract the detector and skill honor, and classify
it as a `contract` capability.

**Files:**
- Create: `docs/domi-consumer.md`
- Modify: `capabilities.json` (add one `contract` row)

**Interfaces:**
- Produces: the canonical category list (`branch-commit-discipline`,
  `destructive-action-hard-stops`, `context-session-management`,
  `delegation-dispatch`, `release-semver-governance`, `issue-session-workflow`,
  `sync-update-ownership`) that Task 4 (script output) and Task 6
  (`external_upstreams.authority_for`) reuse verbatim.

- [ ] **Step 1: Write the contract**

Create `docs/domi-consumer.md` with these sections (prose; no code steps to
test — validated by `make check` link/frontmatter checks and the inventory row):

```markdown
# DomI consumer contract

Bindle's provider-neutral contract for recognizing and reporting a DomI
dependency. Bindle **reports** inherited policy; it never **reimplements** it.
DomI (`github.com/domattioli/DomI`) remains the authority for DomI-owned skills
and policy. The executable adapter is `bin/domi-status.sh`.

## `.domi-pin` detection and schema

A DomI-consumer repo commits `.domi-pin` at its root, five fields:
`upstream`, `branch`, `sha` (40-hex), `manifest_sha256` (64-hex), `pinned_at`
(ISO-8601 Z). Absence of the file means the repo is not a DomI consumer.

## Status vocabulary (mirrors DomI `check_pin.sh` exit codes)

| verdict | exit | meaning |
|---------|------|---------|
| current | 0 | pin SHA == upstream HEAD and manifest hash matches |
| behind | 1 | pin SHA != upstream HEAD |
| not-a-domi-consumer | 2 | no `.domi-pin` |
| forked | 3 | manifest hash mismatch at pinned SHA |
| unverifiable | 4 | upstream unreachable — never reported as current |
| malformed | 5 | pin format invalid |

## Source of truth and ownership

DomI owns the definition of every inherited policy. Bindle detects the pin,
reports the verdict, and points at DomI as the authority. Bindle may summarize
the binding categories; it may not silently manufacture a local replacement.

## Write-work gating

`bin/domi-status.sh` reports; the **consumer repo's own policy** decides any hard
stop. current → continue; behind/forked → stop repository write-work *iff* the
consumer repo's policy defines drift as a hard stop, and cite the
`sync-from-domi` path; unverifiable → degraded, never current, follow the
consumer's documented offline policy; malformed → stop and name the bad field;
not-a-domi-consumer → exit cleanly.

## Offline / unverifiable behavior

When neither DomI's scripts nor a DomI checkout are reachable, the detector
reports the pin's self-described facts and the `unverifiable` verdict. It never
upgrades that to `current`.

## Inherited-policy categories and their authority

| category (slug) | authoritative source in DomI |
|-----------------|------------------------------|
| branch-commit-discipline | `skills/git-commit-guard`, `skills/enforce-branch-policy` |
| destructive-action-hard-stops | DomI constitution / session hard-stop policy |
| context-session-management | `skills/session-resume`, spec-006 |
| delegation-dispatch | `skills/dispatch-issue`, `skills/subagent-dispatch-policy` |
| release-semver-governance | `skills/release-integrity`, spec-013 |
| issue-session-workflow | `skills/list-issues`, `skills/check-done` |
| sync-update-ownership | `skills/sync-from-domi` |

## Provider adapters

Claude and Codex both invoke `bin/domi-status.sh` and honor the same vocabulary.
The `domi-consumer` skill is the Claude-native automation; Codex follows this
contract directly.
```

(If any DomI skill path above cannot be confirmed against
`github.com/domattioli/DomI/tree/main/skills`, keep the category slug and mark
the source `DomI (path TBD)` — the slug is the contract; the pointer is
informational. Do not block on it.)

- [ ] **Step 2: Add the `contract` capability row**

Add to the `capabilities` array in `capabilities.json`:

```json
{
  "name": "domi-consumer",
  "type": "contract",
  "path": "docs/domi-consumer.md",
  "description": "The provider-neutral contract for detecting and reporting a DomI-consumer dependency: .domi-pin schema, the status vocabulary mirroring DomI check_pin.sh, source-of-truth/ownership rules, write-work gating, and the inherited-policy category→authority map; bin/domi-status.sh is the executable adapter and the domi-consumer skill is the Claude-native automation.",
  "provider": {
    "claude": "installed",
    "codex": "manual"
  },
  "maturity": "documented",
  "mutation": [],
  "version_introduced": "0.4.0"
}
```

Note: the `contract` capability name `domi-consumer` and the `skill` name
`domi-consumer` (Task 5) share a string but differ in `type`; the inventory keys
on `(type, name)`, so this is allowed (mirrors existing `hands-on-keyboard`
skill + `hands-on-keyboard-contract`… — confirm no `(contract, domi-consumer)`
duplicate only).

- [ ] **Step 3: Run the gate and commit**

Run: `make check`
Expected: green (`capability inventory OK` count increases by one).

```bash
git add docs/domi-consumer.md capabilities.json
git commit -m "docs(domi-consumer): add the portable DomI-consumer contract (#58)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Surface inherited-policy categories + authority in the detector output

Add the static category→authority block to `bin/domi-status.sh` output for any
detected consumer, so a session sees what policy it inherits and where the
authority lives (contract §"Inherited-policy categories").

**Files:**
- Modify: `bin/domi-status.sh` (print the block after the `pin:` line)
- Modify: `bin/test-domi-status.sh` (assert the block appears)

**Interfaces:**
- Consumes: the seven category slugs from `docs/domi-consumer.md` (Task 3).
- Produces: detector output now includes an `authority:` line and the category
  list for every detected consumer (all verdicts except `not-a-domi-consumer`).

- [ ] **Step 1: Add a failing assertion**

In `bin/test-domi-status.sh`, extend the existing `unverifiable` case assertion
to also require the authority line. Replace that case's assertion block with:

```bash
[ "$CODE" -eq 4 ] \
  && grep -qi "unverifiable" "$OUT" \
  && grep -q "pin: domattioli/DomI@aaaaaaa" "$OUT" \
  && grep -q "authority: domattioli/DomI (inherited:" "$OUT" \
  && grep -q "branch-commit-discipline" "$OUT" \
  && ok "valid pin, no DomI → unverifiable (exit 4) + pin facts + authority block" \
  || bad "valid pin, no DomI → unverifiable + pin facts + authority block [got $CODE]"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash bin/test-domi-status.sh`
Expected: the `unverifiable` case FAILS (no `authority:` line yet).

- [ ] **Step 3: Print the authority block**

In `bin/domi-status.sh`, immediately after the `echo "pin: ..."` line (step 4 of
the script), insert:

```bash
# Inherited-policy categories and their authority (docs/domi-consumer.md).
echo "authority: $UPSTREAM (inherited: branch-commit-discipline, destructive-action-hard-stops, context-session-management, delegation-dispatch, release-semver-governance, issue-session-workflow, sync-update-ownership)"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash bin/test-domi-status.sh`
Expected: PASS (`7 passed` with DomI, or `4 passed, 3 skipped` without).

- [ ] **Step 5: Run the gate and commit**

Run: `make check && bash bin/test-domi-status.sh`
Expected: both green.

```bash
git add bin/domi-status.sh bin/test-domi-status.sh
git commit -m "feat(domi-consumer): surface inherited-policy categories + authority (#58)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `skills/domi-consumer/` — thin skill + three-place inventory

Add the Claude-native skill that invokes the detector and interprets the verdict,
plus the two inventory rows the #29 rule requires.

**Files:**
- Create: `skills/domi-consumer/SKILL.md`
- Modify: `capabilities.json` (add one `skill` row)
- Modify: `docs/skill-portability-audit.md` (add one row)

**Interfaces:**
- Consumes: `bin/domi-status.sh` (invocation), `docs/domi-consumer.md`
  (interpretation).

- [ ] **Step 1: Write the skill**

Create `skills/domi-consumer/SKILL.md` (Claude-native frontmatter matches the
repo's other skills — confirm required keys with an existing `skills/*/SKILL.md`):

```markdown
---
name: domi-consumer
description: Use when working in (or unsure whether you're in) a repository that consumes DomI — to detect the .domi-pin, report drift status (current/behind/forked/unverifiable/malformed), and see which inherited policy categories are owned upstream. Reports; never vendors or reimplements DomI-owned policy.
---

# DomI consumer status

Run the read-only detector and interpret its verdict per
`docs/domi-consumer.md`. Never claim `current` without the detector confirming
it; never manufacture a local replacement for a DomI-owned policy.

## Steps

1. Run: `bash bin/domi-status.sh --repo <repo-root>` (default: current repo).
2. Read the exit code / verdict:
   - `not-a-domi-consumer` (2) — nothing to do.
   - `current` (0) — report the source and continue.
   - `behind` (1) / `forked` (3) — if this repo's own policy makes DomI drift a
     hard stop, stop write-work and cite the `sync-from-domi` path; otherwise
     report and continue.
   - `unverifiable` (4) — report degraded status; never treat as current;
     follow the repo's documented offline policy.
   - `malformed` (5) — stop and surface the named bad field.
3. Surface the inherited-policy categories from the detector's `authority:` line
   and point at DomI as the source of truth.

DomI owns its policy. This skill detects and describes the dependency; it does
not vendor, fork, or reimplement it.
```

- [ ] **Step 2: Add the `skill` capability row**

Add to the `capabilities` array in `capabilities.json` (`maturity: draft` —
unpressured; a skill marked `tested` would require a `PRESSURE-TESTS.md`):

```json
{
  "name": "domi-consumer",
  "type": "skill",
  "path": "skills/domi-consumer",
  "description": "Detect a DomI-consumer repo and report its drift status by invoking bin/domi-status.sh, then interpret the verdict per docs/domi-consumer.md and surface the inherited-policy categories and their upstream authority; reports the dependency without vendoring or reimplementing DomI-owned policy.",
  "provider": {
    "claude": "installed",
    "codex": "untested"
  },
  "maturity": "draft",
  "mutation": [
    "network"
  ],
  "version_introduced": "0.4.0"
}
```

- [ ] **Step 3: Add the skill-portability-audit row**

Open `docs/skill-portability-audit.md`, match the existing table's column
layout, and add a row for `domi-consumer` classifying it **portable** (thin
wrapper over a portable bash detector; no Claude-only primitive). Copy the
column set from an adjacent row exactly — the inventory's bound-table check
requires the audit's skill rows to equal `capabilities.json`'s skill set.

- [ ] **Step 4: Run the gate (the three-place check) and commit**

Run: `make check`
Expected: green — `capability inventory OK` with skill bijection + audit
bound-table satisfied. If it fails on bound-table drift, the audit row or skill
row is missing/mismatched; fix before committing.

```bash
git add skills/domi-consumer/SKILL.md capabilities.json docs/skill-portability-audit.md
git commit -m "feat(domi-consumer): add thin Claude-native domi-consumer skill (draft) (#58)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `external_upstreams` provenance + `check-inventory.py` validator

Record DomI as an external upstream integration and teach the inventory checker
to validate the new section.

**Files:**
- Modify: `capabilities.json` (add top-level `external_upstreams` array)
- Modify: `bin/check-inventory.py` (add `check_external_upstreams` + wire it)
- Modify: `bin/test-check-inventory.sh` (add a case for the new validator)

**Interfaces:**
- Consumes: the `detector` (`bin/domi-status.sh`), `contract`
  (`docs/domi-consumer.md`), and category slugs from earlier tasks.
- Produces: `check_external_upstreams(root) -> list[str]` (error strings),
  called from `main()`.

- [ ] **Step 1: Add a failing validator test**

In `bin/test-check-inventory.sh`, following the file's existing fixture pattern
(a temp `capabilities.json`, run `python3 bin/check-inventory.py --root <tmp>`),
add a case asserting that an `external_upstreams` entry missing a required key
(e.g. `owner`) makes the checker exit non-zero with a message naming the missing
key, and that a well-formed entry passes. Match the harness helpers already in
that file.

- [ ] **Step 2: Run it to verify it fails**

Run: `bash bin/test-check-inventory.sh`
Expected: FAIL — `check_external_upstreams` does not exist; the malformed-entry
case is not rejected.

- [ ] **Step 3: Add the validator to `check-inventory.py`**

Add this function (near the other `check_*` functions):

```python
EXTERNAL_UPSTREAM_KEYS = {"name", "owner", "repo", "role", "pin_file",
                          "authority_for", "detector", "contract"}


def check_external_upstreams(root):
    """Validate the optional top-level external_upstreams array: each entry is
    an object carrying the full provenance key set. Not part of the bijection —
    these describe dependencies, not Bindle capabilities."""
    errors = []
    path = os.path.join(root, "capabilities.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    ups = data.get("external_upstreams", [])
    if not isinstance(ups, list):
        return ["capabilities.json: 'external_upstreams' must be an array"]
    for i, e in enumerate(ups):
        label = "external_upstreams[%d]" % i
        if not isinstance(e, dict):
            errors.append("%s: must be an object" % label)
            continue
        missing = EXTERNAL_UPSTREAM_KEYS - set(e.keys())
        if missing:
            errors.append("%s: missing key(s) %s" % (label, sorted(missing)))
        if not isinstance(e.get("authority_for", []), list):
            errors.append("%s: 'authority_for' must be an array" % label)
    return errors
```

Then wire it into `main()` alongside the existing checks (the file already
accumulates with the `errors += check_...(...)` pattern — add
`errors += check_external_upstreams(root)`).

- [ ] **Step 4: Add the `external_upstreams` section to `capabilities.json`**

Add this **top-level** key (a sibling of `capabilities` and `not_a_capability`):

```json
"external_upstreams": [
  {
    "name": "DomI",
    "owner": "domattioli",
    "repo": "domattioli/DomI",
    "role": "upstream workflow authority",
    "pin_file": ".domi-pin",
    "authority_for": [
      "branch-commit-discipline",
      "destructive-action-hard-stops",
      "context-session-management",
      "delegation-dispatch",
      "release-semver-governance",
      "issue-session-workflow",
      "sync-update-ownership"
    ],
    "detector": "bin/domi-status.sh",
    "contract": "docs/domi-consumer.md"
  }
]
```

- [ ] **Step 5: Run the validator test + gate**

Run: `bash bin/test-check-inventory.sh && make check`
Expected: both green (`All checks passed.`).

- [ ] **Step 6: Commit**

```bash
git add capabilities.json bin/check-inventory.py bin/test-check-inventory.sh
git commit -m "feat(inventory): record DomI as an external_upstreams integration (#58)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: CHANGELOG + full-suite verification

Record the work and run the whole gate.

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add a CHANGELOG entry**

Under the current unreleased section (match the file's existing style), add a
line noting the DomI-consumer profile, and **mark the `domi-consumer` skill a
draft** (unpressured, per the repo rule that a skill isn't done until
pressure-tested).

- [ ] **Step 2: Run the full gate**

Run: `make check && make test`
Expected: both green. If `make test` runs `bin/test-domi-status.sh` in an
environment without DomI, its delegation cases skip (not fail).

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog for DomI-consumer profile; skill marked draft (#58)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Post-plan notes (not tasks)

- **PR, not a direct push.** After all tasks, open a PR closing #58 targeting
  `main`. Do not push until the operator asks (repo/global rule).
- **Pressure-test follow-up.** The `domi-consumer` skill ships `draft`. A
  separate pressure-test pass (fresh subagents in fixture repos, per
  superpowers:writing-skills) is required before it can be marked `tested` and
  gain a `PRESSURE-TESTS.md` — track as a follow-up issue, out of scope here.
- **Real-consumer acceptance.** #58's "≥1 real consumer checkout" step needs an
  actual DomI-consumer repo present locally; run `bin/domi-status.sh --repo
  <that repo>` there to satisfy it. Not blocking for the build.

## Self-review

- **Spec coverage:** detector (Tasks 1–2, 4) · contract (Task 3) · skill
  (Task 5) · capabilities.json script/contract/skill rows (Tasks 1/3/5) ·
  `external_upstreams` + validator (Task 6) · fixtures for the full #58 matrix
  (Tasks 1–2) · CHANGELOG/verification (Task 7). All spec sections map to a task.
- **Placeholder scan:** the only deliberate deferrals are informational and
  bounded — the audit-table column copy (Task 5.3) and the DomI skill-path
  pointers (Task 3.1), both with explicit fallbacks; no `TODO`/`TBD` in code.
- **Type consistency:** exit codes `0/1/2/3/4/5` and the six verdict labels are
  used identically across Tasks 1, 2, 4, and the contract; the seven category
  slugs are identical in Tasks 3, 4, and 6; `version_introduced: "0.4.0"` and the
  `maturity` values are consistent with the confirmed schema.
