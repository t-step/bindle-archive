# Release Captain L4 (strategy seam) Implementation Plan — PR-A

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the provider-neutral release-strategy seam (`release-captain.toml` + a two-verb `dry-run`/`apply` strategy contract) and its one `local-release-please` strategy, plus the Release Please configuration that makes Release Please the artifact authority — all with fixture tests, no publication path.

**Architecture:** A thin selector (`bin/release-strategy.sh`) reads a single `strategy` key from `release-captain.toml`, fails closed on missing/unknown, and dispatches a verb to `bin/release-strategies/<strategy>.sh`. The one strategy, `local-release-please.sh`, assembles `release-please release-pr` invocations: `dry-run` is read-only (zero mutation), `apply` creates/updates the release PR and refuses without an ephemeral approval token passed by the caller. Release Please config + manifest (`release-type: simple`, seeded at `0.4.0`) make it own `VERSION` + `CHANGELOG.md`.

**Tech Stack:** Bash (POSIX-ish, `set -euo pipefail`), git fixtures for tests (repo idiom: `bin/test-*.sh`), Release Please via `npx` (stubbed in tests through a `RELEASE_PLEASE_CMD` override), `capabilities.json` inventory.

## Global Constraints

- **Three qualified authorities**, used verbatim in every script header/doc: intent → Release Captain; artifact → Release Please; publication → human maintainer. Never the bare word "authority".
- **`apply` is an artifact action only.** It may only create/update the release PR. It must NEVER merge, tag, create a GitHub Release, publish, or deploy.
- **Strategy scripts are non-interactive** — never prompt, never block on input. All human interaction lives in the (future L3) orchestrator.
- **Fail closed.** Missing `release-captain.toml`, missing `strategy` key, or an unknown strategy is a hard stop with a nonzero exit. No implicit fallback, registry, or discovery.
- **Approval token is ephemeral invocation state** passed by the caller into `apply` — not a reusable secret, not a persisted marker. `apply` without it is a hard stop before any mutation.
- **`dry-run` proves zero mutation** of repository, branch, remote, Release Please manifest, and working tree.
- **Tests never touch the network or a real repo** — stub `release-please` via `RELEASE_PLEASE_CMD`; use throwaway git fixtures.
- Every commit must pass `make check` (shellcheck, `shfmt -i 2 -ci -w`, links, inventory, private-info) and the pre-commit hooks. Never `--no-verify`. Work on branch `feature/release-captain-l4-116`.
- `version_introduced` for new capabilities = `0.5.0`.

---

### Task 1: Config + selector seam (`release-captain.toml`, `bin/release-strategy.sh`)

**Files:**
- Create: `release-captain.toml`
- Create: `bin/release-strategy.sh`
- Test: `bin/test-release-strategy.sh`

**Interfaces:**
- Produces: `bin/release-strategy.sh <verb> [args...]` where `<verb>` ∈ {`which`, `dry-run`, `apply`}. `which` prints the resolved strategy name and script path (for the L3 orchestrator's "show exact strategy" requirement) and exits 0. `dry-run`/`apply` are dispatched verbatim (plus remaining args) to `bin/release-strategies/<strategy>.sh`. Exit codes: `0` ok; `64` fail-closed config error (missing file / missing key / unknown strategy); `2` unknown verb.
- Consumes: `release-captain.toml` key `strategy = "<name>"`.

- [ ] **Step 1: Write the failing test harness with the fail-closed + which cases**

Create `bin/test-release-strategy.sh` (mirrors `bin/test-session-end-land.sh` idiom):

```bash
#!/usr/bin/env bash
#
# test-release-strategy.sh — exercise bin/release-strategy.sh (the selector seam)
# and bin/release-strategies/local-release-please.sh against throwaway fixtures
# with a stubbed release-please. Never touches the network or a real repo.
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEL="$REPO_ROOT/bin/release-strategy.sh"

pass=0 fail=0
ok() { printf '  \342\234\223 %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \342\234\227 %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# fixture_repo — a checkout copy with bin/ + release-captain.toml, so the
# selector resolves paths relative to its own location. We invoke the real
# selector but point it at a fixture config via RC_CONFIG override.
run() { # run <config-file> <args...> -> sets $code/$out
  local cfg="$1"; shift
  out="$(RC_CONFIG="$cfg" "$SEL" "$@" 2>&1)"; code=$?
}

# --- fail-closed: missing config ---
run "$TMP/nope.toml" which
{ [ "$code" -eq 64 ] && printf '%s' "$out" | grep -qi 'missing'; } \
  && ok "missing config -> exit 64" || bad "missing config ($code): $out"

# --- fail-closed: config present but no strategy key ---
: >"$TMP/empty.toml"
run "$TMP/empty.toml" which
[ "$code" -eq 64 ] && ok "no strategy key -> exit 64" || bad "no key ($code)"

# --- fail-closed: unknown strategy name ---
printf 'strategy = "does-not-exist"\n' >"$TMP/unknown.toml"
run "$TMP/unknown.toml" which
{ [ "$code" -eq 64 ] && printf '%s' "$out" | grep -qi 'unknown strategy'; } \
  && ok "unknown strategy -> exit 64" || bad "unknown strategy ($code): $out"

# --- which: resolves the real local-release-please strategy ---
printf 'strategy = "local-release-please"\n' >"$TMP/good.toml"
run "$TMP/good.toml" which
{ [ "$code" -eq 0 ] && printf '%s' "$out" | grep -q 'local-release-please'; } \
  && ok "which resolves strategy" || bad "which ($code): $out"

# --- unknown verb ---
run "$TMP/good.toml" bogus-verb
[ "$code" -eq 2 ] && ok "unknown verb -> exit 2" || bad "unknown verb ($code)"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
```

- [ ] **Step 2: Run to verify it fails**

Run: `bash bin/test-release-strategy.sh`
Expected: FAIL — `bin/release-strategy.sh` does not exist yet (all cases error).

- [ ] **Step 3: Create `release-captain.toml`**

```toml
# Release Captain configuration.
#
# Selects the one release strategy the orchestrator will drive. The strategy
# named here must have a matching script at bin/release-strategies/<name>.sh.
# There is no fallback, registry, or discovery: an unknown or missing value is
# a hard stop. The strategy is an ARTIFACT strategy (Release Please owns the
# VERSION/CHANGELOG/release-PR artifacts); it never merges, tags, publishes, or
# deploys — publication is a separate, explicitly human-authorized action.
strategy = "local-release-please"
```

- [ ] **Step 4: Write `bin/release-strategy.sh`**

```bash
#!/usr/bin/env bash
#
# release-strategy.sh — the provider-neutral release-strategy seam for Release
# Captain (L4 of #116). Reads the single `strategy` key from release-captain.toml
# and dispatches a verb to bin/release-strategies/<strategy>.sh. Fails closed on
# a missing file, missing key, or unknown strategy. Selection only — it performs
# no release action itself and knows nothing about approval.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${RC_CONFIG:-$REPO_ROOT/release-captain.toml}"

die() { echo "release-strategy: $1" >&2; exit "${2:-64}"; }

[ -f "$CONFIG" ] || die "release-captain.toml missing at $CONFIG" 64

# Minimal, dependency-free parse of `strategy = "value"` (first match wins).
strategy="$(sed -n 's/^[[:space:]]*strategy[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG" | head -n1)"
[ -n "$strategy" ] || die "no 'strategy' key in $CONFIG" 64

script="$REPO_ROOT/bin/release-strategies/$strategy.sh"
[ -f "$script" ] || die "unknown strategy '$strategy' (no $script)" 64

verb="${1:-}"
case "$verb" in
  which)
    echo "strategy=$strategy"
    echo "script=$script"
    ;;
  dry-run | apply)
    shift
    exec bash "$script" "$verb" "$@"
    ;;
  *)
    die "unknown verb '${verb:-<none>}' (want: which|dry-run|apply)" 2
    ;;
esac
```

- [ ] **Step 5: Run tests to verify the fail-closed + which cases pass**

Run: `bash bin/test-release-strategy.sh`
Expected: the 5 Task-1 cases PASS. (`dry-run`/`apply` dispatch will still fail until Task 2 creates the strategy script — those cases are added in Task 2, so at this point the harness only holds Task-1 cases and is green.)

- [ ] **Step 6: Format + commit**

```bash
shfmt -i 2 -ci -w bin/release-strategy.sh bin/test-release-strategy.sh
git add release-captain.toml bin/release-strategy.sh bin/test-release-strategy.sh
git commit -m "feat(#116): release-strategy seam — fail-closed strategy selector"
```

(This commit will trip inventory until Task 5 registers `bin/release-strategy.sh`. If `make check` runs in the pre-commit hook and blocks, do Task 5's inventory row for this file first, then commit. Simplest: commit Tasks 1–4 together at Task 4's end, or add the inventory row now. See Task 5.)

---

### Task 2: The `local-release-please` strategy

**Files:**
- Create: `bin/release-strategies/local-release-please.sh`
- Test: `bin/test-release-strategy.sh` (extend)

**Interfaces:**
- Produces: `local-release-please.sh <verb> [args...]`. `dry-run` runs the release-please release-pr command with `--dry-run` (read-only, zero mutation) and prints its output. `apply` requires `--approval-token <non-empty>`; without it, exit `3` and no invocation. Both resolve the release-please binary from `RELEASE_PLEASE_CMD` (default `npx release-please`), enabling test stubs. Exit `2` on unknown verb.
- Consumes: env `RELEASE_PLEASE_CMD` (override), `RELEASE_PLEASE_REPO_URL` (override; default derived from `git remote get-url origin`).

- [ ] **Step 1: Add failing dry-run + apply-token cases to the harness**

Append to `bin/test-release-strategy.sh` (before the summary print):

```bash
# A stub release-please that records its argv and mutates NOTHING.
STUB="$TMP/rp-stub.sh"
cat >"$STUB" <<'EOF'
#!/usr/bin/env bash
echo "STUB-RELEASE-PLEASE $*" >>"$RP_STUB_LOG"
echo "release-please stub ok"
EOF
chmod +x "$STUB"

# A git fixture the strategy runs inside; we assert it stays byte-identical.
FIX="$TMP/fix"; git init -q "$FIX"
git -C "$FIX" config user.email t@e.st; git -C "$FIX" config user.name t
git -C "$FIX" checkout -q -b main; : >"$FIX/f"; git -C "$FIX" add f
git -C "$FIX" commit -qm base
git -C "$FIX" remote add origin https://example.invalid/o/r.git
snapshot() { git -C "$FIX" status --porcelain; git -C "$FIX" rev-parse HEAD; }

RP_STUB_LOG="$TMP/rp.log"; : >"$RP_STUB_LOG"
before="$(snapshot)"

# --- dry-run: calls release-please with --dry-run, mutates nothing ---
out="$(cd "$FIX" && RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
       "$SEL" dry-run 2>&1)"; code=$?
after="$(snapshot)"
{ [ "$code" -eq 0 ] \
  && grep -q -- '--dry-run' "$RP_STUB_LOG" \
  && grep -q 'release-pr' "$RP_STUB_LOG" \
  && [ "$before" = "$after" ]; } \
  && ok "dry-run assembles --dry-run + mutates nothing" \
  || bad "dry-run ($code): log=$(cat "$RP_STUB_LOG"); mutated=$([ "$before" = "$after" ] && echo no || echo YES)"

# --- apply without token: refuses, no invocation ---
: >"$RP_STUB_LOG"
out="$(cd "$FIX" && RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
       "$SEL" apply 2>&1)"; code=$?
{ [ "$code" -eq 3 ] && [ ! -s "$RP_STUB_LOG" ]; } \
  && ok "apply without token refuses, no invocation" \
  || bad "apply-no-token ($code): log=$(cat "$RP_STUB_LOG")"

# --- apply with token: invokes release-please WITHOUT --dry-run ---
: >"$RP_STUB_LOG"
out="$(cd "$FIX" && RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
       "$SEL" apply --approval-token "eph-123" 2>&1)"; code=$?
{ [ "$code" -eq 0 ] \
  && grep -q 'release-pr' "$RP_STUB_LOG" \
  && ! grep -q -- '--dry-run' "$RP_STUB_LOG"; } \
  && ok "apply with token invokes release-pr (no --dry-run)" \
  || bad "apply-token ($code): log=$(cat "$RP_STUB_LOG")"
```

- [ ] **Step 2: Run to verify the new cases fail**

Run: `bash bin/test-release-strategy.sh`
Expected: FAIL — `bin/release-strategies/local-release-please.sh` does not exist (dispatch errors).

- [ ] **Step 3: Write `bin/release-strategies/local-release-please.sh`**

```bash
#!/usr/bin/env bash
#
# local-release-please.sh — the local Release Please ARTIFACT strategy for
# Release Captain (L4 of #116). Release Please is the artifact authority: it
# owns the VERSION bump, the CHANGELOG.md content, and the release PR. This
# strategy assembles the `release-please release-pr` invocation and nothing
# else. It NEVER merges, tags, creates a GitHub Release, publishes, or deploys —
# publication is a separate, explicitly human-authorized action.
#
# Verbs:
#   dry-run  read-only preview; proves zero mutation.
#   apply    create/update the release PR; requires --approval-token <ephemeral>
#            passed by the orchestrator for this one invocation. No token =>
#            hard stop, no invocation. The token is ephemeral invocation state,
#            never a reusable secret or a persisted approval marker.
#
set -euo pipefail

verb="${1:-}"; shift || true

: "${RELEASE_PLEASE_CMD:=npx release-please}"
repo_url="${RELEASE_PLEASE_REPO_URL:-}"
if [ -z "$repo_url" ]; then
  origin="$(git remote get-url origin 2>/dev/null || true)"
  # normalize git@github.com:o/r.git and https://github.com/o/r(.git) -> o/r
  repo_url="$(printf '%s' "$origin" | sed -E 's#^git@[^:]+:##; s#^https?://[^/]+/##; s#\.git$##')"
fi

rp() { # invoke the (possibly stubbed) release-please binary with args
  # shellcheck disable=SC2086 # RELEASE_PLEASE_CMD may be "npx release-please"
  $RELEASE_PLEASE_CMD "$@"
}

case "$verb" in
  dry-run)
    rp release-pr --repo-url="$repo_url" --dry-run "$@"
    ;;
  apply)
    token=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --approval-token) token="${2:-}"; shift 2 ;;
        --approval-token=*) token="${1#*=}"; shift ;;
        *) shift ;;
      esac
    done
    if [ -z "$token" ]; then
      echo "local-release-please: apply refused — no approval token" >&2
      exit 3
    fi
    rp release-pr --repo-url="$repo_url"
    ;;
  *)
    echo "local-release-please: unknown verb '${verb:-<none>}'" >&2
    exit 2
    ;;
esac
```

- [ ] **Step 4: Run tests to verify all cases pass**

Run: `bash bin/test-release-strategy.sh`
Expected: all Task-1 + Task-2 cases PASS, `0 failed`.

- [ ] **Step 5: Format + commit**

```bash
shfmt -i 2 -ci -w bin/release-strategies/local-release-please.sh bin/test-release-strategy.sh
git add bin/release-strategies/local-release-please.sh bin/test-release-strategy.sh
git commit -m "feat(#116): local-release-please artifact strategy (dry-run/apply, token-gated)"
```

(Same inventory caveat as Task 1 — register in Task 5 if the hook blocks.)

---

### Task 3: Release Please configuration + manifest

**Files:**
- Create: `release-please-config.json`
- Create: `.release-please-manifest.json`
- Test: `bin/test-release-strategy.sh` (extend with a config-validity case)

**Interfaces:**
- Produces: a `release-type: simple` config that makes Release Please manage `VERSION` + `CHANGELOG.md` for the repo root package (`.`), seeded at `0.4.0`.

- [ ] **Step 1: Write a failing config-validity case**

Append to `bin/test-release-strategy.sh` (before the summary):

```bash
# --- Release Please config: valid JSON, simple type, manifest seeded 0.4.0 ---
CFG="$REPO_ROOT/release-please-config.json"
MAN="$REPO_ROOT/.release-please-manifest.json"
{ python3 -c "import json,sys; c=json.load(open('$CFG')); \
    p=c['packages']['.']; assert p['release-type']=='simple', p; \
    m=json.load(open('$MAN')); assert m['.']=='0.4.0', m" ; } \
  && ok "release-please config: simple type, manifest seeded 0.4.0" \
  || bad "release-please config invalid"
```

- [ ] **Step 2: Run to verify it fails**

Run: `bash bin/test-release-strategy.sh`
Expected: FAIL — config files do not exist.

- [ ] **Step 3: Create `release-please-config.json`**

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "packages": {
    ".": {
      "release-type": "simple",
      "package-name": "bindle",
      "changelog-path": "CHANGELOG.md",
      "extra-files": ["VERSION"]
    }
  }
}
```

- [ ] **Step 4: Create `.release-please-manifest.json`**

```json
{
  ".": "0.4.0"
}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `bash bin/test-release-strategy.sh`
Expected: all cases PASS.

- [ ] **Step 6: Commit**

```bash
git add release-please-config.json .release-please-manifest.json bin/test-release-strategy.sh
git commit -m "feat(#116): release-please config (simple type) + manifest seeded 0.4.0"
```

---

### Task 4: Wire the test into `make test` + pre-commit

**Files:**
- Modify: `Makefile` (append to the `test:` target list)
- Modify: `.pre-commit-config.yaml` (add a `bindle-test-release-strategy` hook)

**Interfaces:** none produced; makes the Task-1–3 test run under `make test` and pre-commit, matching every other `bin/test-*.sh`.

- [ ] **Step 1: Add the test to `Makefile`'s `test:` target**

After the `bin/test-session-end-land.sh` line, add:

```make
	bin/test-release-strategy.sh
```

- [ ] **Step 2: Add the pre-commit hook**

After the `bindle-test-session-end-land` hook block in `.pre-commit-config.yaml`, add:

```yaml
      - id: bindle-test-release-strategy
        name: release-strategy seam tests
        entry: bin/test-release-strategy.sh
        language: script
        pass_filenames: false
        always_run: true
```

- [ ] **Step 3: Verify both run**

Run: `make test 2>&1 | grep -i 'release-strategy'`
Expected: the release-strategy tests appear and pass.

- [ ] **Step 4: Commit**

```bash
git add Makefile .pre-commit-config.yaml
git commit -m "test(#116): wire release-strategy seam tests into make test + pre-commit"
```

---

### Task 5: Capability registration, L1 sharpening, plan/spec ledger

**Files:**
- Modify: `capabilities.json` (2 script capability rows + 1 ledger row for the plan doc)
- Modify: `docs/workflows/release-captain.md` (L1 sharpening)

**Interfaces:** none produced; satisfies `bin/check-inventory.py` (every tracked `bin/**/*.sh` that is not `test-*.sh` must be a `script` capability or a `not_a_capability` entry) and records the L1 wording sharpening.

- [ ] **Step 1: Register the two new scripts as `script` capabilities**

Add to the `capabilities` array of `capabilities.json`, mirroring the `release-evidence` row's schema (`name`, `type: "script"`, `path`, `description`, `provider`, `maturity`, `mutation`, `version_introduced`). Copy the exact `provider`/`maturity`/`mutation` value vocabulary from the `release-evidence` entry (read it first). Two rows:

- `bin/release-strategy.sh` — name `release-strategy`; description: the provider-neutral release-strategy seam (L4 of #116) that reads `release-captain.toml` and dispatches a verb to the selected strategy, failing closed on missing/unknown; selection only, no release action; `version_introduced: "0.5.0"`.
- `bin/release-strategies/local-release-please.sh` — name `local-release-please`; description: the local Release Please artifact strategy (L4 of #116); `dry-run` previews read-only, `apply` creates/updates the release PR and requires an ephemeral approval token; never merges/tags/publishes/deploys; `version_introduced: "0.5.0"`.

- [ ] **Step 2: Add the plan-doc ledger entry**

Add to the `not_a_capability` array (the design spec is already ledgered):

```json
    {
      "path": "docs/superpowers/plans/2026-07-15-release-captain-l4.md",
      "reason": "a point-in-time implementation plan for release-captain L4 (the strategy seam, PR-A of #116), paired with its design spec; planning artifact, not itself a capability."
    },
```

- [ ] **Step 3: Sharpen L1 wording in `docs/workflows/release-captain.md`**

In Step 6 and §5, replace the phrasing that lumps "tagging, and GitHub Release creation" under Release Please's mechanical layer with the three-authority split: **Release Please owns the mechanical release-PR artifact layer (version/changelog updates + the release PR); tag, GitHub Release, package publication, and deployment belong to explicitly human-authorized publication.** Keep it a wording sharpening — do not change the six steps or the invariant.

- [ ] **Step 4: Verify inventory + full gate**

Run: `make check`
Expected: `capability inventory OK` with the new counts; all checks pass. Fix row fields until green (e.g. an unaccepted `version_introduced`, a missing required field).

- [ ] **Step 5: Commit**

```bash
git add capabilities.json docs/workflows/release-captain.md
git commit -m "chore(#116): register L4 strategy capabilities + sharpen L1 publication wording"
```

---

### Task 6: Full-gate green + open PR-A

- [ ] **Step 1: Final full gate**

Run: `make check && make test`
Expected: all green.

- [ ] **Step 2: Push the branch and open PR-A (PAUSE for human merge)**

Push `feature/release-captain-l4-116`, open a PR to `main` referencing #116 (title e.g. `feat(#116): release-captain L4 — provider-neutral strategy seam + local Release Please`). Body: what L4 adds, the three-authority split, the two-verb contract, what is deferred to PR-B (the L3 skill), and that #116 closes on PR-B. **Do not merge — the human confirms the merge.**

## Self-Review

- **Spec coverage:** §3.1 config → Task 1; §3.2 two-verb contract → Tasks 1–2; §3.3 local-release-please → Task 2; §3.4 ephemeral token → Task 2 (apply-token cases); §3.5 RP config seeded 0.4.0 → Task 3; §5 L1 sharpening → Task 5; §8 tests (dry-run zero-mutation, apply refuses w/o token, fail-closed) → Tasks 1–3; §9 inventory → Task 5; §10 PR-A split + §11 handoff → Task 6. Changelog migration (§4) is a v0.5.0-release-time behavior (not a PR-A code task) — correctly out of PR-A's code scope; it happens when the release is cut through the seam.
- **Placeholder scan:** all script + test code is concrete. The only prose-directed step is Task 5 Step 1/3 (register rows / reword L1) — both reference an existing row (`release-evidence`) to copy the exact schema and a specific wording change, not a vague "add appropriate".
- **Type consistency:** selector verbs `which|dry-run|apply` and exit codes (`64` fail-closed, `2` unknown verb, `3` apply-no-token) are used identically across Tasks 1–2 and the tests. `RELEASE_PLEASE_CMD` / `RC_CONFIG` / `RELEASE_PLEASE_REPO_URL` override names match between scripts and tests.
